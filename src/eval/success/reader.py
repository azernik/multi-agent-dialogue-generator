from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import SuccessContext, TranscriptTurn, TranscriptToolEvent


def load_success_context(conversation_path: Path) -> SuccessContext:
    data = json.loads(Path(conversation_path).read_text())
    meta = data.get("meta", {})
    config = data.get("config", {})
    task = config.get("task", {}) or {}
    messages = data.get("messages", []) or []

    turns: List[TranscriptTurn] = []
    # Build map from turn_id to user text to pair with assistant
    user_text_by_turn: Dict[int, str] = {}
    assistant_steps: Dict[int, Dict[str, Any]] = {}

    for message in messages:
        turn_id = message.get("turn_id")
        if turn_id is None:
            continue
        role = message.get("role")
        if role == "user":
            user_text_by_turn[turn_id] = message.get("output_raw", "")
        elif role == "assistant":
            assistant_steps.setdefault(turn_id, message)

    for turn_id, assistant_entry in sorted(assistant_steps.items(), key=lambda kv: kv[0]):
        steps = assistant_entry.get("steps") or []
        say_text = ""
        tools: List[TranscriptToolEvent] = []
        for step in steps:
            action_structured = step.get("action_structured") or {}
            action_type = action_structured.get("type")
            if action_type == "say":
                say_text = action_structured.get("text", "").strip()
            elif action_type == "tool_call":
                name = action_structured.get("name") or "<unknown>"
                args = action_structured.get("args") or {}
                observation = step.get("observation") or {}
                result = observation.get("parsed", observation.get("raw"))
                tools.append(TranscriptToolEvent(name=name, args=args, result=result))
        user_text = user_text_by_turn.get(turn_id, "")
        turns.append(
            TranscriptTurn(
                turn_id=turn_id,
                user=user_text,
                assistant=say_text,
                tools=tools,
            )
        )

    return SuccessContext(
        conversation_id=meta.get("conversation_id") or config.get("scenario_name") or "",
        turns=turns,
        task_description=task.get("description", ""),
        task_slots=task.get("slots", {}) or {},
        impossible=bool(task.get("impossible")),
        fallback_behavior=task.get("fallback_behavior"),
    )
