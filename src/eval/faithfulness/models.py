from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal

ActionType = Literal["tool", "say"]


@dataclass
class StepEvidence:
    conversation_id: str
    turn_id: int
    step_index: int
    action_type: ActionType
    history: List[Dict[str, Any]]
    current_step: Dict[str, Any]


@dataclass
class FaithfulnessFinding:
    turn_id: int
    step_index: int
    action_type: ActionType
    issues: List[Dict[str, str]] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.issues


@dataclass
class FaithfulnessReport:
    conversation_id: str
    findings: List[FaithfulnessFinding]

    @property
    def valid(self) -> bool:
        return all(f.is_clean for f in self.findings)

    @property
    def pass_rate(self) -> float:
        if not self.findings:
            return 1.0
        clean = sum(1 for f in self.findings if f.is_clean)
        return clean / len(self.findings)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "error_turns": [
                {
                    "turn_id": f.turn_id,
                    "step_index": f.step_index,
                    "action_type": f.action_type,
                    "issues": f.issues,
                }
                for f in self.findings
                if not f.is_clean
            ],
            "summary": {
                "valid": self.valid,
                "pass_rate": self.pass_rate,
            },
        }
