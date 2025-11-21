from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable, List, Optional

from scenario import ExampleScenario

from .checks import evaluate_turn_structure
from .models import (
    CategorySummary,
    ConversationArtifact,
    ConversationEvalResult,
    ConversationTurn,
    StepInput,
    ToolParameterSpec,
    ToolRegistry,
    ToolSchema,
    TurnEvalResult,
)


def load_conversation_artifact(
    conversation_json_path: Path,
    *,
    scenario_file: Optional[Path] = None,
) -> ConversationArtifact:
    """Load a conversation.json artifact and accompanying tool schema."""
    path = Path(conversation_json_path)
    data = json.loads(path.read_text())

    conversation_id = (
        data.get("meta", {}).get("conversation_id")
        or data.get("config", {}).get("scenario_name")
        or path.parent.name
    )

    turns = _load_turns_from_data(data)

    registry = _build_tool_registry(
        data,
        path,
        scenario_file=scenario_file,
    )

    return ConversationArtifact(
        conversation_id=conversation_id,
        turns=turns,
        tool_registry=registry,
        source_path=path,
    )


def evaluate_conversation(artifact: ConversationArtifact) -> ConversationEvalResult:
    """Evaluate syntax/tool correctness for a loaded conversation artifact."""
    turn_results: List[TurnEvalResult] = []
    structure_failures = Counter()
    tool_failures = Counter()

    for turn in artifact.turns:
        result = evaluate_turn_structure(turn.steps, artifact.tool_registry)
        turn_results.append(result)
        for step in result.step_results:
            structure_failures.update(step.structure_errors)
            tool_failures.update(step.tool_errors)
        structure_failures.update(result.turn_structure_errors)
        tool_failures.update(result.turn_tool_errors)

    structure_summary = _build_category_summary(
        [t.structure_valid for t in turn_results],
        structure_failures,
    )
    tool_summary = _build_category_summary(
        [t.tool_valid for t in turn_results],
        tool_failures,
    )

    return ConversationEvalResult(
        conversation_id=artifact.conversation_id,
        turns=turn_results,
        total_turns=len(turn_results),
        structure_summary=structure_summary,
        tool_summary=tool_summary,
        source_path=artifact.source_path,
        conversation_checks=[],
    )


def _load_turns_from_data(data: dict) -> List[ConversationTurn]:
    """Extract assistant turns from the modern single-file conversation format."""
    messages = data.get("messages")
    if messages is None:
        raise ValueError("conversation.json missing expected 'messages' field")

    turns: List[ConversationTurn] = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        turn_id = message.get("turn_id")
        steps_data = message.get("steps") or []
        step_inputs: List[StepInput] = []
        for idx, step in enumerate(steps_data):
            raw_text = step.get("output_raw")
            if raw_text is None:
                continue
            micro_index = step.get("step_index")
            if micro_index is None:
                micro_index = idx + 1
            micro_index = int(micro_index)  # Keep 1-indexed as in conversation.json
            step_inputs.append(
                StepInput(
                    turn_id=turn_id,
                    micro_step_index=micro_index,
                    content=str(raw_text),
                )
            )
        if step_inputs:
            turns.append(ConversationTurn(turn_id=turn_id, steps=step_inputs))
    return turns


def _build_tool_registry(
    data: dict,
    conversation_path: Path,
    *,
    scenario_file: Optional[Path] = None,
) -> ToolRegistry:
    """Construct tool registry from scenario metadata."""
    if scenario_file is None:
        scenario_file = _infer_scenario_file(data, conversation_path)
    if scenario_file is None or not scenario_file.exists():
        return ToolRegistry()
    scenario = ExampleScenario.load(str(scenario_file))
    return _registry_from_tools_dict(scenario.tools)


def _infer_scenario_file(data: dict, conversation_path: Path) -> Optional[Path]:
    """Best-effort inference of the scenario file based on metadata/path."""
    from scenario import extract_scenario_id_from_filename
    
    repo_root = Path(__file__).resolve().parents[3]

    # Attempt inference from parent directory naming convention
    parent_name = conversation_path.parent.name
    if "__" in parent_name:
        prefix = parent_name.split("__", 1)[0]
        parts = prefix.split(".")
        if len(parts) >= 3:
            domain, use_case, scenario_id = parts[0], parts[1], parts[2]
            # Look for scenario file matching this scenario_id (with any persona)
            use_case_dir = repo_root / "data" / "domains" / domain / use_case
            if use_case_dir.exists():
                # Find file starting with scenario_id
                for candidate_file in use_case_dir.glob(f"{scenario_id}*.json"):
                    if candidate_file.name != "tools.json":
                        return candidate_file

    # Fallback: use config scenario name with domain metadata if present
    scenario_name = data.get("config", {}).get("scenario_name")
    domain_meta = data.get("meta", {}).get("domain_id")
    if scenario_name and domain_meta:
        # Try to find scenario file in use_case directory
        # scenario_name format: domain.use_case.scenario_id
        scenario_parts = scenario_name.split(".")
        if len(scenario_parts) >= 3:
            domain, use_case, scenario_id = scenario_parts[0], scenario_parts[1], scenario_parts[2]
            use_case_dir = repo_root / "data" / "domains" / domain / use_case
            if use_case_dir.exists():
                # Find file starting with scenario_id
                for candidate_file in use_case_dir.glob(f"{scenario_id}*.json"):
                    if candidate_file.name != "tools.json":
                        return candidate_file
    return None


def _registry_from_tools_dict(tools: dict) -> ToolRegistry:
    registry = ToolRegistry()
    for tool_name, tool_def in (tools or {}).items():
        params = tool_def.get("parameters", {})
        schema = ToolSchema(name=tool_name)
        for param_name, param_def in params.items():
            schema.parameters[param_name] = ToolParameterSpec(
                name=param_name,
                required=bool(param_def.get("required")),
                type=param_def.get("type"),
                description=param_def.get("description"),
            )
        registry.tools[tool_name] = schema
    return registry


def _build_category_summary(
    turn_valid_flags: Iterable[bool],
    failure_counter: Counter,
) -> CategorySummary:
    flags = list(turn_valid_flags)
    total = len(flags)
    valid_count = sum(1 for flag in flags if flag)
    pass_rate = valid_count / total if total else 1.0
    all_valid = valid_count == total
    return CategorySummary(
        valid=all_valid,
        pass_rate=pass_rate,
        failure_counts=dict(failure_counter),
    )
