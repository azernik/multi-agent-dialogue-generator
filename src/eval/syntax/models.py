from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ToolParameterSpec:
    """Schema definition for a single tool parameter."""

    name: str
    required: bool
    type: Optional[str] = None
    description: Optional[str] = None


@dataclass
class ToolSchema:
    """Structured view of a tool definition."""

    name: str
    parameters: Dict[str, ToolParameterSpec] = field(default_factory=dict)

    def has_parameter(self, param_name: str) -> bool:
        return param_name in self.parameters

    def required_parameters(self) -> List[str]:
        return [name for name, spec in self.parameters.items() if spec.required]

    def parameter_type(self, param_name: str) -> Optional[str]:
        spec = self.parameters.get(param_name)
        return spec.type if spec else None


@dataclass
class ToolRegistry:
    """Registry holding all available tool schemas for a scenario."""

    tools: Dict[str, ToolSchema] = field(default_factory=dict)

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self.tools

    def get_tool(self, tool_name: str) -> Optional[ToolSchema]:
        return self.tools.get(tool_name)


@dataclass
class StepInput:
    """Assistant micro-step payload pulled from the conversation artifact."""

    turn_id: int
    micro_step_index: int
    content: str


@dataclass
class ConversationTurn:
    """Assistant turn containing one or more micro-steps."""

    turn_id: int
    steps: List[StepInput]


@dataclass
class ConversationArtifact:
    """Top-level artifact consumed by the evaluator."""

    conversation_id: str
    turns: List[ConversationTurn]
    tool_registry: ToolRegistry
    source_path: Optional[Path] = None


@dataclass
class StepEvalResult:
    """Per-step evaluation outcome."""

    micro_step_index: int
    structure_errors: List[str] = field(default_factory=list)
    tool_errors: List[str] = field(default_factory=list)

    @property
    def structure_valid(self) -> bool:
        return not self.structure_errors

    @property
    def tool_valid(self) -> bool:
        return not self.tool_errors


@dataclass
class TurnEvalResult:
    """Aggregated result for a single assistant turn."""

    turn_id: int
    step_results: List[StepEvalResult] = field(default_factory=list)
    turn_structure_errors: List[str] = field(default_factory=list)
    turn_tool_errors: List[str] = field(default_factory=list)

    @property
    def structure_valid(self) -> bool:
        if self.turn_structure_errors:
            return False
        return all(step.structure_valid for step in self.step_results)

    @property
    def tool_valid(self) -> bool:
        if self.turn_tool_errors:
            return False
        return all(step.tool_valid for step in self.step_results)


@dataclass
class CategorySummary:
    """Summary stats for a single category (structure/tool)."""

    valid: bool
    pass_rate: float
    failure_counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class ConversationEvalResult:
    """Top-level evaluation output."""

    conversation_id: str
    turns: List[TurnEvalResult]
    total_turns: int
    structure_summary: CategorySummary
    tool_summary: CategorySummary
    source_path: Optional[Path] = None
    conversation_checks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result for reporting."""
        return {
            "conversation_id": self.conversation_id,
            "source_path": str(self.source_path) if self.source_path else None,
            "total_turns": self.total_turns,
            "turns": self._serialize_error_turns(),
            "summary": {
                "structure": {
                    "valid": self.structure_summary.valid,
                    "pass_rate": self.structure_summary.pass_rate,
                    "failure_counts": self.structure_summary.failure_counts,
                },
                "tool": {
                    "valid": self.tool_summary.valid,
                    "pass_rate": self.tool_summary.pass_rate,
                    "failure_counts": self.tool_summary.failure_counts,
                },
            },
            "conversation_checks": self.conversation_checks,
        }

    def _serialize_error_turns(self) -> List[Dict[str, Any]]:
        error_turns: List[Dict[str, Any]] = []
        for turn in self.turns:
            if turn.structure_valid and turn.tool_valid:
                continue
            turn_payload: Dict[str, Any] = {
                "turn_id": turn.turn_id,
            }
            step_entries = []
            for step in turn.step_results:
                entry: Dict[str, Any] = {"micro_step_index": step.micro_step_index}
                if step.structure_errors:
                    entry["structure_errors"] = step.structure_errors
                if step.tool_errors:
                    entry["tool_errors"] = step.tool_errors
                if len(entry) > 1:
                    step_entries.append(entry)
            if step_entries:
                turn_payload["steps"] = step_entries
            if turn.turn_structure_errors:
                turn_payload["turn_structure_errors"] = turn.turn_structure_errors
            if turn.turn_tool_errors:
                turn_payload["turn_tool_errors"] = turn.turn_tool_errors
            turn_payload["structure_valid"] = turn.structure_valid
            turn_payload["tool_valid"] = turn.tool_valid
            error_turns.append(turn_payload)
        return error_turns
