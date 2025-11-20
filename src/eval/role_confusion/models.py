from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RoleConfusionContext:
    conversation_id: str
    user_messages: List[Dict[str, Any]]  # List of {turn_id, content} dicts


@dataclass
class RoleConfusionEvaluation:
    has_confusion: Optional[bool]  # True if user acted like assistant at any point
    reason: Optional[str]
    confused_turns: List[int] = field(default_factory=list)  # Turn IDs where confusion occurred
    raw_response: Any = None

