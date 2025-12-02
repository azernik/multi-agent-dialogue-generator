"""Data models for L1 evaluation results.

Defines data classes for representing actions, turn-level metrics,
conversation-level metrics, and complete L1 evaluation results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Action:
    turn_id: int
    step_index: int
    action_type: str
    tool_name: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


@dataclass
class TurnMetrics:
    turn_id: int
    action_accuracy: float
    tool_selection_f1: float
    parameter_f1_with_optional: float
    parameter_f1_without_optional: float
    action_recall: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "action_accuracy": self.action_accuracy,
            "tool_selection_f1": self.tool_selection_f1,
            "parameter_f1_with_optional": self.parameter_f1_with_optional,
            "parameter_f1_without_optional": self.parameter_f1_without_optional,
            "action_recall": self.action_recall,
        }


@dataclass
class ConversationLevelMetrics:
    action_accuracy: float
    tool_selection_f1: float
    parameter_f1_with_optional: float
    parameter_f1_without_optional: float
    action_recall: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_accuracy": self.action_accuracy,
            "tool_selection_f1": self.tool_selection_f1,
            "parameter_f1_with_optional": self.parameter_f1_with_optional,
            "parameter_f1_without_optional": self.parameter_f1_without_optional,
            "action_recall": self.action_recall,
        }


@dataclass
class L1EvaluationResult:
    conversation_id: str
    source_conversation_path: str
    gold_conversation_path: str
    conversation_level: ConversationLevelMetrics
    turn_level: List[TurnMetrics]
    alignment_issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "source_conversation_path": self.source_conversation_path,
            "gold_conversation_path": self.gold_conversation_path,
            "conversation_level": self.conversation_level.to_dict(),
            "turn_level": [tm.to_dict() for tm in self.turn_level],
            "alignment_issues": self.alignment_issues,
        }

