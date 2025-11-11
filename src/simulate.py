import argparse
import json
import os
import sys
import logging
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Tuple, Dict, List, Optional, Any
from dotenv import load_dotenv

from core import LLMClient, ConversationContext
from agents import SystemAgent, UserAgent, ToolAgent
from scenario import ExampleScenario, load_system_prompts
from runner import ConversationRunner, ConversationResult

_PERSONA_CATALOG_CACHE: Dict[str, Dict[str, Any]] = {}


def _load_persona_from_catalog(catalog_path: Path, persona_id: str) -> Dict[str, Any]:
    catalog_key = str(catalog_path.resolve())
    catalog_data = _PERSONA_CATALOG_CACHE.get(catalog_key)
    if catalog_data is None:
        if not catalog_path.exists():
            raise FileNotFoundError(f"Persona catalog not found: {catalog_path}")
        catalog_data = json.loads(catalog_path.read_text())
        _PERSONA_CATALOG_CACHE[catalog_key] = catalog_data
    personas = catalog_data.get('personas') or []
    for persona in personas:
        if persona.get('id') == persona_id:
            return persona
    raise ValueError(f"Persona id '{persona_id}' not found in catalog {catalog_path}")


def _merge_task_slots(base_task: Dict[str, Any], slot_overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    task_copy = deepcopy(base_task) if base_task else {}
    if slot_overrides:
        existing_slots = deepcopy(task_copy.get('slots', {})) if task_copy.get('slots') else {}
        existing_slots.update(slot_overrides)
        task_copy['slots'] = existing_slots
    return task_copy


def _prepare_persona_context(
    scenario: ExampleScenario,
    persona_arg: Optional[str],
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    task_override = deepcopy(scenario.task) if scenario.task else {}
    persona_context: Optional[Dict[str, Any]] = None
    persona_id: Optional[str] = None

    if scenario.persona_catalog and scenario.persona_entries:
        persona_id = persona_arg or next((entry.get('id') for entry in scenario.persona_entries if entry.get('id')), None)
        if not persona_id:
            raise ValueError("Persona entries configured but no valid id provided")
        matching_entry = next((entry for entry in scenario.persona_entries if entry.get('id') == persona_id), None)
        if matching_entry is None:
            raise ValueError(f"Persona id '{persona_id}' not listed in scenario personas")

        catalog_path = Path(scenario.persona_catalog)
        if not catalog_path.is_absolute():
            repo_root = Path(__file__).resolve().parent.parent
            catalog_path = (repo_root / catalog_path).resolve()

        base_persona = _load_persona_from_catalog(catalog_path, persona_id)
        persona_context = dict(base_persona)
        persona_context['id'] = persona_id

        slot_overrides = matching_entry.get('slot_overrides') if isinstance(matching_entry, dict) else None
        task_override = _merge_task_slots(task_override, slot_overrides)
        if slot_overrides:
            persona_context['slot_overrides'] = slot_overrides
    elif persona_arg:
        raise ValueError("Persona id provided but scenario has no personas configured")

    return persona_context, task_override, persona_id

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Run multi-agent conversation simulation')
    parser.add_argument('example_path', help='Path to scenario directory (e.g., data/domains/restaurant_booking/dine_in/rb_001)')
    parser.add_argument('--model', default='gpt-4o-mini', help='LLM model to use')
    parser.add_argument('--max-turns', type=int, default=20, help='Maximum conversation turns')
    parser.add_argument('--api-key', help='OpenAI API key (default: OPENAI_API_KEY env var)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose console output')
    parser.add_argument('--system-prompts-dir', help='Path to system prompts directory (default: prompts)')
    parser.add_argument('--system-agent-prompt', help='Path to system agent prompt file')
    parser.add_argument('--user-agent-prompt', help='Path to user agent prompt file') 
    parser.add_argument('--tool-agent-prompt', help='Path to tool agent prompt file')
    parser.add_argument('--prompt-version', default='v1', help='Version of prompts to use (default: v1)')
    parser.add_argument('--debug-transcripts', action='store_true', help='Write system.md/user.md/tool.md and agent_flow.log')
    parser.add_argument('--export-steps-jsonl', action='store_true', help='Write turns.jsonl (one JSONL record per system turn)')
    parser.add_argument('--outputs-root', help='Root directory for outputs (default: env MADG_OUTPUT_ROOT or data/outputs)')
    parser.add_argument('--persona-id', help='Persona ID to use when scenario defines personas')
    return parser.parse_args()

def _resolve_outputs_root(example_path: str, cli_outputs_root: str | None) -> Path:
    """Resolve outputs root directory with CLI > env > default precedence."""
    # 1) CLI flag
    if cli_outputs_root:
        return Path(cli_outputs_root)
    # 2) Environment variable
    env_root = os.getenv('MADG_OUTPUT_ROOT')
    if env_root:
        return Path(env_root)
    # 3) Default to repo-root/data/outputs
    cwd = Path(__file__).resolve().parent.parent  # src/ -> repo root
    return cwd / 'data' / 'outputs'

def _relative_scenario_path(example_dir: Path) -> Path:
    """Compute scenario-relative path under data/scenarios or data/examples if present.
    Falls back to just the leaf directory name.
    """
    parts = example_dir.resolve().parts
    rel = None
    if 'domains' in parts:
        idx = parts.index('domains')
        rel = Path(*parts[idx+1:]) if idx + 1 < len(parts) else None
    elif 'scenarios' in parts:
        idx = parts.index('scenarios')
        rel = Path(*parts[idx+1:]) if idx + 1 < len(parts) else None
    elif 'examples' in parts:
        idx = parts.index('examples')
        rel = Path(*parts[idx+1:]) if idx + 1 < len(parts) else None
    return rel if rel and str(rel) else Path(example_dir.name)

def _scenario_key(example_dir: Path) -> str:
    """Canonical scenario key: domain.use_case.scenario_id derived from data/domains path."""
    parts = example_dir.resolve().parts
    if 'domains' in parts:
        idx = parts.index('domains')
        tail = [p for p in parts[idx+1:]]
        if len(tail) >= 3:
            domain, use_case, scenario_id = tail[0], tail[1], tail[2]
            return f"{domain}.{use_case}.{scenario_id}"
    # fallback: join remaining parts with dots
    return '.'.join([example_dir.parent.name, example_dir.name])

def _sanitize_persona_id(persona_id: Optional[str]) -> Optional[str]:
    if not persona_id:
        return None
    slug = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '-' for ch in persona_id)
    slug = slug.strip('-_')
    return slug or None


def setup_logging(
    example_path: str,
    outputs_root: Path,
    verbose: bool = False,
    persona_id: Optional[str] = None,
) -> Tuple[str, str, str, Path, str]:
    """Set up logging and return output paths.
    Returns: output_file, log_file, agent_flow_file, run_dir, run_id
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    example_dir = Path(example_path)
    persona_slug = _sanitize_persona_id(persona_id)
    if persona_slug:
        run_id = f"simulate_{persona_slug}_{timestamp}"
    else:
        run_id = f"simulate_{timestamp}"

    # Compute centralized outputs path mirroring scenario hierarchy
    scenario_key = _scenario_key(example_dir)
    run_dir = outputs_root / f"{scenario_key}__{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = run_dir / "simulate.log"
    output_file = run_dir / "simulate.out"
    agent_flow_file = run_dir / "agent_flow.log"
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stderr) if verbose else logging.NullHandler()
        ]
    )
    
    return str(output_file), str(log_file), str(agent_flow_file), run_dir, run_id


def _resolve_prompts_dir(example_path: str) -> Path:
    """Resolve the prompts directory robustly when a custom dir is not provided."""
    # Prefer repo-root/prompts if present; fallback to legacy data/system_prompts
    cwd = Path(__file__).resolve().parent.parent  # src/ -> repo root
    candidate_new = cwd / 'prompts'
    if candidate_new.exists():
        return candidate_new
    candidate_old = cwd / 'data' / 'system_prompts'
    if candidate_old.exists():
        return candidate_old
    # Else, walk up from the example path to find siblings
    cur = Path(example_path).resolve()
    for parent in [cur] + list(cur.parents):
        sibling_new = parent.parent / 'prompts'
        if sibling_new.exists():
            return sibling_new
        sibling_old = parent.parent / 'data' / 'system_prompts'
        if sibling_old.exists():
            return sibling_old
    # Fallback to new default
    return Path('prompts')


def load_scenario_and_prompts(example_path: str, args: argparse.Namespace) -> Tuple[ExampleScenario, Dict[str, str]]:
    """Load scenario and system prompts"""
    try:
        # Load scenario from example_path
        scenario = ExampleScenario.load(example_path)
        
        # Load system prompts
        if args.system_agent_prompt or args.user_agent_prompt or args.tool_agent_prompt:
            # Load individual prompt files if specified
            system_prompts = {}
            custom_prompts = {
                'system_agent': args.system_agent_prompt,
                'user_agent': args.user_agent_prompt,
                'tool_agent': args.tool_agent_prompt
            }
            
            for agent_type, custom_path in custom_prompts.items():
                if custom_path:
                    # Use custom path
                    with open(custom_path, 'r') as f:
                        system_prompts[agent_type] = f.read().strip()
                else:
                    # Fall back to default location
                    prompts_dir = Path(args.system_prompts_dir) if args.system_prompts_dir else _resolve_prompts_dir(example_path)
                    prompt_file = prompts_dir / agent_type / f"{args.prompt_version}.txt"
                    with open(prompt_file, 'r') as f:
                        system_prompts[agent_type] = f.read().strip()
        else:
            # Use directory-based loading
            prompts_dir = Path(args.system_prompts_dir) if args.system_prompts_dir else _resolve_prompts_dir(example_path)
            system_prompts = load_system_prompts(str(prompts_dir), args.prompt_version)
        
        return scenario, system_prompts
        
    except FileNotFoundError as e:
        print(f"Error: Could not find required files: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading scenario: {e}", file=sys.stderr)
        sys.exit(1)

def create_agents(scenario: ExampleScenario, 
                 system_prompts: Dict[str, str], 
                 llm_client: LLMClient,
                 flow_logger=None) -> Tuple[SystemAgent, UserAgent, ToolAgent]:
    """Create the three agents with appropriate configurations"""
    try:
        # Create SystemAgent with raw tools JSON
        system_agent = SystemAgent(
            system_prompts['system_agent'],
            llm_client,
            scenario.tools
        )
        system_agent.flow_logger = flow_logger
        
        # Create UserAgent with new user_agent JSON
        user_agent = UserAgent(
            system_prompts['user_agent'],
            llm_client,
            scenario.user_agent
        )
        user_agent.flow_logger = flow_logger
        
        # Create ToolAgent with raw tools JSON
        tool_agent = ToolAgent(
            system_prompts['tool_agent'],
            llm_client,
            scenario.tools
        )
        tool_agent.flow_logger = flow_logger
        
        return system_agent, user_agent, tool_agent
        
    except Exception as e:
        print(f"Error creating agents: {e}", file=sys.stderr)
        sys.exit(1)


def attach_prompt_recorders(
    system_agent: SystemAgent,
    user_agent: UserAgent,
    tool_agent: ToolAgent,
    prompt_captures: Dict[str, Dict[str, Any]],
) -> None:
    """Attach prompt recorder callbacks to each agent to capture prompts."""

    def make_recorder(key: str):
        def recorder(agent_name: str, messages: List[Dict[str, Any]], context: ConversationContext):
            if prompt_captures.get(key) is not None:
                return
            prompt_captures[key] = {
                "agent": agent_name,
                "turn_number": context.turn_number,
                "messages": messages,
            }

        return recorder

    system_agent.prompt_recorder = make_recorder("system_agent")
    user_agent.prompt_recorder = make_recorder("user_agent")
    tool_agent.prompt_recorder = make_recorder("tool_agent")


def write_agent_prompts(
    prompt_captures: Dict[str, Optional[Dict[str, Any]]],
    output_dir: Path,
) -> None:
    """Persist captured prompts for all agents to agent_prompts.json."""
    serialized = {
        agent_key: {
            "agent": entry.get("agent"),
            "turn_number": entry.get("turn_number"),
            "messages": entry.get("messages"),
        }
        for agent_key, entry in prompt_captures.items()
        if entry is not None
    }
    output_path = output_dir / "agent_prompts.json"
    with output_path.open("w") as f:
        json.dump(serialized, f, indent=2)

def format_output(result: ConversationResult, verbose: bool = False) -> Dict:
    """Format conversation result for output"""
    output_data = {
        'scenario': result.metadata.get('scenario', 'unknown'),
        'success': result.success,
        'termination_reason': result.termination_reason,
        'total_turns': result.metadata.get('total_turns', 0),
        'system_transcript': [
            {
                'role': msg.role.value,
                'content': msg.content,
                **({'metadata': msg.metadata} if getattr(msg, 'metadata', None) else {})
            }
            for msg in result.system_transcript
        ],
        'user_transcript': [
            {
                'role': msg.role.value,
                'content': msg.content,
                **({'metadata': msg.metadata} if getattr(msg, 'metadata', None) else {})
            }
            for msg in result.user_transcript
        ],
        'tool_transcript': [
            {
                'role': msg.role.value,
                'content': msg.content,
                **({'metadata': msg.metadata} if getattr(msg, 'metadata', None) else {})
            }
            for msg in result.tool_transcript
        ],
        'metadata': result.metadata
    }
    
    if verbose:
        output_data['summary'] = {
            'system_message_count': len(result.system_transcript),
            'user_message_count': len(result.user_transcript),
            'tool_message_count': len(result.tool_transcript),
            'had_tool_calls': result.metadata.get('had_tool_calls', False),
        }
    
    return output_data

def print_verbose_summary(result: ConversationResult):
    """Print human-readable summary if verbose mode"""
    print(f"\n=== Conversation Summary ===", file=sys.stderr)
    print(f"Scenario: {result.metadata.get('scenario', 'unknown')}", file=sys.stderr)
    print(f"Success: {result.success}", file=sys.stderr)
    print(f"Termination: {result.termination_reason}", file=sys.stderr)
    print(f"Total turns: {result.metadata.get('total_turns', 0)}", file=sys.stderr)
    print(f"System messages: {len(result.system_transcript)}", file=sys.stderr)
    print(f"User messages: {len(result.user_transcript)}", file=sys.stderr)
    print(f"Tool messages: {len(result.tool_transcript)}", file=sys.stderr)
    print(f"Had tool calls: {result.metadata.get('had_tool_calls', False)}", file=sys.stderr)
        
    print("=" * 30, file=sys.stderr)

def format_transcript_as_markdown(transcript: List, transcript_name: str, scenario_name: str) -> str:
    """Format a transcript as readable markdown"""
    markdown = f"# {transcript_name}\n\n"
    markdown += f"**Scenario:** {scenario_name}\n\n"
    markdown += f"**Messages:** {len(transcript)}\n\n"
    markdown += "---\n\n"

    # Special grouped rendering for System Transcript
    if transcript_name == "System Transcript":
        # Group messages by turn_id in encountered order
        turns: List[Dict[str, List[Dict]]]= []
        turn_index: Dict[int, int] = {}

        for msg in transcript:
            meta = msg.get('metadata') or {}
            t_id = meta.get('turn_id')
            if t_id is None:
                # Skip messages without turn metadata
                continue
            if t_id not in turn_index:
                turn_index[t_id] = len(turns)
                turns.append({"turn_id": t_id, "messages": []})
            turns[turn_index[t_id]]["messages"].append(msg)

        def _escape_inline(text: str) -> str:
            return text.replace('*', '\\*').replace('_', '\\_').replace('#', '\\#')

        def _render_assistant_sections(content: str) -> str:
            out = ""
            think_start = content.find('<think>')
            think_end = content.find('</think>')
            plan_start = content.find('<plan>')
            plan_end = content.find('</plan>')
            think_text = ''
            plan_text = ''
            action_section = content
            if think_start != -1 and think_end != -1 and think_end > think_start:
                think_text = content[think_start + len('<think>'):think_end].strip()
            if plan_start != -1 and plan_end != -1 and plan_end > plan_start:
                plan_text = content[plan_start + len('<plan>'):plan_end].strip()
                action_section = content[plan_end + len('</plan>'):].strip()
            else:
                if think_end != -1:
                    action_section = content[think_end + len('</think>'):].strip()
            if think_text:
                out += "&lt;think&gt;\n" + _escape_inline(think_text) + "\n&lt;/think&gt;\n\n"
            if plan_text:
                out += "&lt;plan&gt;\n" + _escape_inline(plan_text) + "\n&lt;/plan&gt;\n\n"
            # Parse <action ...> tag (current format)
            def _parse_action_tag(text: str) -> Dict[str, Any]:
                result: Dict[str, Any] = {}
                if not text:
                    return result
                start = text.find('<action')
                if start == -1:
                    return result
                open_end = text.find('>', start)
                if open_end == -1:
                    return result
                header = text[start + len('<action'):open_end]
                a_type = None
                if 'type="tool"' in header:
                    a_type = 'tool'
                elif 'type="say"' in header:
                    a_type = 'say'
                name_val = None
                npos = header.find('name="')
                if npos != -1:
                    nend = header.find('"', npos + 6)
                    if nend != -1:
                        name_val = header[npos + 6:nend]
                end_tag = '</action>'
                close = text.find(end_tag, open_end + 1)
                if close != -1:
                    body = text[open_end + 1:close].strip()
                else:
                    body = text[open_end + 1:].strip()
                result['type'] = a_type
                if name_val:
                    result['name'] = name_val
                result['body'] = body
                if a_type == 'tool':
                    try:
                        result['args'] = json.loads(body)
                    except Exception:
                        result['args'] = None
                return result

            parsed = _parse_action_tag(action_section)
            if parsed.get('type'):
                out += "### Action\n\n"
                if parsed['type'] == 'say':
                    out += _escape_inline(parsed.get('body', '')) + "\n\n"
                elif parsed['type'] == 'tool':
                    name = parsed.get('name') or 'tool'
                    args_obj = parsed.get('args')
                    if isinstance(args_obj, dict):
                        out += f"`{name}({json.dumps(args_obj, separators=(',', ':'))})`\n\n"
                    else:
                        out += f"`{name}(...)`\n\n"
            return out

        # Render each turn
        for ti, t in enumerate(turns):
            t_id = t["turn_id"]
            msgs = t["messages"]
            # User header and content
            user_msg = next((m for m in msgs if m['role'] == 'user'), None)
            if user_msg:
                markdown += f"## 👤 User (Turn {t_id})\n\n"
                markdown += _escape_inline(user_msg.get('content', '').strip()) + "\n\n"
            # Assistant block with steps
            markdown += f"## 🤖 Assistant (Turn {t_id})\n\n"
            # Collect steps by micro_step_index
            step_to_msgs: Dict[int, Dict[str, Dict]] = {}
            for m in msgs:
                if m['role'] not in ('assistant', 'tool'):
                    continue
                meta = m.get('metadata') or {}
                step = meta.get('micro_step_index')
                if isinstance(step, int):
                    step_to_msgs.setdefault(step, {})[m['role']] = m
            for step in sorted(step_to_msgs.keys()):
                display_step = step + 1
                markdown += f"### Turn {t_id}.{display_step}\n\n"
                amsg = step_to_msgs[step].get('assistant')
                if amsg:
                    markdown += _render_assistant_sections(amsg.get('content', ''))
                tmsg = step_to_msgs[step].get('tool')
                if tmsg:
                    markdown += "#### Observation\n\n"
                    markdown += "```\n" + tmsg.get('content', '').strip() + "\n```\n\n"
            if ti < len(turns) - 1:
                markdown += "---\n\n"

        return markdown
    
    for i, msg in enumerate(transcript, 1):
        role = msg['role']
        content = msg['content']
        meta = msg.get('metadata') or {}
        turn_id = meta.get('turn_id')
        step = meta.get('micro_step_index')
        display_step = (step + 1) if isinstance(step, int) else step
        
        # Format role as header
        if role == 'user':
            markdown += f"## 👤 User (Turn {turn_id})\n\n"
        elif role == 'assistant':
            markdown += f"## 🤖 Assistant (Turn {turn_id}, Step {display_step})\n\n"
        elif role == 'tool':
            markdown += f"## 🔧 Tool (Turn {turn_id}, Step {display_step})\n\n"
        else:
            markdown += f"## 🔧 {role.title()} (Turn {turn_id})\n\n"
        
        # Format content by role with subheaders
        if not content.strip():
            markdown += "*[Empty message]*\n\n"
        else:
            if role == 'assistant':
                think_start = content.find('<think>')
                think_end = content.find('</think>')
                plan_start = content.find('<plan>')
                plan_end = content.find('</plan>')
                # Extract sections safely
                think_text = ''
                plan_text = ''
                action_section = content
                if think_start != -1 and think_end != -1 and think_end > think_start:
                    think_text = content[think_start + len('<think>'):think_end].strip()
                if plan_start != -1 and plan_end != -1 and plan_end > plan_start:
                    plan_text = content[plan_start + len('<plan>'):plan_end].strip()
                    action_section = content[plan_end + len('</plan>'):].strip()
                else:
                    # If no plan, try after </think>
                    if think_end != -1:
                        action_section = content[think_end + len('</think>'):].strip()

                # THINK
                if think_text:
                    markdown += f"### Think\n\n"
                    # Escape basic markdown chars in text sections
                    escaped = think_text.replace('*', '\\*').replace('_', '\\_').replace('#', '\\#')
                    markdown += escaped + "\n\n"

                # PLAN (optional)
                if plan_text:
                    markdown += f"### Plan\n\n"
                    escaped = plan_text.replace('*', '\\*').replace('_', '\\_').replace('#', '\\#')
                    markdown += escaped + "\n\n"

                # ACTION (parse <action> tag from current format)
                def _parse_action_tag2(text: str) -> Dict[str, Any]:
                    result: Dict[str, Any] = {}
                    if not text:
                        return result
                    start = text.find('<action')
                    if start == -1:
                        return result
                    open_end = text.find('>', start)
                    if open_end == -1:
                        return result
                    header = text[start + len('<action'):open_end]
                    a_type = None
                    if 'type="tool"' in header:
                        a_type = 'tool'
                    elif 'type="say"' in header:
                        a_type = 'say'
                    name_val = None
                    npos = header.find('name="')
                    if npos != -1:
                        nend = header.find('"', npos + 6)
                        if nend != -1:
                            name_val = header[npos + 6:nend]
                    end_tag = '</action>'
                    close = text.find(end_tag, open_end + 1)
                    if close != -1:
                        body = text[open_end + 1:close].strip()
                    else:
                        body = text[open_end + 1:].strip()
                    result['type'] = a_type
                    if name_val:
                        result['name'] = name_val
                    result['body'] = body
                    if a_type == 'tool':
                        try:
                            result['args'] = json.loads(body)
                        except Exception:
                            result['args'] = None
                    return result

                parsed = _parse_action_tag2(action_section)
                if parsed.get('type'):
                    markdown += f"### Action\n\n"
                    if parsed['type'] == 'say':
                        escaped = parsed.get('body', '').replace('*', '\\*').replace('_', '\\_').replace('#', '\\#')
                        markdown += escaped + "\n\n"
                    else:
                        name = parsed.get('name') or 'tool'
                        args_obj = parsed.get('args')
                        if isinstance(args_obj, dict):
                            markdown += f"`{name}({json.dumps(args_obj, separators=(',', ':'))})`\n\n"
                        else:
                            markdown += f"`{name}(...)`\n\n"
            elif role == 'tool':
                markdown += f"### Observation\n\n"
                # Prefer code fence for tool JSON/text
                markdown += "```\n" + content.strip() + "\n```\n\n"
            else:
                # User or other roles: render as plain text
                escaped = content.replace('*', '\\*').replace('_', '\\_').replace('#', '\\#')
                markdown += escaped + "\n\n"
        
        # Add separator between messages
        if i < len(transcript):
            markdown += "---\n\n"
    
    return markdown

def write_markdown_transcripts(result: ConversationResult, base_filename: str) -> Dict[str, str]:
    """Write all transcripts as markdown files and return the file paths"""
    base_path = Path(base_filename)
    output_dir = base_path.parent
    
    markdown_files = {}
    
    # Define transcript types and their data
    transcripts = [
        ("System Transcript", result.system_transcript, "system"),
        ("User Transcript", result.user_transcript, "user"), 
        ("Tool Transcript", result.tool_transcript, "tool")
    ]
    
    for transcript_name, transcript_data, file_suffix in transcripts:
        # Convert transcript data to the format expected by format_transcript_as_markdown
        formatted_data = [
            {
                'role': msg.role.value,
                'content': msg.content,
                'metadata': getattr(msg, 'metadata', None)
            }
            for msg in transcript_data
        ]
        
        # Generate markdown content
        markdown_content = format_transcript_as_markdown(
            formatted_data, 
            transcript_name, 
            result.metadata.get('scenario', 'unknown')
        )
        
        # Create filename with simple name
        markdown_file = output_dir / f"{file_suffix}.md"
        
        # Write markdown file
        with open(markdown_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        markdown_files[file_suffix] = str(markdown_file)
    
    return markdown_files

def write_system_markdown_transcript(result: ConversationResult, output_dir: Path) -> str:
    """Write only the system transcript to system.md and return its path."""
    formatted_data = [
        {
            'role': msg.role.value,
            'content': msg.content,
            'metadata': getattr(msg, 'metadata', None)
        }
        for msg in result.system_transcript
    ]
    markdown_content = format_transcript_as_markdown(
        formatted_data,
        "System Transcript",
        result.metadata.get('scenario', 'unknown')
    )
    md_path = output_dir / 'system.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    return str(md_path)

def write_conversation_log(result: ConversationResult, output_dir: Path) -> str:
    """Write a simple conversational log with user-facing messages only."""
    log_path = output_dir / 'conversation.log'
    with open(log_path, 'w', encoding='utf-8') as f:
        for msg in result.user_transcript:
            role = msg.role.value
            # Normalize role names
            prefix = 'User' if role == 'user' else 'Assistant' if role == 'assistant' else role.title()
            f.write(f"{prefix}: {msg.content}\n\n")
    return str(log_path)

def _infer_domain_id(example_path: str) -> Optional[str]:
    """Infer domain id from an example path like data/scenarios/<domain>/..."""
    try:
        p = Path(example_path).resolve()
        parts = list(p.parts)
        if 'scenarios' in parts:
            idx = parts.index('scenarios')
            if idx + 1 < len(parts):
                return parts[idx + 1]
    except Exception:
        pass
    return None

def write_single_conversation_file(
    result: ConversationResult,
    scenario: ExampleScenario,
    example_path: str,
    output_dir: Path,
    model: str,
    prompt_version: str,
    custom_prompt_paths: Optional[Dict[str, Optional[str]]] = None,
    seed: Optional[int] = None,
    toolset_id: Optional[str] = None,
    task_context: Optional[Dict[str, Any]] = None,
    persona: Optional[Dict[str, Any]] = None
) -> str:
    """Write a single-file JSON conversation artifact optimized for SFT.

    Includes meta/config/outcome. Per-turn traces will be added in a later task.
    Returns the file path as a string.
    """
    domain_id = _infer_domain_id(example_path)
    prompt_versions = {
        'system_agent': prompt_version,
        'user_agent': prompt_version,
        'tool_agent': prompt_version
    }
    meta: Dict[str, Any] = {
        'conversation_id': f"{domain_id}.{scenario.name}" if domain_id else scenario.name,
        'domain_id': domain_id,
        'toolset_id': toolset_id,
        'model': model,
        'prompt_versions': prompt_versions,
        'seed': seed,
        'simulator_version': '0.1.0'
    }
    if custom_prompt_paths:
        meta['prompt_files'] = custom_prompt_paths

    # Transform per-turn traces to a role-based messages list
    messages: List[Dict[str, Any]] = []
    for t in (result.turn_traces or []):
        turn_id = t.get('turn_id')
        user_text = t.get('user', '')
        assistant_obj = t.get('assistant', {}) or {}
        steps = assistant_obj.get('steps', []) or []
        # User message
        messages.append({
            'turn_id': turn_id,
            'role': 'user',
            'output_raw': user_text
        })
        # Assistant message with steps
        messages.append({
            'turn_id': turn_id,
            'role': 'assistant',
            'steps': steps
        })

    conversation_obj: Dict[str, Any] = {
        'meta': meta,
        'config': {
            'scenario_name': scenario.name,
            'task': task_context or scenario.task,
            'user_agent_config': scenario.user_agent,
            'tool_agent_config': scenario.tool_agent
        },
        'messages': messages,
        'outcome': {
            'success': result.success,
            'reason': result.termination_reason,
            'total_turns': result.metadata.get('total_turns', 0),
            'had_tool_calls': result.metadata.get('had_tool_calls', False)
        },
        'quality': {
            'ok': True,
            'reasons': []
        }
    }

    if persona:
        conversation_obj['config']['persona'] = persona

    conversation_file = output_dir / 'conversation.json'
    with open(conversation_file, 'w') as f:
        json.dump(conversation_obj, f, indent=2)
    return str(conversation_file)

def main():
    """Main CLI entry point"""
    try:
        # Load environment variables from .env file
        load_dotenv()
        
        # Parse arguments
        args = parse_arguments()
        
        # Resolve outputs root
        outputs_root = _resolve_outputs_root(args.example_path, args.outputs_root)

        # Load scenario and prompts
        scenario, system_prompts = load_scenario_and_prompts(args.example_path, args)

        persona_context, task_override, persona_id = _prepare_persona_context(
            scenario,
            args.persona_id,
        )

        # Set up logging/paths (persona-aware)
        output_file, log_file, agent_flow_file, run_dir, run_id = setup_logging(
            args.example_path,
            outputs_root,
            args.verbose,
            persona_id=persona_id,
        )
        logger = logging.getLogger(__name__)
        logger.info(f"Starting simulation with model: {args.model}")
        logger.info(f"Loaded scenario: {scenario.name}")
        if persona_id:
            logger.info(f"Using persona: {persona_id}")

        # Initialize LLM client
        api_key = args.api_key or os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("OpenAI API key required")
            print("Error: OpenAI API key required. Set OPENAI_API_KEY environment variable or use --api-key", file=sys.stderr)
            sys.exit(1)
            
        llm_client = LLMClient(model=args.model, api_key=api_key)
        logger.info(f"Initialized LLM client with model: {args.model}")
        
        prompt_captures: Dict[str, Optional[Dict[str, Any]]] = {
            "system_agent": None,
            "user_agent": None,
            "tool_agent": None,
        }

        # Create agents; only open flow logger in debug mode
        if args.debug_transcripts:
            with open(agent_flow_file, 'w') as flow_logger:
                system_agent, user_agent, tool_agent = create_agents(scenario, system_prompts, llm_client, flow_logger)
                attach_prompt_recorders(system_agent, user_agent, tool_agent, prompt_captures)
                runner = ConversationRunner(
                    scenario,
                    system_agent,
                    user_agent,
                    tool_agent,
                    args.max_turns,
                    persona=persona_context,
                    task_override=task_override,
                )
                result = runner.run_conversation()
        else:
            system_agent, user_agent, tool_agent = create_agents(scenario, system_prompts, llm_client, None)
            attach_prompt_recorders(system_agent, user_agent, tool_agent, prompt_captures)
            runner = ConversationRunner(
                scenario,
                system_agent,
                user_agent,
                tool_agent,
                args.max_turns,
                persona=persona_context,
                task_override=task_override,
            )
            result = runner.run_conversation()

        logger.info(f"Conversation completed")

        if persona_id is not None:
            result.metadata.setdefault('persona_id', persona_id)
        
        # Write single-file conversation artifact (conversation.json)
        run_dir = Path(output_file).parent
        # Detect whether custom prompt files were used
        custom_prompt_paths = {
            'system_agent': args.system_agent_prompt,
            'user_agent': args.user_agent_prompt,
            'tool_agent': args.tool_agent_prompt
        } if (args.system_agent_prompt or args.user_agent_prompt or args.tool_agent_prompt) else None

        conversation_file = write_single_conversation_file(
            result=result,
            scenario=scenario,
            example_path=args.example_path,
            output_dir=run_dir,
            model=args.model,
            prompt_version=args.prompt_version,
            custom_prompt_paths=custom_prompt_paths,
            seed=None,
            toolset_id=None,
            task_context=task_override,
            persona=persona_context
        )
        logger.info(f"Conversation file saved to: {conversation_file}")

        write_agent_prompts(prompt_captures, run_dir)

        # Write markdown transcripts only in debug mode
        if args.debug_transcripts:
            write_markdown_transcripts(result, output_file)

        # Optional: per-turn JSONL export
        if args.export_steps_jsonl:
            turns_path = run_dir / 'turns.jsonl'
            with open(turns_path, 'w') as jf:
                for i, t in enumerate(result.turn_traces or []):
                    target_text = '\n'.join(t.get('system_messages_raw', []))
                    rec = {
                        'meta': {
                            'conversation_id': f"{_infer_domain_id(args.example_path)}.{scenario.name}",
                            'step_index': i
                        },
                        'history_before': t.get('history_before', []),
                        'target_text': target_text,
                        'actions_structured': t.get('actions_structured', []),
                        'tool_results': t.get('tool_results', [])
                    }
                    jf.write(json.dumps(rec) + '\n')
            logger.info(f"Per-turn JSONL saved to: {turns_path}")
        
        # Append to global manifest
        try:
            scenario_key = _scenario_key(Path(args.example_path))
            manifest_line = {
                "scenario_key": scenario_key,
                "run_id": run_id,
                "success": result.success,
                "termination_reason": result.termination_reason,
                "had_tool_calls": result.metadata.get('had_tool_calls', False),
                "persona_id": persona_context.get('id') if persona_context else None,
                "paths": {
                    "output": str(Path(output_file)),
                    "log": str(Path(log_file)),
                    "agent_flow": str(Path(agent_flow_file)),
                    "run_dir": str(run_dir)
                }
            }
            manifest_path = outputs_root / 'index.jsonl'
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(manifest_path, 'a') as mf:
                mf.write(json.dumps(manifest_line) + "\n")
            logger.info(f"Manifest updated: {manifest_path}")
        except Exception as _e:
            logger.warning(f"Could not update manifest: {_e}")

        # Exit with appropriate code
        sys.exit(0 if result.success else 1)
        
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main() 
