#!/usr/bin/env python3
"""
Conversation viewer script that formats conversation.json files from different agent perspectives.

Usage:
    python view.py <path-to-conversation.json> --as [system|user|tool]
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


# ANSI color codes
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Text colors
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Background colors
    BG_BLUE = '\033[44m'
    BG_GREEN = '\033[42m'


def parse_sections(output_raw: str) -> Dict[str, Optional[str]]:
    """Parse output_raw to extract reasoning, plan, and action sections."""
    sections = {
        'reasoning': None,
        'plan': None,
        'action': None
    }
    
    if not output_raw:
        return sections
    
    # Extract reasoning
    reasoning_start = output_raw.find('<think>')
    reasoning_end = output_raw.find('</think>')
    if reasoning_start != -1 and reasoning_end != -1:
        sections['reasoning'] = output_raw[reasoning_start + len('<think>'):reasoning_end].strip()
    
    # Extract plan
    plan_start = output_raw.find('<plan>')
    plan_end = output_raw.find('</plan>')
    if plan_start != -1 and plan_end != -1:
        sections['plan'] = output_raw[plan_start + len('<plan>'):plan_end].strip()
    
    # Extract action (everything after plan or reasoning)
    action_start = output_raw.find('<action')
    if action_start != -1:
        action_open_end = output_raw.find('>', action_start)
        if action_open_end != -1:
            action_close = output_raw.find('</action>', action_open_end)
            if action_close != -1:
                sections['action'] = output_raw[action_open_end + 1:action_close].strip()
            else:
                # No closing tag, take rest of text
                sections['action'] = output_raw[action_open_end + 1:].strip()
    
    return sections


def format_tool_call(action_structured: Dict[str, Any]) -> str:
    """Format a tool call with pretty-printed JSON arguments."""
    name = action_structured.get('name', '<unknown>')
    args = action_structured.get('args', {})
    
    if args:
        args_json = json.dumps(args, indent=2, ensure_ascii=False)
        return f"{name}(\n{args_json}\n)"
    else:
        raw = action_structured.get('raw', '')
        if raw:
            return raw
        return f"{name}()"


def format_observation(observation: Optional[Dict[str, Any]]) -> str:
    """Format a tool observation/response."""
    if not observation:
        return ""
    
    # Prefer parsed if available, otherwise raw
    if observation.get('parsed'):
        return json.dumps(observation['parsed'], indent=2, ensure_ascii=False)
    elif observation.get('raw'):
        raw = observation['raw']
        # Try to parse and pretty-print if it's JSON
        try:
            parsed = json.loads(raw)
            return json.dumps(parsed, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            return raw
    return ""


def colorize_xml_tags(text: str, use_colors: bool = True, base_color: str = '') -> str:
    """Colorize XML tags in red while keeping the rest of the text in base_color."""
    if not use_colors:
        return text
    
    # Pattern to match XML tags: <tag> or </tag> or <tag attr="value">
    # This matches <...> where ... can contain attributes
    pattern = r'(<[^>]+>)'
    
    # Split text by tags, keeping the tags in the result
    parts = re.split(pattern, text)
    output_parts = []
    
    # Start with base color if provided
    if base_color:
        output_parts.append(base_color)
    
    for part in parts:
        if re.match(pattern, part):
            # This is a tag, make it red
            output_parts.append(f"{Colors.RED}{part}")
            # Restore base color after tag
            if base_color:
                output_parts.append(base_color)
            else:
                output_parts.append(Colors.RESET)
        else:
            # Regular text, keep as is (already in base_color context)
            output_parts.append(part)
    
    # Close with reset
    output_parts.append(Colors.RESET)
    
    return ''.join(output_parts)


def colorize_xml_tags_markdown(text: str) -> str:
    """Colorize XML tags in markdown using HTML spans."""
    # Pattern to match XML tags
    pattern = r'(<[^>]+>)'
    
    def replace_tag(match):
        tag = match.group(0)
        # Escape HTML special characters in the tag content for safety
        # But keep < and > visible, so we'll escape & and quotes if needed
        escaped_tag = tag.replace('&', '&amp;')
        return f'<span style="color: red;">{escaped_tag}</span>'
    
    return re.sub(pattern, replace_tag, text)


def format_system_perspective(messages: List[Dict[str, Any]], use_colors: bool = True) -> Tuple[str, str]:
    """Format conversation from system perspective (sees everything)."""
    stdout_lines = []
    md_lines = []
    
    for msg in messages:
        turn_id = msg.get('turn_id', '?')
        role = msg.get('role', '')
        
        if role == 'user':
            content = msg.get('output_raw', '')
            
            # Stdout
            if use_colors:
                stdout_lines.append(f"{Colors.BOLD}{Colors.BLUE}=== Turn {turn_id}: User ==={Colors.RESET}")
                stdout_lines.append(f"{Colors.WHITE}{content}{Colors.RESET}\n")
            else:
                stdout_lines.append(f"=== Turn {turn_id}: User ===")
                stdout_lines.append(f"{content}\n")
            
            # Markdown
            md_lines.append(f"## Turn {turn_id}: User\n")
            md_lines.append(f"{content}\n\n")
            
        elif role == 'assistant':
            steps = msg.get('steps', [])
            
            # Stdout
            if use_colors:
                stdout_lines.append(f"{Colors.BOLD}{Colors.GREEN}=== Turn {turn_id}: Assistant ==={Colors.RESET}")
            else:
                stdout_lines.append(f"=== Turn {turn_id}: Assistant ===")
            
            # Markdown
            md_lines.append(f"## Turn {turn_id}: Assistant\n")
            
            for step in steps:
                step_index = step.get('step_index', 0)
                output_raw = step.get('output_raw', '')
                action_structured = step.get('action_structured', {})
                observation = step.get('observation')
                
                # Display raw output with proper formatting (newlines and Unicode already decoded from JSON)
                # Colorize XML tags in red, while keeping role-based color (green for assistant)
                if output_raw:
                    if use_colors:
                        # Use green as base color for assistant output
                        colorized_output = colorize_xml_tags(output_raw, use_colors, base_color=Colors.GREEN)
                        stdout_lines.append(f"{colorized_output}\n")
                    else:
                        stdout_lines.append(f"{output_raw}\n")
                    
                    # For markdown, use HTML spans for colored tags (outside code blocks so HTML renders)
                    md_colorized = colorize_xml_tags_markdown(output_raw)
                    # Escape the content for markdown (convert newlines to <br> or use <pre>)
                    md_lines.append(f"<pre>{md_colorized}</pre>\n\n")
                
                # Observation (tool response) - show separately
                if observation:
                    obs_str = format_observation(observation)
                    if obs_str:
                        if use_colors:
                            stdout_lines.append(f"{Colors.BOLD}{Colors.BLUE}[Observation]{Colors.RESET}")
                            stdout_lines.append(f"{Colors.BLUE}{obs_str}{Colors.RESET}\n")
                        else:
                            stdout_lines.append("[Observation]")
                            stdout_lines.append(f"{obs_str}\n")
                        
                        md_lines.append(f"### Observation\n\n```json\n{obs_str}\n```\n\n")
                
                stdout_lines.append("")  # Empty line between steps
                md_lines.append("---\n\n")
            
            stdout_lines.append("")  # Empty line between turns
            md_lines.append("\n")
    
    return '\n'.join(stdout_lines), '\n'.join(md_lines)


def format_user_perspective(messages: List[Dict[str, Any]], use_colors: bool = True) -> Tuple[str, str]:
    """Format conversation from user perspective (sees user messages + assistant say outputs only)."""
    stdout_lines = []
    md_lines = []
    
    for msg in messages:
        turn_id = msg.get('turn_id', '?')
        role = msg.get('role', '')
        
        if role == 'user':
            content = msg.get('output_raw', '')
            
            # Stdout
            if use_colors:
                stdout_lines.append(f"{Colors.BOLD}{Colors.BLUE}=== Turn {turn_id}: User ==={Colors.RESET}")
                stdout_lines.append(f"{Colors.WHITE}{content}{Colors.RESET}\n")
            else:
                stdout_lines.append(f"=== Turn {turn_id}: User ===")
                stdout_lines.append(f"{content}\n")
            
            # Markdown
            md_lines.append(f"## Turn {turn_id}: User\n")
            md_lines.append(f"{content}\n\n")
            
        elif role == 'assistant':
            steps = msg.get('steps', [])
            
            # Only show steps with "say" actions
            say_texts = []
            for step in steps:
                action_structured = step.get('action_structured', {})
                if action_structured.get('type') == 'say':
                    text = action_structured.get('text', '').strip()
                    if text:
                        say_texts.append(text)
            
            if say_texts:
                # Combine all say texts for this turn
                combined_text = '\n\n'.join(say_texts)
                
                # Stdout
                if use_colors:
                    stdout_lines.append(f"{Colors.BOLD}{Colors.GREEN}=== Turn {turn_id}: Assistant ==={Colors.RESET}")
                    stdout_lines.append(f"{Colors.GREEN}{combined_text}{Colors.RESET}\n")
                else:
                    stdout_lines.append(f"=== Turn {turn_id}: Assistant ===")
                    stdout_lines.append(f"{combined_text}\n")
                
                # Markdown
                md_lines.append(f"## Turn {turn_id}: Assistant\n")
                md_lines.append(f"{combined_text}\n\n")
        
        stdout_lines.append("")  # Empty line between turns
        md_lines.append("\n")
    
    return '\n'.join(stdout_lines), '\n'.join(md_lines)


def format_tool_perspective(messages: List[Dict[str, Any]], use_colors: bool = True) -> Tuple[str, str]:
    """Format conversation from tool perspective (sees tool calls + responses only)."""
    stdout_lines = []
    md_lines = []
    
    tool_call_count = 0
    
    for msg in messages:
        if msg.get('role') != 'assistant':
            continue
        
        steps = msg.get('steps', [])
        turn_id = msg.get('turn_id', '?')
        
        for step in steps:
            action_structured = step.get('action_structured', {})
            observation = step.get('observation')
            
            if action_structured.get('type') == 'tool_call':
                tool_call_count += 1
                tool_call_str = format_tool_call(action_structured)
                
                # Stdout - Tool Call (as input)
                if use_colors:
                    stdout_lines.append(f"{Colors.BOLD}{Colors.MAGENTA}=== Tool Call {tool_call_count} (Turn {turn_id}) ==={Colors.RESET}")
                    stdout_lines.append(f"{Colors.MAGENTA}{tool_call_str}{Colors.RESET}\n")
                else:
                    stdout_lines.append(f"=== Tool Call {tool_call_count} (Turn {turn_id}) ===")
                    stdout_lines.append(f"{tool_call_str}\n")
                
                # Markdown
                md_lines.append(f"## Tool Call {tool_call_count} (Turn {turn_id})\n")
                md_lines.append(f"```\n{tool_call_str}\n```\n\n")
                
                # Tool Response (as output)
                if observation:
                    obs_str = format_observation(observation)
                    if obs_str:
                        if use_colors:
                            stdout_lines.append(f"{Colors.BOLD}{Colors.BLUE}=== Response ==={Colors.RESET}")
                            stdout_lines.append(f"{Colors.BLUE}{obs_str}{Colors.RESET}\n")
                        else:
                            stdout_lines.append("=== Response ===")
                            stdout_lines.append(f"{obs_str}\n")
                        
                        md_lines.append(f"### Response\n\n```json\n{obs_str}\n```\n\n")
                
                stdout_lines.append("")  # Empty line between tool calls
                md_lines.append("---\n\n")
    
    if tool_call_count == 0:
        no_calls_msg = "No tool calls found in this conversation."
        if use_colors:
            stdout_lines.append(f"{Colors.YELLOW}{no_calls_msg}{Colors.RESET}")
        else:
            stdout_lines.append(no_calls_msg)
        md_lines.append(f"*{no_calls_msg}*")
    
    return '\n'.join(stdout_lines), '\n'.join(md_lines)


def load_conversation(path: Path) -> Dict[str, Any]:
    """Load conversation.json file."""
    if not path.exists():
        raise FileNotFoundError(f"Conversation file not found: {path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description='View conversation.json from different agent perspectives',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python view.py conversation.json
  python view.py conversation.json --as user
  python view.py conversation.json --as tool --to-file
        """
    )
    parser.add_argument('conversation_path', type=str, help='Path to conversation.json file')
    parser.add_argument('--as', dest='perspective', choices=['system', 'user', 'tool'], default='system',
                       help='Perspective to view from: system (sees everything), user (sees user + say outputs), tool (sees tool calls + responses). Default: system')
    parser.add_argument('--to-file', action='store_true', help='Write markdown file to disk (default: only print to stdout)')
    parser.add_argument('--no-color', action='store_true', help='Disable ANSI colors in stdout')
    
    args = parser.parse_args()
    
    try:
        # Load conversation
        conv_path = Path(args.conversation_path)
        conversation = load_conversation(conv_path)
        messages = conversation.get('messages', [])
        
        if not messages:
            print("Warning: No messages found in conversation file.", file=sys.stderr)
            return 1
        
        # Format based on perspective
        use_colors = not args.no_color
        
        if args.perspective == 'system':
            stdout_output, md_output = format_system_perspective(messages, use_colors)
        elif args.perspective == 'user':
            stdout_output, md_output = format_user_perspective(messages, use_colors)
        elif args.perspective == 'tool':
            stdout_output, md_output = format_tool_perspective(messages, use_colors)
        
        # Print to stdout
        print(stdout_output)
        
        # Write markdown file
        if args.to_file:
            output_dir = conv_path.parent
            output_file = output_dir / f"conversation_pretty_{args.perspective}.md"
            
            # Add header to markdown
            meta = conversation.get('meta', {})
            conversation_id = meta.get('conversation_id', 'unknown')
            
            md_header = f"# Conversation View: {args.perspective.title()} Perspective\n\n"
            md_header += f"**Conversation ID:** {conversation_id}\n\n"
            md_header += "---\n\n"
            
            full_md = md_header + md_output
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(full_md)
            
            print(f"\nMarkdown file written to: {output_file}", file=sys.stderr)
        
        return 0
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in conversation file: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

