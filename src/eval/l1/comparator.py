"""Comparison logic for L1 evaluation.

Implements conversation alignment and metric calculations including action
accuracy, tool selection F1, parameter F1 (with and without optional params),
and action recall. Provides both turn-level and conversation-level metrics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    Action,
    ConversationLevelMetrics,
    L1EvaluationResult,
    TurnMetrics,
)
from .reader import extract_actions, load_tool_registry


def normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, list):
        return tuple(normalize_value(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, normalize_value(v)) for k, v in value.items()))
    return value


def align_conversations(
    gold_actions: List[Action], test_actions: List[Action]
) -> Tuple[List[Tuple[Action, Optional[Action]]], List[str]]:
    aligned_pairs: List[Tuple[Action, Optional[Action]]] = []
    issues: List[str] = []

    gold_by_turn: Dict[int, List[Action]] = {}
    test_by_turn: Dict[int, List[Action]] = {}

    for action in gold_actions:
        gold_by_turn.setdefault(action.turn_id, []).append(action)
    for action in test_actions:
        test_by_turn.setdefault(action.turn_id, []).append(action)

    all_turn_ids = sorted(set(gold_by_turn.keys()) | set(test_by_turn.keys()))

    for turn_id in all_turn_ids:
        gold_turn = sorted(gold_by_turn.get(turn_id, []), key=lambda a: a.step_index)
        test_turn = sorted(test_by_turn.get(turn_id, []), key=lambda a: a.step_index)

        if len(gold_turn) != len(test_turn):
            issues.append(
                f"Turn {turn_id}: Step count mismatch (gold: {len(gold_turn)}, test: {len(test_turn)})"
            )

        max_steps = max(len(gold_turn), len(test_turn))
        for i in range(max_steps):
            gold_action = gold_turn[i] if i < len(gold_turn) else None
            test_action = test_turn[i] if i < len(test_turn) else None

            if gold_action is None:
                issues.append(f"Turn {turn_id}: Extra step at index {i+1} in test")
                continue
            if test_action is None:
                issues.append(f"Turn {turn_id}: Missing step at index {i+1} in test")
                aligned_pairs.append((gold_action, None))
            else:
                aligned_pairs.append((gold_action, test_action))

    return aligned_pairs, issues


def calculate_action_accuracy(
    aligned_pairs: List[Tuple[Action, Optional[Action]]]
) -> float:
    if not aligned_pairs:
        return 0.0

    correct = 0
    total = 0

    for gold_action, test_action in aligned_pairs:
        total += 1
        if test_action is not None and gold_action.action_type == test_action.action_type:
            correct += 1

    return correct / total if total > 0 else 0.0


def calculate_tool_selection_f1(
    aligned_pairs: List[Tuple[Action, Optional[Action]]]
) -> float:
    TP = 0
    FP = 0
    FN = 0

    for gold_action, test_action in aligned_pairs:
        if gold_action.action_type != "tool":
            continue

        if test_action is None:
            FN += 1
        elif test_action.action_type == "tool":
            if gold_action.tool_name == test_action.tool_name:
                TP += 1
            else:
                FP += 1
                FN += 1
        else:
            FN += 1

    precision = TP / (TP + FP) if (TP + FP) > 0 else 0.0
    recall = TP / (TP + FN) if (TP + FN) > 0 else 0.0
    f1 = (
        2 * (precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return f1


def calculate_parameter_f1(
    aligned_pairs: List[Tuple[Action, Optional[Action]]],
    include_optional: bool,
    tool_registry: Dict[str, Dict[str, Any]],
) -> float:
    TP = 0
    FP = 0
    FN = 0

    for gold_action, test_action in aligned_pairs:
        if (
            gold_action.action_type != "tool"
            or test_action is None
            or test_action.action_type != "tool"
            or gold_action.tool_name != test_action.tool_name
        ):
            continue

        tool_name = gold_action.tool_name
        if not tool_name or tool_name not in tool_registry:
            continue

        tool_info = tool_registry[tool_name]
        required_params = set(tool_info.get("required", []))
        optional_params = set(tool_info.get("optional", []))

        gold_params = gold_action.parameters or {}
        test_params = test_action.parameters or {}

        all_param_names = set(gold_params.keys()) | set(test_params.keys())

        for param_name in all_param_names:
            is_optional = param_name in optional_params

            if not include_optional and is_optional:
                continue

            gold_value = gold_params.get(param_name)
            test_value = test_params.get(param_name)

            gold_normalized = normalize_value(gold_value)
            test_normalized = normalize_value(test_value)

            if gold_value is not None and test_value is not None:
                if gold_normalized == test_normalized:
                    TP += 1
                else:
                    FN += 1
            elif gold_value is not None and test_value is None:
                FN += 1
            elif gold_value is None and test_value is not None:
                FP += 1

    precision = TP / (TP + FP) if (TP + FP) > 0 else 0.0
    recall = TP / (TP + FN) if (TP + FN) > 0 else 0.0
    f1 = (
        2 * (precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return f1


def calculate_action_recall(
    gold_actions: List[Action], test_actions: List[Action]
) -> float:
    gold_tool_actions = set()
    for action in gold_actions:
        if action.action_type == "tool":
            params_tuple = tuple(
                sorted(
                    (k, normalize_value(v))
                    for k, v in (action.parameters or {}).items()
                )
            )
            action_key = (action.turn_id, action.tool_name, params_tuple)
            gold_tool_actions.add(action_key)

    test_tool_actions = set()
    for action in test_actions:
        if action.action_type == "tool":
            params_tuple = tuple(
                sorted(
                    (k, normalize_value(v))
                    for k, v in (action.parameters or {}).items()
                )
            )
            action_key = (action.turn_id, action.tool_name, params_tuple)
            test_tool_actions.add(action_key)

    if not gold_tool_actions:
        return 1.0

    matching = gold_tool_actions & test_tool_actions
    return len(matching) / len(gold_tool_actions)


def calculate_turn_metrics(
    turn_id: int,
    gold_actions: List[Action],
    test_actions: List[Action],
    tool_registry: Dict[str, Dict[str, Any]],
) -> TurnMetrics:
    gold_turn_actions = [a for a in gold_actions if a.turn_id == turn_id]
    test_turn_actions = [a for a in test_actions if a.turn_id == turn_id]

    aligned_pairs, _ = align_conversations(gold_turn_actions, test_turn_actions)

    action_accuracy = calculate_action_accuracy(aligned_pairs)
    tool_selection_f1 = calculate_tool_selection_f1(aligned_pairs)
    parameter_f1_with_optional = calculate_parameter_f1(
        aligned_pairs, include_optional=True, tool_registry=tool_registry
    )
    parameter_f1_without_optional = calculate_parameter_f1(
        aligned_pairs, include_optional=False, tool_registry=tool_registry
    )
    action_recall = calculate_action_recall(gold_turn_actions, test_turn_actions)

    return TurnMetrics(
        turn_id=turn_id,
        action_accuracy=action_accuracy,
        tool_selection_f1=tool_selection_f1,
        parameter_f1_with_optional=parameter_f1_with_optional,
        parameter_f1_without_optional=parameter_f1_without_optional,
        action_recall=action_recall,
    )


def compare_conversations(
    gold_path: Path, test_path: Path
) -> L1EvaluationResult:
    with open(gold_path, "r") as f:
        gold_data = json.load(f)
    with open(test_path, "r") as f:
        test_data = json.load(f)

    conversation_id = (
        test_data.get("meta", {}).get("conversation_id")
        or test_data.get("config", {}).get("scenario_name")
        or ""
    )

    gold_actions = extract_actions(gold_data)
    test_actions = extract_actions(test_data)

    tool_registry = load_tool_registry(test_path)

    aligned_pairs, alignment_issues = align_conversations(gold_actions, test_actions)

    all_turn_ids = sorted(
        set(a.turn_id for a in gold_actions) | set(a.turn_id for a in test_actions)
    )

    turn_metrics_list: List[TurnMetrics] = []
    for turn_id in all_turn_ids:
        turn_metrics = calculate_turn_metrics(
            turn_id, gold_actions, test_actions, tool_registry
        )
        turn_metrics_list.append(turn_metrics)

    conversation_action_accuracy = calculate_action_accuracy(aligned_pairs)
    conversation_tool_f1 = calculate_tool_selection_f1(aligned_pairs)
    conversation_param_f1_with_opt = calculate_parameter_f1(
        aligned_pairs, include_optional=True, tool_registry=tool_registry
    )
    conversation_param_f1_without_opt = calculate_parameter_f1(
        aligned_pairs, include_optional=False, tool_registry=tool_registry
    )
    conversation_action_recall = calculate_action_recall(gold_actions, test_actions)

    conversation_level = ConversationLevelMetrics(
        action_accuracy=conversation_action_accuracy,
        tool_selection_f1=conversation_tool_f1,
        parameter_f1_with_optional=conversation_param_f1_with_opt,
        parameter_f1_without_optional=conversation_param_f1_without_opt,
        action_recall=conversation_action_recall,
    )

    return L1EvaluationResult(
        conversation_id=conversation_id,
        source_conversation_path=str(test_path),
        gold_conversation_path=str(gold_path),
        conversation_level=conversation_level,
        turn_level=turn_metrics_list,
        alignment_issues=alignment_issues,
    )

