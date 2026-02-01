#!/usr/bin/env python3
"""
Script to summarize conversations from valid_outputs/v2 into a single JSON file.

For each conversation, extracts:
- domain
- conversation_id
- use_case
- scenario_type (normal | behavior | impossible)
- behavior_types (list of behavior type_ids)
- tool_sequence (list of tool names called in order)
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional


def extract_tool_sequence(messages: List[Dict[str, Any]]) -> List[str]:
    """Extract the sequence of tool calls from conversation messages."""
    tool_sequence = []
    
    for message in messages:
        if message.get('role') == 'assistant':
            steps = message.get('steps', [])
            for step in steps:
                action_structured = step.get('action_structured', {})
                if action_structured.get('type') == 'tool_call':
                    tool_name = action_structured.get('name')
                    if tool_name:
                        tool_sequence.append(tool_name)
    
    return tool_sequence


def determine_scenario_type(config: Dict[str, Any]) -> str:
    """Determine scenario type: impossible, behavior, or normal."""
    task = config.get('task', {})
    
    # Check if impossible
    if task.get('impossible', False):
        return 'impossible'
    
    # Check if has behaviors
    user_behaviors = config.get('user_agent_config', {}).get('injected_behaviors', [])
    tool_behaviors = config.get('tool_agent_config', {}).get('injected_behaviors', [])
    
    if user_behaviors or tool_behaviors:
        return 'behavior'
    
    return 'normal'


def extract_behavior_types(config: Dict[str, Any]) -> List[str]:
    """Extract all behavior type_ids from user and tool agent configs."""
    behavior_types = []
    
    # Extract from user agent behaviors
    user_behaviors = config.get('user_agent_config', {}).get('injected_behaviors', [])
    for behavior in user_behaviors:
        if isinstance(behavior, dict) and 'type_id' in behavior:
            behavior_types.append(behavior['type_id'])
    
    # Extract from tool agent behaviors
    tool_behaviors = config.get('tool_agent_config', {}).get('injected_behaviors', [])
    for behavior in tool_behaviors:
        if isinstance(behavior, dict) and 'type_id' in behavior:
            behavior_types.append(behavior['type_id'])
    
    return behavior_types


def extract_use_case(config: Dict[str, Any], conversation_id: str) -> Optional[str]:
    """Extract use_case from scenario_name or conversation_id.
    
    Scenario name format: {domain}_{use_case}_{pattern_id}
    e.g., 'os_co_001' -> use_case is 'co'
    """
    # Try to get from scenario_name first
    scenario_name = config.get('scenario_name', '')
    if scenario_name:
        # Parse scenario_name format: {domain}_{use_case}_{pattern_id}
        parts = scenario_name.split('_')
        if len(parts) >= 2:
            return parts[1]  # use_case is the second part
    
    # Fallback: try to extract from conversation_id
    # Format: {domain}.{scenario_id} or just {scenario_id}
    if '.' in conversation_id:
        scenario_id = conversation_id.split('.', 1)[1]
    else:
        scenario_id = conversation_id
    
    parts = scenario_id.split('_')
    if len(parts) >= 2:
        return parts[1]
    
    return None


def summarize_conversation(conv_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Summarize a single conversation file."""
    try:
        meta = conv_data.get('meta', {})
        config = conv_data.get('config', {})
        messages = conv_data.get('messages', [])
        
        # Extract domain
        domain = meta.get('domain_id')
        if not domain:
            # Try to infer from conversation_id
            conversation_id = meta.get('conversation_id', '')
            if '.' in conversation_id:
                domain = conversation_id.split('.')[0]
        
        if not domain:
            print(f"Warning: Could not determine domain for conversation {meta.get('conversation_id', 'unknown')}", file=sys.stderr)
            return None
        
        # Extract conversation_id
        conversation_id = meta.get('conversation_id', 'unknown')
        
        # Extract use_case
        use_case = extract_use_case(config, conversation_id)
        
        # Determine scenario type
        scenario_type = determine_scenario_type(config)
        
        # Extract behavior types
        behavior_types = extract_behavior_types(config)
        
        # Extract tool sequence
        tool_sequence = extract_tool_sequence(messages)
        
        return {
            'domain': domain,
            'conversation_id': conversation_id,
            'use_case': use_case,
            'scenario_type': scenario_type,
            'behavior_types': behavior_types,
            'tool_sequence': tool_sequence
        }
    except Exception as e:
        print(f"Error processing conversation: {e}", file=sys.stderr)
        return None


def process_all_conversations(valid_outputs_dir: Path, output_file: Path, domain_filter: Optional[str] = None):
    """Process all conversation files in valid_outputs/v2 and generate summary."""
    summaries = []
    
    # Find all JSON files
    json_files = list(valid_outputs_dir.glob('*.json'))
    
    print(f"Found {len(json_files)} conversation files", file=sys.stderr)
    
    for json_file in sorted(json_files):
        try:
            with open(json_file, 'r') as f:
                conv_data = json.load(f)
            
            summary = summarize_conversation(conv_data)
            
            if summary:
                # Apply domain filter if specified
                if domain_filter and summary['domain'] != domain_filter:
                    continue
                
                summaries.append(summary)
        except Exception as e:
            print(f"Error reading {json_file}: {e}", file=sys.stderr)
            continue
    
    # Write summary file
    with open(output_file, 'w') as f:
        json.dump(summaries, f, indent=2)
    
    print(f"Generated summary with {len(summaries)} conversations", file=sys.stderr)
    print(f"Output written to: {output_file}", file=sys.stderr)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Summarize conversations from valid_outputs/v2')
    parser.add_argument(
        '--input-dir',
        type=str,
        default='data/valid_outputs/v2',
        help='Directory containing conversation JSON files (default: data/valid_outputs/v2)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='conversation_summary.json',
        help='Output JSON file path (default: conversation_summary.json)'
    )
    parser.add_argument(
        '--domain',
        type=str,
        default=None,
        help='Filter by domain (e.g., online_shopping). If not specified, processes all domains.'
    )
    
    args = parser.parse_args()
    
    input_dir = Path(args.input_dir)
    output_file = Path(args.output)
    
    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}", file=sys.stderr)
        sys.exit(1)
    
    process_all_conversations(input_dir, output_file, domain_filter=args.domain)


if __name__ == '__main__':
    main()

