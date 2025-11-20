from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from core import LLMClient
from .models import SuccessContext, SuccessEvaluation
from .reader import load_success_context

SUCCESS_PROMPT_TEMPLATE = """You are an evaluation assistant. Decide whether the assistant accomplished the user's task.

Task description:
{task_description}

Target slots:
{task_slots}
{success_criteria_section}
Task impossible: {impossible}
{fallback_section}

Conversation transcript:
{transcript}

Instructions:
{success_instructions}
1. Success means the assistant satisfied the task description using the target slots unless the task is marked impossible.
2. If the task is impossible, success requires the assistant to clearly communicate the impossibility and offer a gentle fallback (e.g., alternatives or next steps).
3. Base your decision only on the conversation transcript and tool outputs provided.
4. Respond ONLY with a JSON object like {{"success": true/false, "reason": "..."}}
"""


def _format_transcript(context: SuccessContext) -> str:
    lines: list[str] = []
    for turn in context.turns:
        if turn.user:
            lines.append(f"User (Turn {turn.turn_id}): {turn.user}")
        for tool_event in turn.tools:
            arg_text = json.dumps(tool_event.args, ensure_ascii=False)
            lines.append(f"Tool Call: {tool_event.name}{arg_text}")
            if tool_event.result is not None:
                result_text = json.dumps(tool_event.result, ensure_ascii=False)
                lines.append(f"Tool Result: {result_text}")
        if turn.assistant:
            lines.append(f"Assistant (Turn {turn.turn_id}): {turn.assistant}")
    return "\n".join(lines)


def _format_slots(slots: Dict[str, Any]) -> str:
    if not slots:
        return "(none)"
    return json.dumps(slots, ensure_ascii=False)


def evaluate_success(
    conversation_path: Path,
    *,
    model: str = "gpt-4.1-mini",
    api_key: Optional[str] = None,
) -> SuccessEvaluation:
    context = load_success_context(conversation_path)
    transcript_text = _format_transcript(context) or "(no conversation available)"
    fallback_section = ""
    if context.impossible:
        fb = context.fallback_behavior or "Explain clearly why the task is impossible and offer alternatives."
        fallback_section = f"Fallback behavior: {fb}\n"

    # Handle success_criteria if present
    success_criteria_section = ""
    success_instructions = ""
    if context.success_criteria:
        criteria_text = json.dumps(context.success_criteria, indent=2, ensure_ascii=False)
        success_criteria_section = f"\nSuccess criteria:\n{criteria_text}\n"
        target_selector = context.success_criteria.get('target_selector', {})
        action = context.success_criteria.get('action', '')
        notes = context.success_criteria.get('notes', '')
        
        # Build concrete instructions based on success_criteria
        instruction_parts = []
        if target_selector:
            selector_desc = ", ".join([f"{k}={v}" for k, v in target_selector.items()])
            instruction_parts.append(f"Check that the assistant worked with data matching: {selector_desc}")
        if action:
            instruction_parts.append(f"Verify that the assistant performed the action: {action}")
        if notes:
            instruction_parts.append(f"Note: {notes}")
        
        if instruction_parts:
            success_instructions = "0. " + " ".join(instruction_parts) + "\n"
    else:
        success_instructions = ""

    prompt = SUCCESS_PROMPT_TEMPLATE.format(
        task_description=context.task_description or "(not specified)",
        task_slots=_format_slots(context.task_slots),
        success_criteria_section=success_criteria_section,
        impossible=str(context.impossible).lower(),
        fallback_section=fallback_section,
        success_instructions=success_instructions,
        transcript=transcript_text,
    )

    client = LLMClient(model=model, api_key=api_key)
    response_text = client.chat_completion(
        messages=[{"role": "system", "content": "You are a precise evaluation assistant."}, {"role": "user", "content": prompt}],
        temperature=0,
    ).strip()

    try:
        parsed = json.loads(response_text)
        success_value = parsed.get("success")
        reason_value = parsed.get("reason")
    except Exception:
        parsed = None
        success_value = None
        reason_value = None

    return SuccessEvaluation(
        success=success_value if isinstance(success_value, bool) else None,
        reason=reason_value if isinstance(reason_value, str) else None,
        raw_response=parsed or response_text,
    )
