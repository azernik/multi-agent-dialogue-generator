import json
import argparse
import sys
import os
from pathlib import Path
from typing import List, Dict, Any

# Add src to python path
repo_root = Path(__file__).resolve().parent.parent
sys.path.append(str(repo_root / "src"))

from core import Message, MessageRole, convert_messages_to_hf_format, build_hf_prompt
from scenario import resolve_scenario_id, ExampleScenario, load_system_prompts

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

def create_samples_from_conversation(
    conv_data: Dict[str, Any], 
    system_prompt: str,
    tools: Dict[str, Any]
) -> List[Dict[str, str]]:
    
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
                "completion": target_output + "<|endoftext|>" # Explicit stop token for training
            })
            
            # Add this message to history for next step
            history_buffer.append(Message(role, content))
            
        else:
            # User or Tool message - just add to history
            history_buffer.append(Message(role, content))
            
    return samples

def main():
    parser = argparse.ArgumentParser(description="Prepare SFT dataset from conversation logs")
    parser.add_argument("--input_dir", type=str, required=True, help="Directory containing conversation JSONs")
    parser.add_argument("--output_file", type=str, required=True, help="Output JSONL file")
    parser.add_argument("--system_prompt_path", type=str, default="prompts/system_agent/v3.txt", help="Path to system prompt")
    args = parser.parse_args()
    
    # Load system prompt template
    with open(args.system_prompt_path, 'r') as f:
        base_system_prompt = f.read().strip()
        
    input_path = Path(args.input_dir)
    json_files = list(input_path.glob("**/*.json"))
    
    all_samples = []
    success_count = 0
    fail_count = 0
    
    print(f"Found {len(json_files)} conversation files.")
    
    for json_file in json_files:
        try:
            conv_data = load_conversation(json_file)
            
            # 1. Resolve Scenario and Tools
            scenario_name = conv_data.get('config', {}).get('scenario_name')
            # Fallback to filename parsing if config missing
            if not scenario_name:
                # filename format: 20251206_...__scenario_id__persona.json
                # or just scenario_id__persona.json
                parts = json_file.name.split('__')
                if len(parts) >= 2:
                    scenario_name = parts[-2] # Assumes ...__scenario__persona.json
                else:
                    print(f"Skipping {json_file.name}: Could not deduce scenario name")
                    fail_count += 1
                    continue
            
            # Find the scenario file to load tools
            try:
                scenario_path = resolve_scenario_id(scenario_name)
                scenario = ExampleScenario.from_file(scenario_path)
                tools = scenario.tools
            except Exception as e:
                print(f"Warning: Could not resolve scenario '{scenario_name}' for {json_file.name}: {e}")
                # Fallback: empty tools? Or skip? Better to skip to ensure quality.
                # Actually, check if toolset_id is available in meta?
                # For now, skip if we can't find tools
                fail_count += 1
                continue
                
            # 2. Generate Samples
            file_samples = create_samples_from_conversation(conv_data, base_system_prompt, tools)
            all_samples.extend(file_samples)
            success_count += 1
            
        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            fail_count += 1
            
    # Save to JSONL
    print(f"Generated {len(all_samples)} samples from {success_count} conversations ({fail_count} failed).")
    with open(args.output_file, 'w') as f:
        for sample in all_samples:
            f.write(json.dumps(sample) + "\n")
            
    print(f"Saved dataset to {args.output_file}")

if __name__ == "__main__":
    main()

