import argparse
import json
import os
import sys
import random
import torch
from pathlib import Path
from typing import Dict, List, Optional

from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    Trainer,
    TrainingArguments,
    DataCollatorForLanguageModeling,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# Constants
IGNORE_INDEX = -100
MAX_LENGTH = 4096

def load_jsonl(path: str) -> List[Dict]:
    with open(path, 'r') as f:
        return [json.loads(line) for line in f]

def tokenize_and_mask(example: Dict[str, str], tokenizer, max_len: int) -> Dict[str, List[int]]:
    """
    Tokenize prompt+completion and mask the prompt labels so loss is only calculated on completion.
    """
    prompt = example['prompt']
    completion = example['completion']
    
    full_text = prompt + completion
    
    # Tokenize full text
    tokenized_full = tokenizer(
        full_text, 
        max_length=max_len, 
        truncation=True, 
        padding=False, 
        return_tensors=None
    )
    
    # Tokenize prompt only (to find where to mask)
    tokenized_prompt = tokenizer(
        prompt, 
        max_length=max_len, 
        truncation=True, 
        padding=False, 
        return_tensors=None
    )
    
    input_ids = tokenized_full['input_ids']
    labels = list(input_ids) # Copy
    
    # Mask the prompt part
    prompt_len = len(tokenized_prompt['input_ids'])
    
    # Handle case where full text was truncated
    if prompt_len > len(input_ids):
        # This shouldn't happen if max_len is sufficient, but if prompt is huge, 
        # we might be training on nothing.
        prompt_len = len(input_ids)
        
    for i in range(prompt_len):
        labels[i] = IGNORE_INDEX
        
    return {
        "input_ids": input_ids,
        "attention_mask": tokenized_full['attention_mask'],
        "labels": labels
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_path", type=str, required=True, help="Path to sft_train.jsonl")
    parser.add_argument("--base_model", type=str, required=True, help="Base model ID (e.g. Qwen/Qwen2.5-7B-Instruct)")
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch_size", type=int, default=4)
    parser.add_argument("--grad_accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--lora_r", type=int, default=16)
    parser.add_argument("--lora_alpha", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    
    # Set seed
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    
    print(f"Loading data from {args.data_path}")
    raw_data = load_jsonl(args.data_path)
    print(f"Loaded {len(raw_data)} samples.")
    
    # Convert to HF Dataset
    dataset = Dataset.from_list(raw_data)
    
    # Load Tokenizer
    print(f"Loading tokenizer: {args.base_model}")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        
    # Preprocess dataset
    def _map_fn(ex):
        return tokenize_and_mask(ex, tokenizer, MAX_LENGTH)
    
    print("Tokenizing dataset...")
    dataset = dataset.map(_map_fn, remove_columns=dataset.column_names)
    
    # Load Model (4-bit for efficiency)
    print(f"Loading model: {args.base_model}")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16
    )
    
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True
    )
    
    # Prepare for LoRA
    model = prepare_model_for_kbit_training(model)
    
    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    )
    
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()
    
    # Training Arguments
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        fp16=False,
        bf16=True, # Qwen usually prefers bf16
        logging_steps=10,
        save_strategy="epoch",
        report_to="none",
        optim="paged_adamw_32bit"
    )
    
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)
    )
    
    print("Starting training...")
    trainer.train()
    
    print(f"Saving model to {args.output_dir}")
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

if __name__ == "__main__":
    main()

