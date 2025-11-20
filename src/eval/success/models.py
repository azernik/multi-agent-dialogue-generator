from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCallEvidence:
    name: str
    args: Dict[str, Any]
    result: Any


@dataclass
class TranscriptTurn:
    turn_id: int
    user: str
    assistant: str
    tools: List[ToolCallEvidence] = field(default_factory=list)


@dataclass
class SuccessContext:
    conversation_id: str
    turns: List[TranscriptTurn]
    task_description: str
    task_slots: Dict[str, Any]
    impossible: bool = False
    fallback_behavior: Optional[str] = None
    success_criteria: Optional[Dict[str, Any]] = None


@dataclass
class SuccessEvaluation:
    success: Optional[bool]
    reason: Optional[str]
    raw_response: Any = None
