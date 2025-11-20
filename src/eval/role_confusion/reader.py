from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .models import RoleConfusionContext


def load_role_confusion_context(conversation_path: Path) -> RoleConfusionContext:
    """Extract user messages from conversation.json for role confusion evaluation."""
    data = json.loads(Path(conversation_path).read_text())
    meta = data.get("meta", {})
    messages = data.get("messages", []) or []

    user_messages: List[Dict[str, Any]] = []
    
    for message in messages:
        role = message.get("role")
        turn_id = message.get("turn_id")
        
        if role == "user" and turn_id is not None:
            user_messages.append({
                "turn_id": turn_id,
                "content": message.get("output_raw", "").strip()
            })

    return RoleConfusionContext(
        conversation_id=meta.get("conversation_id") or data.get("config", {}).get("scenario_name") or "",
        user_messages=user_messages,
    )

