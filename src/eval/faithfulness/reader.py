from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List

from .models import StepEvidence


def _action_type(step: Dict[str, Any]) -> str:
    action = step.get("action_structured") or {}
    if isinstance(action, dict):
        return action.get("type", "")
    return ""


def load_faithfulness_evidence(conversation_path: Path) -> List[StepEvidence]:
    payload = json.loads(Path(conversation_path).read_text())
    messages: List[Dict[str, Any]] = payload.get("messages", []) or []
    conversation_id = (
        payload.get("meta", {}).get("conversation_id")
        or payload.get("config", {}).get("scenario_name")
        or ""
    )

    evidence: List[StepEvidence] = []
    history: List[Dict[str, Any]] = []

    for message in messages:
        role = message.get("role")

        if role != "assistant":
            history.append(copy.deepcopy(message))
            continue

        turn_id = message.get("turn_id")
        steps = message.get("steps") or []
        assistant_stub = {
            "role": "assistant",
            "turn_id": turn_id,
            "steps": [],
        }

        for step in steps:
            step_copy = copy.deepcopy(step)
            assistant_stub["steps"].append(step_copy)

            action = _action_type(step_copy)
            if action not in {"tool_call", "say"}:
                continue

            history_snapshot = [copy.deepcopy(item) for item in history]
            prior_steps = assistant_stub["steps"][:-1]
            if prior_steps:
                history_snapshot.append(
                    {
                        "role": "assistant",
                        "turn_id": turn_id,
                        "steps": copy.deepcopy(prior_steps),
                    }
                )

            evidence.append(
                StepEvidence(
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    step_index=step_copy.get("step_index", 0),
                    action_type="tool" if action == "tool_call" else "say",
                    history=history_snapshot,
                    current_step=step_copy,
                )
            )

        history.append(copy.deepcopy(message))

    return evidence
