from __future__ import annotations

from typing import Dict, List, Optional

from .models import StepEvalResult, StepInput, ToolRegistry, TurnEvalResult
from .parser import ParsedAction, parse_action_body_json, parse_action_blocks


STRUCTURE_MISSING_BLOCK = "structure_missing_block"
STRUCTURE_INVALID_BLOCK_FORMAT = "structure_invalid_block_format"
STRUCTURE_UNEXPECTED_TEXT = "structure_unexpected_text"
SYNTAX_ILLEGAL_ACTION_TYPE = "syntax_illegal_action_type"
SYNTAX_ACTION_ATTRIBUTE_MISSING = "syntax_action_attribute_missing"

TOOL_ILLEGAL_BODY_JSON = "tool_illegal_body_json"
TOOL_ILLEGAL_VALUE_TYPE = "tool_illegal_value_type"
TOOL_INVALID_NAME = "tool_invalid_name"
TOOL_UNKNOWN_ARG = "tool_unknown_arg"
TOOL_MISSING_REQUIRED_ARG = "tool_missing_required_arg"

TURN_STRUCTURE_INVALID_SAY = "turn_structure_invalid_say"
TURN_FIRST_STEP_MISSING_PLAN = "turn_first_step_missing_plan"


def evaluate_turn_structure(
    turn_steps: List[StepInput],
    tool_registry: ToolRegistry,
) -> TurnEvalResult:
    step_results: List[StepEvalResult] = []
    say_step_indices: List[int] = []
    first_step_has_plan: Optional[bool] = None

    for idx, step in enumerate(turn_steps):
        parsed = parse_action_blocks(step.content)
        structure_errors = _collect_structure_errors(parsed, is_first_step=(idx == 0))
        tool_errors: List[str] = []
        if parsed.action_type == "tool":
            tool_errors = _collect_tool_errors(parsed, tool_registry)
        elif parsed.action_type == "say":
            say_step_indices.append(idx)
        else:
            if parsed.action_type is not None and parsed.action_type != "say":
                structure_errors.append(SYNTAX_ILLEGAL_ACTION_TYPE)

        if idx == 0:
            first_step_has_plan = parsed.plan is not None

        step_results.append(
            StepEvalResult(
                micro_step_index=step.micro_step_index,
                structure_errors=structure_errors,
                tool_errors=tool_errors,
            )
        )

    turn_structure_errors: List[str] = []
    if first_step_has_plan is False:
        turn_structure_errors.append(TURN_FIRST_STEP_MISSING_PLAN)
    turn_structure_errors.extend(_evaluate_turn_structure_rules(step_results, say_step_indices))

    return TurnEvalResult(
        turn_id=turn_steps[0].turn_id if turn_steps else -1,
        step_results=step_results,
        turn_structure_errors=turn_structure_errors,
        turn_tool_errors=[],
    )


def _collect_structure_errors(parsed: ParsedAction, is_first_step: bool) -> List[str]:
    errors: List[str] = []
    if "missing_think_block" in parsed.parse_errors:
        errors.append(STRUCTURE_MISSING_BLOCK)
    if parsed.think and parsed.think.end == -1:
        errors.append(STRUCTURE_INVALID_BLOCK_FORMAT)
    if parsed.plan and parsed.plan.end == -1:
        errors.append(STRUCTURE_INVALID_BLOCK_FORMAT)
    if "missing_action_block" in parsed.parse_errors:
        errors.append(STRUCTURE_MISSING_BLOCK)
    if "action_missing_close" in parsed.parse_errors:
        errors.append(STRUCTURE_INVALID_BLOCK_FORMAT)
    if parsed.extra_action_blocks > 0:
        errors.append(STRUCTURE_INVALID_BLOCK_FORMAT)
    if parsed.non_enclosed_segments:
        errors.append(STRUCTURE_UNEXPECTED_TEXT)
    if parsed.action_type is None:
        errors.append(STRUCTURE_MISSING_BLOCK)
    if parsed.action_type == "tool" and not parsed.action_name:
        errors.append(SYNTAX_ACTION_ATTRIBUTE_MISSING)
    if parsed.action_type == "say" and not parsed.action_body.strip():
        errors.append(STRUCTURE_MISSING_BLOCK)
    # Deduplicate while preserving order
    return list(dict.fromkeys(errors))


def _collect_tool_errors(parsed: ParsedAction, registry: ToolRegistry) -> List[str]:
    errors: List[str] = []
    if not registry.tools:
        return errors
    if not parsed.action_name:
        return errors
    if not registry.has_tool(parsed.action_name):
        errors.append(TOOL_INVALID_NAME)
        return errors
    tool_schema = registry.get_tool(parsed.action_name)
    if tool_schema is None:
        errors.append(TOOL_INVALID_NAME)
        return errors

    body_obj = parse_action_body_json(parsed.action_body)
    if body_obj is None:
        errors.append(TOOL_ILLEGAL_BODY_JSON)
        return errors

    # Check for unexpected args
    for arg_name in body_obj.keys():
        if not tool_schema.has_parameter(arg_name):
            errors.append(TOOL_UNKNOWN_ARG)

    # Check required args
    for required in tool_schema.required_parameters():
        if required not in body_obj:
            errors.append(TOOL_MISSING_REQUIRED_ARG)

    # Best-effort type validation
    for arg_name, value in body_obj.items():
        expected_type = tool_schema.parameter_type(arg_name)
        if expected_type is None:
            continue
        if not _value_matches_type(value, expected_type):
            errors.append(TOOL_ILLEGAL_VALUE_TYPE)

    return list(dict.fromkeys(errors))


def _value_matches_type(value, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int)
    if expected_type == "number":
        return isinstance(value, (int, float))
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    return True


def _evaluate_turn_structure_rules(
    step_results: List[StepEvalResult], say_step_indices: List[int]
) -> List[str]:
    errors: List[str] = []
    if not say_step_indices:
        errors.append(TURN_STRUCTURE_INVALID_SAY)
        return errors
    if len(say_step_indices) > 1:
        errors.append(TURN_STRUCTURE_INVALID_SAY)
        return errors
    last_index = len(step_results) - 1
    if say_step_indices[0] != last_index:
        errors.append(TURN_STRUCTURE_INVALID_SAY)
    return errors
