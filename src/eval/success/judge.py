from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from core import LLMClient
from .models import SuccessContext, SuccessEvaluation
from .reader import load_success_context

SUCCESS_PROMPT_TEMPLATE = """You are an evaluation assistant. Decide whether the assistant accomplished the user's task.

Task objective:
{task_objective}

Target slots:
{task_slots}
{success_criteria_section}
Task impossible: {impossible}
{fallback_section}

Conversation transcript:
{transcript}

Instructions:
{success_instructions}
1. If success criteria are provided above, treat them as the primary definition of success. Otherwise, use the task objective and target slots to infer what success requires.
2. Treat tool call results and their parsed outputs as authoritative ground truth about what actually happened in the environment.
3. When comparing times, dates, numeric values, or other quantities, consider two representations equivalent if they refer to the same underlying value (for example, 14:00Z and 06:00 Pacific for the same instant, or 249.99 and "249.99" for the same amount). Do not mark the conversation as a failure just because the assistant used a different but equivalent format or time zone.
4. Base your decision only on the conversation transcript and tool outputs provided.
5. Respond ONLY with a JSON object like {{"success": true/false, "reason": "..."}}
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
    model: str = "gpt-5.1",
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

    # Add guidance about constraints vs preferences when the task slots use that structure.
    slots = context.task_slots or {}
    constraints = slots.get("constraints") if isinstance(slots, dict) else None
    preferences = slots.get("preferences") if isinstance(slots, dict) else None
    constraints_prefs_instructions_parts: list[str] = []
    if isinstance(constraints, dict) and constraints:
        constraints_prefs_instructions_parts.append(
            "Treat the fields under 'constraints' in Target slots as hard requirements that must be satisfied for success, "
            "unless the user explicitly agrees to change or relax them. "
        )
    if isinstance(preferences, dict) and preferences:
        constraints_prefs_instructions_parts.append(
            "Treat the fields under 'preferences' in Target slots as soft preferences: the assistant should try to satisfy them, "
            "but it is acceptable to relax them if no option satisfies all constraints, as long as trade-offs are explained and the user agrees. "
        )
    if constraints_prefs_instructions_parts:
        success_instructions += "".join(constraints_prefs_instructions_parts)

    prompt = SUCCESS_PROMPT_TEMPLATE.format(
        task_objective=context.task_objective or "(not specified)",
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
