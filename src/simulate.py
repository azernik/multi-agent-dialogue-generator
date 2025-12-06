import argparse
import json
import os
import shutil
import sys
import logging
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Tuple, Dict, List, Optional, Any
from dotenv import load_dotenv

from core import LLMClient, HuggingFaceLLMClient, ConversationContext
from agents import SystemAgent, UserAgent, ToolAgent
from scenario import ExampleScenario, load_system_prompts, resolve_scenario_id, resolve_scenario_target, resolve_scenario_pattern
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

    # Use persona_arg if provided, otherwise use persona from scenario
    persona_id = persona_arg or scenario.persona_id
    
    if persona_id:
        # Hardcoded catalog path
        repo_root = Path(__file__).resolve().parent.parent
        catalog_path = (repo_root / "data/personas/catalog.json").resolve()
        
        if not catalog_path.exists():
            raise FileNotFoundError(f"Persona catalog not found: {catalog_path}")
        
        base_persona = _load_persona_from_catalog(catalog_path, persona_id)
        persona_context = dict(base_persona)
        persona_context['id'] = persona_id
    elif persona_arg:
        raise ValueError("Persona id provided but scenario has no persona configured")

    return persona_context, task_override, persona_id

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Run multi-agent conversation simulation')
    parser.add_argument('targets', nargs='+', help='Scenario file paths or scenario IDs (e.g., ca_oe_005__persona_001)')
    parser.add_argument('--model', default='gpt-5.1', help='LLM model to use')
    parser.add_argument('--max-turns', type=int, default=20, help='Maximum conversation turns')
    parser.add_argument('--api-key', help='OpenAI API key (default: OPENAI_API_KEY env var)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose console output')
    parser.add_argument('--system-prompts-dir', help='Path to system prompts directory (default: prompts)')
    parser.add_argument('--system-agent-prompt', help='Path to system agent prompt file')
    parser.add_argument('--user-agent-prompt', help='Path to user agent prompt file') 
    parser.add_argument('--tool-agent-prompt', help='Path to tool agent prompt file')
    parser.add_argument('--prompt-version', default=None, help='Version of prompts to use for all agents (overrides per-agent versions if specified)')
    parser.add_argument('--system-agent-prompt-version', default='v3', help='Version of system agent prompt (default: v3)')
    parser.add_argument('--user-agent-prompt-version', default='v1', help='Version of user agent prompt (default: v1)')
    parser.add_argument('--tool-agent-prompt-version', default='v1', help='Version of tool agent prompt (default: v1)')
    parser.add_argument('--debug-transcripts', action='store_true', help='Write system.md/user.md/tool.md and agent_flow.log')
    parser.add_argument('--export-steps-jsonl', action='store_true', help='Write turns.jsonl (one JSONL record per system turn)')
    parser.add_argument('--outputs-root', help='Root directory for outputs (default: env MADG_OUTPUT_ROOT or data/outputs)')
    parser.add_argument('--persona-id', help='Persona ID to use when scenario defines personas')
    parser.add_argument('--run-eval', action='store_true', help='Automatically run evaluation after conversation completes')
    parser.add_argument('--eval-model', default='gpt-5.1', help='Model to use for evaluation (default: gpt-5.1)')
    parser.add_argument('--skip-faithfulness', action='store_true', help='Skip faithfulness evaluation when running --run-eval')
    parser.add_argument('--skip-role-confusion', action='store_true', help='Skip role confusion evaluation when running --run-eval')
    parser.add_argument('--hf-model', help='HuggingFace model name/path (enables HF mode, e.g., ajChakrarborty/custom-qwen2.5-7b-instruct-ft-1)')
    parser.add_argument('--hf-base-model', help='Base model name if using LoRA (e.g., Qwen/Qwen2.5-7B-Instruct)')
    parser.add_argument('--no-4bit', action='store_true', help='Disable 4-bit quantization for HF models')
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

def _relative_scenario_path(example_path: Path) -> Path:
    """Compute scenario-relative path under data/domains.
    Falls back to just the filename (without extension).
    """
    parts = example_path.resolve().parts
    rel = None
    if 'domains' in parts:
        idx = parts.index('domains')
        # Include all parts after domains, but replace filename with base name (no extension)
        domain_parts = parts[idx+1:]
        if domain_parts:
            # Replace last part (filename) with filename without extension
            from scenario import extract_scenario_id_from_filename
            base_parts = list(domain_parts[:-1])
            filename_base = extract_scenario_id_from_filename(domain_parts[-1])
            rel = Path(*base_parts) / filename_base if base_parts else Path(filename_base)
    return rel if rel and str(rel) else Path(example_path.stem)

def _scenario_key(example_path: Path) -> str:
    """Canonical scenario key: domain.use_case.scenario_id derived from data/domains path and filename."""
    from scenario import extract_scenario_id_from_filename, parse_scenario_filename
    
    parts = example_path.resolve().parts
    if 'domains' in parts:
        idx = parts.index('domains')
        tail = [p for p in parts[idx+1:]]
        if len(tail) >= 2:
            domain, use_case = tail[0], tail[1]
            # Extract scenario_id from filename (last part)
            scenario_id = extract_scenario_id_from_filename(tail[-1])
            return f"{domain}.{use_case}.{scenario_id}"
    # fallback: use filename without extension
    return extract_scenario_id_from_filename(example_path.name)

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
) -> Tuple[str, str, str, Path, str, str, str, str]:
    """Set up logging and return output paths.
    Returns: output_file, log_file, agent_flow_file, run_dir, run_id, timestamp, scenario_id, persona_id
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    scenario_file = Path(example_path)
    
    # Extract scenario_id from filename
    from scenario import extract_scenario_id_from_filename, extract_persona_from_filename
    scenario_id = extract_scenario_id_from_filename(scenario_file.name)
    
    # Extract persona from filename if not provided
    if not persona_id:
        persona_id = extract_persona_from_filename(scenario_file.name)
    
    persona_slug = _sanitize_persona_id(persona_id)
    persona_str = persona_id or "default"
    
    if persona_slug:
        run_id = f"simulate_{persona_slug}_{timestamp}"
    else:
        run_id = f"simulate_{timestamp}"

    # New format: timestamp__scenario_id__persona_id
    run_dir = outputs_root / f"{timestamp}__{scenario_id}__{persona_str}"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = run_dir / "simulate.log"
    output_file = run_dir / "simulate.out"
    agent_flow_file = run_dir / "agent_flow.log"
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s:  %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stderr) if verbose else logging.NullHandler()
        ]
    )
    
    # Suppress httpx HTTP request logs
    logging.getLogger('httpx').setLevel(logging.WARNING)
    
    return str(output_file), str(log_file), str(agent_flow_file), run_dir, run_id, timestamp, scenario_id, persona_str


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
    # Else, walk up from the scenario file's directory to find siblings
    scenario_file = Path(example_path).resolve()
    cur = scenario_file.parent  # Start from scenario file's directory
    for parent in [cur] + list(cur.parents):
        sibling_new = parent.parent / 'prompts'
        if sibling_new.exists():
            return sibling_new
        sibling_old = parent.parent / 'data' / 'system_prompts'
        if sibling_old.exists():
            return sibling_old
    # Fallback to new default
    return Path('prompts')


def load_scenario_and_prompts(example_path: str, args: argparse.Namespace) -> Tuple[ExampleScenario, Dict[str, str], Dict[str, str]]:
    """Load scenario and system prompts"""
    try:
        # Load scenario from example_path
        scenario = ExampleScenario.load(example_path)
        
        # Determine prompt versions: --prompt-version overrides all, otherwise use per-agent defaults
        if args.prompt_version:
            # Override mode: use same version for all agents
            prompt_versions = {
                'system_agent': args.prompt_version,
                'user_agent': args.prompt_version,
                'tool_agent': args.prompt_version
            }
        else:
            # Per-agent version mode
            prompt_versions = {
                'system_agent': args.system_agent_prompt_version,
                'user_agent': args.user_agent_prompt_version,
                'tool_agent': args.tool_agent_prompt_version
            }
        
        # Load system prompts
        if args.system_agent_prompt or args.user_agent_prompt or args.tool_agent_prompt:
            # Load individual prompt files if specified
            system_prompts = {}
            custom_prompts = {
                'system_agent': args.system_agent_prompt,
                'user_agent': args.user_agent_prompt,
                'tool_agent': args.tool_agent_prompt
            }
            
            prompts_dir = Path(args.system_prompts_dir) if args.system_prompts_dir else _resolve_prompts_dir(example_path)
            for agent_type, custom_path in custom_prompts.items():
                if custom_path:
                    # Use custom path
                    with open(custom_path, 'r') as f:
                        system_prompts[agent_type] = f.read().strip()
                else:
                    # Fall back to versioned prompt file
                    prompt_file = prompts_dir / agent_type / f"{prompt_versions[agent_type]}.txt"
                    with open(prompt_file, 'r') as f:
                        system_prompts[agent_type] = f.read().strip()
        else:
            # Use directory-based loading with per-agent versions
            prompts_dir = Path(args.system_prompts_dir) if args.system_prompts_dir else _resolve_prompts_dir(example_path)
            system_prompts = {}
            for agent_type in ['system_agent', 'user_agent', 'tool_agent']:
                prompt_file = prompts_dir / agent_type / f"{prompt_versions[agent_type]}.txt"
                with open(prompt_file, 'r') as f:
                    system_prompts[agent_type] = f.read().strip()
        
        return scenario, system_prompts, prompt_versions
        
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

def _copy_to_valid_outputs(
    output_dir: Path,
    conversation_filename: str,
    repo_root: Path
) -> Optional[Path]:
    """Copy successful simulation conversation file to valid_outputs directory (flat structure).
    Returns destination file path."""
    # Determine valid_outputs root
    valid_outputs_root = repo_root / "data" / "valid_outputs" / "v2"
    
    # Flat structure: just copy the conversation file with same name
    src_file = output_dir / conversation_filename
    if not src_file.exists():
        return None
    
    dest_file = valid_outputs_root / conversation_filename
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    
    shutil.copy2(src_file, dest_file)
    
    return dest_file


def _infer_domain_id(example_path: str) -> Optional[str]:
    """Infer domain id from an example path like data/domains/<domain>/..."""
    try:
        p = Path(example_path).resolve()
        parts = list(p.parts)
        if 'domains' in parts:
            idx = parts.index('domains')
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
    prompt_versions: Dict[str, str],
    timestamp: str,
    scenario_id: str,
    persona_id: str,
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

    # New format: timestamp__scenario_id__persona_id.json
    conversation_filename = f"{timestamp}__{scenario_id}__{persona_id}.json"
    conversation_file = output_dir / conversation_filename
    with open(conversation_file, 'w') as f:
        json.dump(conversation_obj, f, indent=2)
    return str(conversation_file)

def _run_single_simulation(example_path: str, args: argparse.Namespace) -> int:
    """Run a single simulation for the given scenario path.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        # Resolve outputs root
        outputs_root = _resolve_outputs_root(example_path, args.outputs_root)

        # Load scenario and prompts
        scenario, system_prompts, prompt_versions = load_scenario_and_prompts(example_path, args)
        
        # # Print prompt versions at the start
        # print(f"Prompt versions: {json.dumps(prompt_versions, indent=2)}", file=sys.stderr)

        persona_context, task_override, persona_id = _prepare_persona_context(
            scenario,
            args.persona_id,
        )

        # Set up logging/paths (persona-aware)
        output_file, log_file, agent_flow_file, run_dir, run_id, timestamp, scenario_id, persona_str = setup_logging(
            example_path,
            outputs_root,
            args.verbose,
            persona_id=persona_id,
        )
        logger = logging.getLogger(__name__)
        # Reduced verbosity - initialization messages only logged to file, not console
        
        # Initialize LLM client
        if args.hf_model:
            # HuggingFace model mode
            try:
                llm_client = HuggingFaceLLMClient(
                    model_name=args.hf_model,
                    base_model=args.hf_base_model,
                    load_in_4bit=not args.no_4bit
                )
                # Use HF model name for metadata
                model_name_for_metadata = args.hf_model
            except ImportError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                logger.error(f"Failed to load HuggingFace model: {e}")
                print(f"Error: Failed to load HuggingFace model: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            # OpenAI API mode (default)
            api_key = args.api_key or os.getenv('OPENAI_API_KEY')
            if not api_key:
                logger.error("OpenAI API key required")
                print("Error: OpenAI API key required. Set OPENAI_API_KEY environment variable or use --api-key", file=sys.stderr)
                sys.exit(1)
            llm_client = LLMClient(model=args.model, api_key=api_key)
            model_name_for_metadata = args.model
        
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
                    verbose=args.verbose,
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
                verbose=args.verbose,
            )
            result = runner.run_conversation()

        # Conversation completion logged to file only

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
            example_path=example_path,
            output_dir=run_dir,
            model=model_name_for_metadata,
            prompt_versions=prompt_versions,
            timestamp=timestamp,
            scenario_id=scenario_id,
            persona_id=persona_str,
            custom_prompt_paths=custom_prompt_paths,
            seed=None,
            toolset_id=None,
            task_context=task_override,
            persona=persona_context
        )
        # File save logged to file only

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
                            'conversation_id': f"{_infer_domain_id(example_path)}.{scenario.name}",
                            'step_index': i
                        },
                        'history_before': t.get('history_before', []),
                        'target_text': target_text,
                        'actions_structured': t.get('actions_structured', []),
                        'tool_results': t.get('tool_results', [])
                    }
                    jf.write(json.dumps(rec) + '\n')
            # JSONL save logged to file only
        
        # Append to global manifest
        try:
            scenario_key = _scenario_key(Path(example_path))
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
            # Manifest update logged to file only
        except Exception as _e:
            logger.warning(f"Could not update manifest: {_e}")

        # Print final outputs: conversation.json path and eval command
        repo_root = Path(__file__).resolve().parent.parent
        conversation_path = Path(conversation_file)
        relative_path = conversation_path.relative_to(repo_root)
        
        print(f"\nConversation file: {relative_path}", file=sys.stderr)

        # Initialize eval result variables
        eval_overall_success = None
        eval_copied_to_valid = None
        eval_output_data = None

        # Run evaluation if requested
        if args.run_eval:
            try:
                import subprocess
                import sys as sys_module
                
                eval_args = [
                    str(conversation_path),
                    "--model", args.eval_model,
                ]
                if args.skip_faithfulness:
                    eval_args.append("--skip-faithfulness")
                if args.skip_role_confusion:
                    eval_args.append("--skip-role-confusion")
                
                # Run eval and capture output
                eval_result = subprocess.run(
                    [sys_module.executable, "-m", "eval.run"] + eval_args,
                    cwd=str(repo_root),
                    env={**os.environ, "PYTHONPATH": str(repo_root / "src")},
                    capture_output=True,
                    text=True,
                )
                
                # Parse eval output
                if eval_result.returncode == 0 and eval_result.stdout:
                    try:
                        eval_output = json.loads(eval_result.stdout)
                        # Write eval results to file
                        eval_output_file = run_dir / "eval.json"
                        with open(eval_output_file, 'w') as f:
                            json.dump(eval_output, f, indent=2, ensure_ascii=False)
                        
                        # Process eval results
                        overall_success = eval_output.get("SUCCESS", None)
                        copied_to_valid = None
                        
                        # If eval succeeded, automatically copy to valid_outputs
                        if overall_success is True:
                            try:
                                # Extract conversation filename from conversation_file path
                                conversation_filename = Path(conversation_file).name
                                dest_file = _copy_to_valid_outputs(
                                    output_dir=run_dir,
                                    conversation_filename=conversation_filename,
                                    repo_root=repo_root
                                )
                                if dest_file:
                                    valid_outputs_root = repo_root / "data" / "valid_outputs" / "v2"
                                    copied_to_valid = dest_file.relative_to(valid_outputs_root)
                            except Exception as e:
                                logger.warning(f"Failed to copy to valid_outputs: {e}")
                                print(f"Warning: Failed to copy to valid_outputs: {e}", file=sys.stderr)
                        
                        # Store eval results for final summary
                        eval_overall_success = overall_success
                        eval_copied_to_valid = copied_to_valid
                        eval_output_data = eval_output  # Store for failure reason extraction
                        # Also write to log file
                        with open(log_file, 'a') as log_f:
                            log_f.write("\n\n=== EVALUATION OUTPUT ===\n")
                            json.dump(eval_output, log_f, indent=2, ensure_ascii=False)
                            log_f.write("\n")
                    except json.JSONDecodeError:
                        # If not JSON, write raw output
                        eval_output_file = run_dir / "eval.txt"
                        with open(eval_output_file, 'w') as f:
                            f.write(eval_result.stdout)
                        if eval_result.stderr:
                            f.write("\n\nSTDERR:\n" + eval_result.stderr)
                        # Eval output unclear
                        eval_overall_success = None
                        eval_copied_to_valid = None
                        eval_output_data = None
                else:
                    logger.warning(f"Eval failed: {eval_result.stderr}")
                    # Also write failure to log file
                    with open(log_file, 'a') as log_f:
                        log_f.write("\n\n=== EVALUATION FAILED ===\n")
                        if eval_result.stderr:
                            log_f.write(eval_result.stderr)
                        log_f.write("\n")
                    eval_overall_success = None
                    eval_copied_to_valid = None
                    eval_output_data = None
            except Exception as e:
                logger.warning(f"Could not run evaluation: {e}")

        # Print final summary (+ lines)
        if args.run_eval and eval_overall_success is not None:
            if eval_overall_success is True:
                print(f"\nSUCCESS", file=sys.stderr)
                if eval_copied_to_valid:
                    print(f"", file=sys.stderr)
                    print(f"Copied to: {eval_copied_to_valid}", file=sys.stderr)
            else:
                print(f"\nFAILED", file=sys.stderr)
                # Extract and print failure reason
                if eval_output_data:
                    failure_reason = None
                    eval_failed_part = None
                    
                    # Check which part failed
                    syntax = eval_output_data.get("syntax", {})
                    success_eval = eval_output_data.get("success", {})
                    faithfulness = eval_output_data.get("faithfulness", {})
                    role_confusion = eval_output_data.get("role_confusion", {})
                    
                    # Check syntax first
                    if syntax:
                        summary = syntax.get("summary", {})
                        if not (summary.get("structure", {}).get("valid", True) and 
                                summary.get("tool", {}).get("valid", True)):
                            eval_failed_part = "syntax"
                            structure = summary.get("structure", {})
                            tool = summary.get("tool", {})
                            issues = []
                            if not structure.get("valid", True):
                                failure_counts = structure.get("failure_counts", {})
                                if failure_counts:
                                    issue_details = ", ".join(f"{k}: {v}" for k, v in failure_counts.items())
                                    issues.append(f"structure ({issue_details})")
                                else:
                                    issues.append("structure")
                            if not tool.get("valid", True):
                                failure_counts = tool.get("failure_counts", {})
                                if failure_counts:
                                    issue_details = ", ".join(f"{k}: {v}" for k, v in failure_counts.items())
                                    issues.append(f"tool ({issue_details})")
                                else:
                                    issues.append("tool")
                            if issues:
                                failure_reason = f"Syntax error: {'; '.join(issues)}"
                    
                    # Check success evaluation
                    if not eval_failed_part and success_eval and "error" not in success_eval:
                        if not success_eval.get("success", True):
                            eval_failed_part = "success"
                            failure_reason = success_eval.get("reason")
                    
                    # Check faithfulness
                    if not eval_failed_part and faithfulness and "error" not in faithfulness:
                        if not faithfulness.get("summary", {}).get("valid", True):
                            eval_failed_part = "faithfulness"
                            summary = faithfulness.get("summary", {})
                            failure_reason = summary.get("reason") or faithfulness.get("reason")
                            if not failure_reason:
                                error_turns = faithfulness.get("error_turns", [])
                                if error_turns:
                                    failure_reason = f"Faithfulness errors in turns: {', '.join(map(str, error_turns))}"
                                else:
                                    failure_reason = "Faithfulness validation failed"
                    
                    # Check role confusion
                    if not eval_failed_part and role_confusion and "error" not in role_confusion:
                        if role_confusion.get("has_confusion", False):
                            eval_failed_part = "role_confusion"
                            failure_reason = role_confusion.get("reason")
                    
                    # Print failure reason if found
                    if failure_reason:
                        if eval_failed_part:
                            print(f"Failed {eval_failed_part}: {failure_reason}", file=sys.stderr)
                        else:
                            print(f"Failed: {failure_reason}", file=sys.stderr)
        
        # Print file paths
        print(f"", file=sys.stderr)
        try:
            scenario_rel = Path(example_path).relative_to(repo_root)
            print(f"{scenario_rel}", file=sys.stderr)
        except ValueError:
            print(f"{example_path}", file=sys.stderr)
        try:
            conv_rel = conversation_path.relative_to(repo_root)
            print(f"{conv_rel}", file=sys.stderr)
        except ValueError:
            print(f"{conversation_path}", file=sys.stderr)

        # Exit with appropriate code
        return 0 if result.success else 1
        
    except Exception as e:
        print(f"Unexpected error running simulation: {e}", file=sys.stderr)
        return 1


def main():
    """Main CLI entry point"""
    try:
        # Load environment variables from .env file
        load_dotenv()
        
        # Parse arguments
        args = parse_arguments()
        
        # Resolve targets (paths, IDs, or patterns) to scenario file paths
        scenario_paths = []
        for target in args.targets:
            if '*' in target and '/' not in target and not target.endswith('.json'):
                # Treat as glob pattern
                scenario_paths.extend(resolve_scenario_pattern(target))
            else:
                # Treat as path or ID
                scenario_paths.append(resolve_scenario_target(target))
        
        # Run simulation for each scenario
        exit_codes = []
        for scenario_path in scenario_paths:
            exit_code = _run_single_simulation(str(scenario_path), args)
            exit_codes.append(exit_code)
        
        # Exit with error if any simulation failed
        sys.exit(1 if any(code != 0 for code in exit_codes) else 0)
        
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main() 
