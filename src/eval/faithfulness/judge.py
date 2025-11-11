from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import LLMClient

from .models import FaithfulnessFinding, FaithfulnessReport
from .reader import load_faithfulness_evidence

PROMPT_TEMPLATE = """You are an expert in conversational agents, specializing in LLM hallucinations.

TASK
Given a conversation context and the system agent's current output, assess whether the current output is faithful to the conversation context up to this point.

CONTEXT
1. Tool definitions: {tools_json}
2. Message history: {history_json}
3. Current step: {current_step_json}

INSTRUCTIONS
{instruction_block}

SCRATCHPAD
Before you output your answer, use a private scratchpad to reason aloud about the task. Do not include the scratchpad in your final answer. If user inputs vs. tool outputs are in different formats, e.g. 24-hour time vs. 12-hour time, normalize the formats before comparing them.

OUTPUT
Respond with JSON only (no code fences, no commentary). Keep your reason short and concrete.
{{
  "reason": "<short justification>"
  "result": true | false,
}}

Example (faithful):
{{"reason": "Summarizes the tool results accurately.", "result": true}}

Example (not faithful):
{{"reason": "Searches for a cuisine type, Italian, that is not compatible with the user's current preferences (American).", "result": false}}

SAMPLE TO EVALUATE
{sample_blob}

RESPONSE"""

TOOL_INSTRUCTIONS = (
    "Evaluate whether the parameter values passed in the tool call are compatible with the user's current intent. "
    "Allow justified relaxations or deviations from the user's literal inputs if they can be explained by prior observations and don't clearly contradict the user's preferences. "
    "Return false only when the parameter values have no basis in the conversation context or clearly contradict the user's current preferences."
)

SAY_INSTRUCTIONS = (
    "Evaluate whether the agent's user-facing utterance accurately reflects the latest tool call results. "
    "Allow formatting differences or unit conversions. "
    "Any domain-specific information relayed from the agent to the user in the context of a user query must be grounded in tool responses from the current conversation, even if it could have plausibly been in the agent's pre-training data. "
    "Return false only when the assistant introduces domain-specific information that is not grounded in tool responses from the current conversation, introduces unsupported facts, or alters tool data."
)


def evaluate_faithfulness(
    conversation_path: Path,
    *,
    tool_definitions: Optional[Dict[str, Any]] = None,
    model: str = "gpt-4.1-mini",
    api_key: Optional[str] = None,
) -> FaithfulnessReport:
    evidence_list = load_faithfulness_evidence(conversation_path)
    client = LLMClient(model=model, api_key=api_key)
    tools_payload = tool_definitions or {}
    tools_json = json.dumps(tools_payload, ensure_ascii=False, indent=2)

    findings: List[FaithfulnessFinding] = []

    for evidence in evidence_list:
        history_json = json.dumps(evidence.history, ensure_ascii=False, indent=2)
        current_step_json = json.dumps(evidence.current_step, ensure_ascii=False, indent=2)
        sample_blob = json.dumps(
            {
                "tools": tools_payload,
                "messages": evidence.history,
                "current_step": evidence.current_step,
            },
            ensure_ascii=False,
            indent=2,
        )
        instruction_block = TOOL_INSTRUCTIONS if evidence.action_type == "tool" else SAY_INSTRUCTIONS

        prompt = PROMPT_TEMPLATE.format(
            tools_json=tools_json,
            history_json=history_json,
            current_step_json=current_step_json,
            instruction_block=instruction_block,
            sample_blob=sample_blob,
        )

        raw_response = client.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You are a strict grader. Reply with raw JSON only—no code fences, no prefacing text.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        ).strip()

        try:
            parsed = json.loads(raw_response)
            result = bool(parsed.get("result"))
            reason = parsed.get("reason") or ""
        except json.JSONDecodeError:
            result = False
            reason = f"Invalid JSON response: {raw_response}"

        issues: List[Dict[str, str]] = []
        if not result:
            label = "slot_value_faithfulness" if evidence.action_type == "tool" else "tool_summary_faithfulness"
            issues.append({"type": label, "reason": reason})

        findings.append(
            FaithfulnessFinding(
                turn_id=evidence.turn_id,
                step_index=evidence.step_index,
                action_type=evidence.action_type,
                issues=issues,
            )
        )

    conversation_id = evidence_list[0].conversation_id if evidence_list else ""
    return FaithfulnessReport(conversation_id=conversation_id, findings=findings)
