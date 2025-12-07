import json
import argparse
import sys
import os
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Add src to python path
repo_root = Path(__file__).resolve().parent.parent
sys.path.append(str(repo_root / "src"))

from core import Message, MessageRole, convert_messages_to_hf_format, build_hf_prompt
from scenario import resolve_scenario_id, ExampleScenario, extract_scenario_id_from_filename

def load_conversation(file_path: Path) -> Dict[str, Any]:
    with open(file_path, 'r') as f:
        return json.load(f)

def flatten_conversation(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Flatten nested turn structure into linear list of events:
    User -> Assistant Step -> Tool Observation -> Assistant Step -> ...
    """
    flat_events = []
    
    for turn in messages:
        role = turn['role']
        if role == 'user':
            flat_events.append({
                'role': MessageRole.USER,
                'content': turn.get('output_raw', '')
            })
        elif role == 'assistant':
            # Assistant turns have steps
            steps = turn.get('steps', [])
            # If no steps but output_raw exists (legacy/simple), use that
            if not steps and turn.get('output_raw'):
                flat_events.append({
                    'role': MessageRole.ASSISTANT,
                    'content': turn['output_raw']
                })
                continue
                
            for step in steps:
                # Assistant Action (Think + Plan + Action)
                action_content = step.get('output_raw', '')
                flat_events.append({
                    'role': MessageRole.ASSISTANT,
                    'content': action_content
                })
                
                # Tool Observation (if any)
                obs = step.get('observation')
                if obs:
                    obs_content = obs.get('raw', '')
                    # If obs is a dict/list, json dump it
                    if not isinstance(obs_content, str):
                        obs_content = json.dumps(obs_content, indent=2)
                    
                    flat_events.append({
                        'role': MessageRole.TOOL,
                        'content': obs_content
                    })
    
    return flat_events

def extract_metadata(conv_data: Dict[str, Any], tools: Dict[str, Any], scenario_name: str) -> Dict[str, Any]:
    """Extract metadata for analysis."""
    config = conv_data.get('config', {})
    
    # 1. Impossible
    # Check config first, fallback to checking scenario name if known
    is_impossible = config.get('task', {}).get('impossible', False)
    # Also check if it's at the top level of config (some versions)
    if not is_impossible:
        is_impossible = config.get('impossible', False)
        
    # 2. Injected Behaviors
    user_behaviors = []
    ua_config = config.get('user_agent_config', {})
    for b in ua_config.get('injected_behaviors', []):
        if isinstance(b, dict) and 'type_id' in b:
            user_behaviors.append(b['type_id'])
            
    tool_behaviors = []
    ta_config = config.get('tool_agent_config', {})
    for b in ta_config.get('injected_behaviors', []):
        if isinstance(b, dict) and 'type_id' in b:
            tool_behaviors.append(b['type_id'])
            
    # 3. Domain (infer from meta or scenario name)
    domain = conv_data.get('meta', {}).get('domain_id')
    if not domain and '.' in scenario_name:
        domain = scenario_name.split('.')[0]
        
    return {
        "domain": domain,
        "impossible": is_impossible,
        "num_tools": len(tools),
        "user_injected_behaviors": user_behaviors,
        "tool_injected_behaviors": tool_behaviors,
        "scenario_id": scenario_name
    }

def create_samples_from_conversation(
    conv_data: Dict[str, Any], 
    system_prompt: str,
    tools: Dict[str, Any],
    metadata: Dict[str, Any]
) -> List[Dict[str, Any]]:
    
    samples = []
    messages = conv_data.get('messages', [])
    flat_events = flatten_conversation(messages)
    
    history_buffer: List[Message] = []
    
    for i, event in enumerate(flat_events):
        role = event['role']
        content = event['content']
        
        # We only generate samples where the model (Assistant) is supposed to speak
        if role == MessageRole.ASSISTANT:
            # The target output is this assistant message
            target_output = content
            
            # The input context is everything up to this point
            # Convert history buffer to HF format
            dialogue_history = convert_messages_to_hf_format(history_buffer)
            
            # Build full prompt
            prompt = build_hf_prompt(system_prompt, tools, dialogue_history)
            
            # Create sample
            samples.append({
                "prompt": prompt,
                "completion": target_output + "<|endoftext|>", # Explicit stop token for training
                "metadata": metadata
            })
            
            # Add this message to history for next step
            history_buffer.append(Message(role, content))
            
        else:
            # User or Tool message - just add to history
            history_buffer.append(Message(role, content))
            
    return samples

def main():
    parser = argparse.ArgumentParser(description="Prepare SFT dataset from conversation logs")
    parser.add_argument("--input_dir", type=str, default="data/valid_outputs/v2", help="Directory containing conversation JSONs (default: data/valid_outputs/v2)")
    parser.add_argument("--output_dir", type=str, default="training/data", help="Output directory for jsonl files")
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Cache for system prompts
    system_prompts_cache = {}
    
    def get_system_prompt(version: str) -> str:
        if version in system_prompts_cache:
            return system_prompts_cache[version]
        
        # Try to find the prompt file
        prompt_path = Path("prompts/system_agent") / f"{version}.txt"
        if not prompt_path.exists():
            # Fallback to v3 if specific version not found
            print(f"Warning: Prompt file {prompt_path} not found, falling back to v3.txt")
            prompt_path = Path("prompts/system_agent/v3.txt")
            
        with open(prompt_path, 'r') as f:
            content = f.read().strip()
            system_prompts_cache[version] = content
            return content

    input_path = Path(args.input_dir)
    json_files = list(input_path.glob("**/*.json"))
    
    # Pass 1: Scan and collect metadata
    print(f"Scanning {len(json_files)} conversation files in {input_path}...")
    
    scan_results = [] # List of dicts with file info
    
    stats = {
        "processed": 0,
        "failed": 0,
        "train_convs": 0,
        "test_convs": 0,
        "impossible_train": 0,
        "impossible_test": 0
    }
    
    for json_file in json_files:
        try:
            conv_data = load_conversation(json_file)
            
            # Resolve Scenario
            scenario_name = conv_data.get('config', {}).get('scenario_name')
            if not scenario_name:
                extracted = extract_scenario_id_from_filename(json_file.name)
                scenario_name = extracted.split('__')[-1] if extracted else None
                if not scenario_name:
                    print(f"Skipping {json_file.name}: Could not extract scenario ID")
                    stats["failed"] += 1
                    continue
            
            # Load Tools
            try:
                scenario_path = resolve_scenario_id(scenario_name)
                scenario = ExampleScenario.load(scenario_path)
                tools = scenario.tools
            except Exception as e:
                print(f"Warning: Could not resolve scenario '{scenario_name}' for {json_file.name}: {e}")
                stats["failed"] += 1
                continue
                
            # Extract Metadata
            metadata = extract_metadata(conv_data, tools, scenario_name)
            
            scan_results.append({
                "path": json_file,
                "data": conv_data,
                "tools": tools,
                "metadata": metadata,
                "scenario_name": scenario_name
            })
            
        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            stats["failed"] += 1

    # Pass 2: Sort and Split
    # Separate into groups
    impossible_items = [x for x in scan_results if x["metadata"]["impossible"]]
    standard_items = [x for x in scan_results if not x["metadata"]["impossible"]]
    
    # Sort deterministically by filename
    impossible_items.sort(key=lambda x: x["path"].name)
    standard_items.sort(key=lambda x: x["path"].name)
    
    # Assign Splits
    train_items = []
    test_items = []
    
    # Split Impossible: 60% Train, 40% Test
    # If list is small, ensure reasonable distribution.
    # Logic: First 60% -> Train, Rest -> Test
    split_idx_imp = int(len(impossible_items) * 0.6)
    if len(impossible_items) > 0 and split_idx_imp == 0:
        # If e.g. 1 item, put in Train to ensure we learn it? Or Test?
        # User wants "better split", suggesting balance.
        # Let's force at least 1 in Test if we have >= 2 items
        if len(impossible_items) >= 2:
            split_idx_imp = max(1, split_idx_imp)
        else:
            # If only 1, put in Train (default)
            pass
            
    train_items.extend(impossible_items[:split_idx_imp])
    test_items.extend(impossible_items[split_idx_imp:])
    
    stats["impossible_train"] = len(impossible_items[:split_idx_imp])
    stats["impossible_test"] = len(impossible_items[split_idx_imp:])
    
    # Split Standard: 90% Train, 10% Test
    split_idx_std = int(len(standard_items) * 0.9)
    train_items.extend(standard_items[:split_idx_std])
    test_items.extend(standard_items[split_idx_std:])
    
    stats["train_convs"] = len(train_items)
    stats["test_convs"] = len(test_items)
    stats["processed"] = len(scan_results)
    
    # Pass 3: Generate Samples
    train_samples = []
    test_samples = []
    test_scenario_ids = set()
    
    print(f"Generating samples...")
    
    for item in train_items:
        prompt_version = item["data"].get('meta', {}).get('prompt_versions', {}).get('system_agent', 'v3')
        system_prompt = get_system_prompt(prompt_version)
        samples = create_samples_from_conversation(item["data"], system_prompt, item["tools"], item["metadata"])
        train_samples.extend(samples)
        
    for item in test_items:
        prompt_version = item["data"].get('meta', {}).get('prompt_versions', {}).get('system_agent', 'v3')
        system_prompt = get_system_prompt(prompt_version)
        samples = create_samples_from_conversation(item["data"], system_prompt, item["tools"], item["metadata"])
        test_samples.extend(samples)
        test_scenario_ids.add(item["scenario_name"])

    # Save outputs
    train_file = output_dir / "sft_train.jsonl"
    test_file = output_dir / "sft_test.jsonl"
    split_file = output_dir / "test_split.json"
    
    print(f"\nWriting {len(train_samples)} training samples to {train_file}")
    with open(train_file, 'w') as f:
        for sample in train_samples:
            f.write(json.dumps(sample) + "\n")
            
    print(f"Writing {len(test_samples)} test samples to {test_file}")
    with open(test_file, 'w') as f:
        for sample in test_samples:
            f.write(json.dumps(sample) + "\n")
            
    print(f"Writing test split scenario IDs to {split_file}")
    with open(split_file, 'w') as f:
        json.dump(sorted(list(test_scenario_ids)), f, indent=2)
        
    print("\n=== Statistics ===")
    print(f"Total Conversations Processed: {stats['processed']}")
    print(f"Failed Files: {stats['failed']}")
    print(f"Train Conversations: {stats['train_convs']}")
    print(f"Test Conversations:  {stats['test_convs']} ({stats['test_convs'] / (stats['train_convs']+stats['test_convs']) * 100:.1f}%)")
    print(f"Impossible Scenarios Split: {stats['impossible_train']} Train / {stats['impossible_test']} Test")

if __name__ == "__main__":
    main()