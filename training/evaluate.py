import argparse
import json
import sys
import os
import torch
import numpy as np
from pathlib import Path
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, StoppingCriteria, StoppingCriteriaList
from peft import PeftModel

# Add src to python path
repo_root = Path(__file__).resolve().parent.parent
sys.path.append(str(repo_root / "src"))

from eval.syntax.parser import parse_action_blocks, ParsedAction

class EndTokenStoppingCriteria(StoppingCriteria):
    def __init__(self, tokenizer, stop_strings):
        self.tokenizer = tokenizer
        self.stop_strings = stop_strings
        
    def __call__(self, input_ids, scores, **kwargs):
        # Efficiently check if the end of the sequence matches any stop string
        # Decode only the newly generated part (heuristic: check last 20 tokens)
        window_size = 20
        if input_ids.shape[1] < window_size:
            text = self.tokenizer.decode(input_ids[0])
        else:
            text = self.tokenizer.decode(input_ids[0][-window_size:])
            
        for stop_str in self.stop_strings:
            if stop_str in text:
                return True
        return False

def load_jsonl(path):
    with open(path, 'r') as f:
        return [json.loads(line) for line in f]

def compare_actions(gold: ParsedAction, pred: ParsedAction) -> dict:
    """
    Compare gold and predicted actions.
    Returns dict of metrics (bools).
    """
    metrics = {
        "valid_syntax": False,
        "type_match": False,
        "name_match": False,
        "args_match": False
    }
    
    # Check if prediction is valid syntax (has action)
    if not pred.action or "missing_action_block" in pred.parse_errors:
        return metrics
    metrics["valid_syntax"] = True
    
    # Compare Type (tool vs say)
    if gold.action_type != pred.action_type:
        return metrics
    metrics["type_match"] = True
    
    if gold.action_type == "tool":
        # Compare Tool Name
        if gold.action_name != pred.action_name:
            return metrics
        metrics["name_match"] = True
        
        # Compare Args (JSON)
        try:
            gold_args = json.loads(gold.action_body)
            pred_args = json.loads(pred.action_body)
            if gold_args == pred_args:
                metrics["args_match"] = True
        except json.JSONDecodeError:
            pass # Args match fails if JSON invalid
            
    elif gold.action_type == "say":
        # For 'say', name_match is implicitly true (N/A)
        metrics["name_match"] = True 
        # Args match is content match? Usually we don't eval exact text match for 'say'.
        # We can just ignore args_match for 'say' or always set True.
        metrics["args_match"] = True 
        
    return metrics

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test_data", type=str, required=True, help="Path to test .jsonl")
    parser.add_argument("--base_model", type=str, required=True)
    parser.add_argument("--adapter_path", type=str, default=None)
    parser.add_argument("--output_file", type=str, default="eval_results.json")
    parser.add_argument("--predictions_file", type=str, default="eval_predictions.jsonl")
    parser.add_argument("--max_samples", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    
    # Load Data
    data = load_jsonl(args.test_data)
    if args.max_samples:
        data = data[:args.max_samples]
    print(f"Loaded {len(data)} samples.")
    
    # Load Model
    print(f"Loading model: {args.base_model}")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16
    )
    
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True
    )
    
    if args.adapter_path:
        print(f"Loading adapter: {args.adapter_path}")
        model = PeftModel.from_pretrained(model, args.adapter_path)
    
    model.eval()
    
    results = []
    
    print("Running evaluation...")
    for sample in tqdm(data):
        prompt = sample['prompt']
        gold_completion = sample['completion']
        
        # Parse Gold
        gold_parsed = parse_action_blocks(gold_completion)
        if "missing_action_block" in gold_parsed.parse_errors:
            # Skip invalid gold samples (shouldn't happen with correct prep)
            continue
            
        # Generate Prediction
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        
        stopping_criteria = StoppingCriteriaList([
            EndTokenStoppingCriteria(tokenizer, ["</action>", "<user>", "<|endoftext|>"])
        ])
        
        with torch.no_grad():
            output_ids = model.generate(
                **inputs, 
                max_new_tokens=512, 
                do_sample=False, # Greedy for deterministic eval
                stopping_criteria=stopping_criteria
            )
        
        # Decode only new tokens
        input_len = inputs["input_ids"].shape[1]
        pred_text = tokenizer.decode(output_ids[0][input_len:], skip_special_tokens=False)
        
        # Truncate at user tag or end of action (same logic as simulator)
        user_idx = pred_text.find("<user>")
        if user_idx != -1:
            pred_text = pred_text[:user_idx].strip()
        
        action_end = "</action>"
        action_idx = pred_text.find(action_end)
        if action_idx != -1:
            pred_text = pred_text[:action_idx+len(action_end)].strip()
            
        # Parse Prediction
        pred_parsed = parse_action_blocks(pred_text)
        
        # Compare
        metrics = compare_actions(gold_parsed, pred_parsed)
        
        results.append({
            "prompt": prompt,
            "gold_text": gold_completion,
            "pred_text": pred_text,
            "metrics": metrics,
            "gold_type": gold_parsed.action_type,
            "pred_type": pred_parsed.action_type if pred_parsed.action else None
        })
        
    # Aggregate Metrics
    if not results:
        print("No results generated.")
        return

    agg = {
        "count": len(results),
        "valid_syntax": np.mean([r["metrics"]["valid_syntax"] for r in results]),
        "type_match": np.mean([r["metrics"]["type_match"] for r in results]),
        "tool_name_match": np.mean([r["metrics"]["name_match"] for r in results if r["gold_type"] == "tool"]),
        "tool_args_match": np.mean([r["metrics"]["args_match"] for r in results if r["gold_type"] == "tool"]),
    }
    
    print("\nResults:")
    print(json.dumps(agg, indent=2))
    
    with open(args.output_file, 'w') as f:
        json.dump(agg, f, indent=2)
        
    if args.predictions_file:
        print(f"Saving predictions to {args.predictions_file}")
        with open(args.predictions_file, 'w') as f:
            for r in results:
                # We save everything including metrics
                f.write(json.dumps(r) + "\n")

if __name__ == "__main__":
    main()

