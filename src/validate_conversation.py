import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional


def _find_tag(text: str, tag: str) -> Tuple[int, int]:
    """Return (start_index, end_index) for the first full tag occurrence: <tag>...</tag>.
    If closing tag not found, returns (start_index, -1).
    """
    start = text.find(f"<{tag}>")
    if start == -1:
        return -1, -1
    end = text.find(f"</{tag}>", start)
    if end == -1:
        return start, -1
    return start, end + len(f"</{tag}>")


def _parse_action_block(content: str) -> Dict[str, Any]:
    """Parse a single <action ...>...</action> block.
    Returns keys: type, has_closing, ends_with_action, name?, body, args? (tool),
    start_index, open_end_index, close_index.
    """
    result: Dict[str, Any] = {
        "type": None,
        "name": None,
        "body": "",
        "args": None,
        "has_closing": False,
        "ends_with_action": False,
        "start_index": -1,
        "open_end_index": -1,
        "close_index": -1,
    }
    if not content:
        return result
    start = content.find("<action")
    if start == -1:
        return result
    open_end = content.find('>', start)
    if open_end == -1:
        return result
    header = content[start + len("<action"):open_end]
    act_type = None
    if 'type="tool"' in header:
        act_type = 'tool'
    elif 'type="say"' in header:
        act_type = 'say'
    # name (optional)
    name_val = None
    npos = header.find('name="')
    if npos != -1:
        nend = header.find('"', npos + 6)
        if nend != -1:
            name_val = header[npos + 6:nend]

    end_tag = '</action>'
    close_index = content.find(end_tag, open_end + 1)
    has_closing = close_index != -1
    if has_closing:
        body = content[open_end + 1:close_index].strip()
        tail = content[close_index + len(end_tag):]
        ends_with_action = tail == ''
    else:
        body = content[open_end + 1:].strip()
        ends_with_action = False

    result.update({
        "type": act_type,
        "name": name_val,
        "body": body,
        "has_closing": has_closing,
        "ends_with_action": ends_with_action,
        "start_index": start,
        "open_end_index": open_end,
        "close_index": close_index,
    })

    if act_type == 'tool':
        try:
            result["args"] = json.loads(body)
        except Exception:
            result["args"] = None

    return result


def _count_action_blocks(content: str) -> int:
    return len(re.findall(r"<action\s", content or ""))


def _extract_sections(content: str) -> Dict[str, Tuple[int, int]]:
    """Return approximate spans for think, plan, and action sections."""
    s: Dict[str, Tuple[int, int]] = {
        "think": (-1, -1),
        "plan": (-1, -1),
        "action": (-1, -1),
    }
    if not content:
        return s
    think_start = content.find('<think>')
    think_end = content.find('</think>')
    if think_start != -1 and think_end != -1 and think_end > think_start:
        s["think"] = (think_start, think_end + len('</think>'))
    plan_start = content.find('<plan>')
    plan_end = content.find('</plan>')
    if plan_start != -1 and plan_end != -1 and plan_end > plan_start:
        s["plan"] = (plan_start, plan_end + len('</plan>'))
    action_start = content.find('<action')
    if action_start != -1:
        s["action"] = (action_start, -1)
    return s


def validate_conversation_file(path: Path) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        return False, [f"Failed to read/parse JSON: {e}"]

    messages = data.get('messages') or []
    for m in messages:
        if m.get('role') != 'assistant':
            continue
        turn_id = m.get('turn_id')
        steps = m.get('steps') or []
        if not isinstance(steps, list) or not steps:
            errors.append(f"Turn {turn_id}: assistant message has no steps")
            continue
        for step in steps:
            step_index = step.get('step_index')
            raw = step.get('output_raw') or ''
            action_structured = step.get('action_structured') or {}
            observation = step.get('observation')

            # 1) Exactly one <action>...
            action_count = _count_action_blocks(raw)
            if action_count != 1:
                errors.append(f"Turn {turn_id}.{step_index}: expected exactly one <action>, found {action_count}")

            # 2) Parse action and enforce formatting rules
            parsed = _parse_action_block(raw)
            if parsed["type"] not in ('say', 'tool'):
                errors.append(f"Turn {turn_id}.{step_index}: action type missing or invalid")

            if not parsed["has_closing"]:
                errors.append(f"Turn {turn_id}.{step_index}: missing closing </action> tag")

            if not parsed["ends_with_action"]:
                errors.append(f"Turn {turn_id}.{step_index}: message must end with </action> (no trailing text/whitespace)")

            # 3) Section ordering: action appears after </plan> if plan exists; else after </think>
            sections = _extract_sections(raw)
            action_start = sections["action"][0]
            if sections["plan"][1] != -1 and action_start != -1 and action_start < sections["plan"][1]:
                errors.append(f"Turn {turn_id}.{step_index}: action should follow </plan> section")
            elif sections["plan"][1] == -1 and sections["think"][1] != -1 and action_start < sections["think"][1]:
                errors.append(f"Turn {turn_id}.{step_index}: action should follow </think> when plan is absent")

            # 4) Tool JSON validity
            if parsed["type"] == 'tool' and parsed["args"] is None:
                errors.append(f"Turn {turn_id}.{step_index}: tool action body must be valid JSON")

            # 5) Cross-check with action_structured
            stype = action_structured.get('type')
            if parsed["type"] == 'say' and stype != 'say':
                errors.append(f"Turn {turn_id}.{step_index}: action_structured.type mismatch (expected say)")
            if parsed["type"] == 'tool' and stype != 'tool_call':
                errors.append(f"Turn {turn_id}.{step_index}: action_structured.type mismatch (expected tool_call)")

            if parsed["type"] == 'say':
                expected_text = parsed["body"]
                actual_text = (action_structured.get('text') or '')
                if expected_text != actual_text:
                    errors.append(f"Turn {turn_id}.{step_index}: say text mismatch between raw action and action_structured")

                if observation is not None:
                    errors.append(f"Turn {turn_id}.{step_index}: say step must have observation = null")

            if parsed["type"] == 'tool':
                # Compare args dict when possible
                if isinstance(action_structured.get('args'), dict) and isinstance(parsed["args"], dict):
                    if action_structured['args'] != parsed['args']:
                        errors.append(f"Turn {turn_id}.{step_index}: tool args mismatch between raw action and action_structured")
                # Observation should exist for tool calls
                if not isinstance(observation, dict):
                    errors.append(f"Turn {turn_id}.{step_index}: tool step must include observation object")

    return (len(errors) == 0), errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate assistant message format in conversation.json')
    parser.add_argument('path', help='Path to conversation.json (or a directory to scan recursively)')
    args = parser.parse_args()

    target = Path(args.path)
    files: List[Path] = []
    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = list(target.rglob('conversation.json'))
    else:
        print(f"Error: Path not found: {target}", file=sys.stderr)
        return 2

    any_errors = False
    for f in files:
        ok, errs = validate_conversation_file(f)
        if ok:
            print(f"OK: {f}")
        else:
            any_errors = True
            print(f"FAIL: {f}")
            for e in errs:
                print(f"  - {e}")

    return 0 if not any_errors else 1


if __name__ == '__main__':
    sys.exit(main())


