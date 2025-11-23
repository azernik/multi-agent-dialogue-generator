"""Reader functions for L1 evaluation.

Provides functions to extract actions from conversations, find corresponding
gold conversations in valid_outputs/v2, load tool registries, and generate
sequential run numbers for L1 evaluation outputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from scenario import ExampleScenario

from .models import Action


def extract_actions(conversation_data: Dict[str, Any]) -> List[Action]:
    actions: List[Action] = []
    messages = conversation_data.get("messages", []) or []

    for message in messages:
        if message.get("role") != "assistant":
            continue

        turn_id = message.get("turn_id")
        if turn_id is None:
            continue

        steps = message.get("steps", []) or []
        for idx, step in enumerate(steps):
            step_index = step.get("step_index")
            if step_index is None:
                step_index = idx + 1

            action_structured = step.get("action_structured", {}) or {}
            action_type_str = action_structured.get("type", "")

            if action_type_str == "tool_call":
                tool_name = action_structured.get("name")
                parameters = action_structured.get("args", {}) or {}
                actions.append(
                    Action(
                        turn_id=turn_id,
                        step_index=step_index,
                        action_type="tool",
                        tool_name=tool_name,
                        parameters=parameters,
                    )
                )
            elif action_type_str == "say":
                actions.append(
                    Action(
                        turn_id=turn_id,
                        step_index=step_index,
                        action_type="say",
                        tool_name=None,
                        parameters=None,
                    )
                )

    return actions


def find_gold_conversation(conversation_path: Path) -> Optional[Path]:
    try:
        with open(conversation_path, "r") as f:
            conversation_data = json.load(f)

        config = conversation_data.get("config", {}) or {}
        scenario_name = config.get("scenario_name")
        persona = config.get("persona", {}) or {}
        persona_id = persona.get("id") if isinstance(persona, dict) else persona

        if not scenario_name:
            return None

        if not persona_id:
            return None

        repo_root = Path(__file__).resolve().parents[3]
        valid_outputs_dir = repo_root / "data" / "valid_outputs" / "v2"

        if not valid_outputs_dir.exists():
            return None

        pattern = f"*__{scenario_name}__{persona_id}.json"
        matches = sorted(list(valid_outputs_dir.glob(pattern)))

        if matches:
            return matches[0]

        return None
    except Exception:
        return None


def load_tool_registry(conversation_path: Path) -> Dict[str, Dict[str, Any]]:
    try:
        with open(conversation_path, "r") as f:
            conversation_data = json.load(f)

        config = conversation_data.get("config", {}) or {}
        scenario_name = config.get("scenario_name")

        if not scenario_name:
            return {}

        repo_root = Path(__file__).resolve().parents[3]
        domains_dir = repo_root / "data" / "domains"

        scenario_file = None
        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            for use_case_dir in domain_dir.iterdir():
                if not use_case_dir.is_dir():
                    continue
                candidate = use_case_dir / f"{scenario_name}.json"
                if candidate.exists():
                    scenario_file = candidate
                    break
                for file in use_case_dir.glob(f"{scenario_name}__*.json"):
                    if file.name != "tools.json":
                        scenario_file = file
                        break
                if scenario_file:
                    break
            if scenario_file:
                break

        if not scenario_file or not scenario_file.exists():
            return {}

        scenario = ExampleScenario.load(str(scenario_file))
        tools = scenario.tools or {}

        registry: Dict[str, Dict[str, Any]] = {}
        for tool_name, tool_def in tools.items():
            params = tool_def.get("parameters", {}) or {}
            required = []
            optional = []
            all_params = []

            for param_name, param_def in params.items():
                all_params.append(param_name)
                if param_def.get("required", False):
                    required.append(param_name)
                else:
                    optional.append(param_name)

            registry[tool_name] = {
                "required": required,
                "optional": optional,
                "all_params": all_params,
            }

        return registry
    except Exception:
        return {}


def get_next_run_number(conversation_id: str, eval_l1_dir: Path) -> str:
    eval_l1_dir.mkdir(parents=True, exist_ok=True)

    pattern = f"{conversation_id}_l1_*.json"
    existing_files = list(eval_l1_dir.glob(pattern))

    if not existing_files:
        return "001"

    run_numbers = []
    for file in existing_files:
        stem = file.stem
        parts = stem.split("_l1_")
        if len(parts) == 2:
            try:
                num = int(parts[1])
                run_numbers.append(num)
            except ValueError:
                continue

    if not run_numbers:
        return "001"

    next_num = max(run_numbers) + 1
    return f"{next_num:03d}"

