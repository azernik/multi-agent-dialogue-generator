from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import LLMClient
from .models import RoleConfusionEvaluation
from .reader import load_role_confusion_context

PROMPT_TEMPLATE = """You are an evaluation assistant. Check whether the user agent in this conversation ever confused its role and started acting like the assistant.

ROLE BOUNDARY:
- The USER is the person asking for help, answering questions, and providing information when asked
- The ASSISTANT is the chatbot that asks questions, offers help, confirms details, and provides recommendations

SIGNS OF ROLE CONFUSION (user acting like assistant) - ONLY flag these:
- User asks questions TO the assistant as if the assistant were the user: "Could you please provide...", "What's your...", "Anything else I should know?", "Can you confirm...?"
- User offers to help the assistant: "Let me know if there's anything else I can provide", "Just let me know if you need anything"
- User confirms details FOR the assistant: "Just to confirm, you want to...", "So you want to track...", "To confirm, you're looking for..."
- User provides recommendations or options to the assistant
- User acts like they are helping the assistant complete a task

NORMAL USER BEHAVIOR (NOT confusion - do NOT flag):
- User thanks the assistant: "Thanks!", "Thank you!", "Thanks for the info!"
- User answers questions asked by the assistant
- User provides information when asked
- User makes requests: "I want to track an order", "Can you help me..."
- User asks follow-up questions about THEIR OWN needs: "What's the return process?", "How do I cancel?", "When will it arrive?"
- User expresses preferences or makes decisions
- User acknowledges information: "Got it", "That's great", "Perfect"

CRITICAL: Only flag if the user is clearly acting like an ASSISTANT (asking questions TO help the assistant, offering to help the assistant, confirming details FOR the assistant). Normal polite responses, thanks, and questions about the user's own needs are NOT role confusion.

Conversation (user messages only):
{user_messages}

Instructions:
1. Check if the user EVER acted like an assistant (asked questions TO help the assistant, offered to help the assistant, confirmed details FOR the assistant)
2. If confusion occurred, identify which turn(s) showed the confusion
3. Respond ONLY with a JSON object like {{"has_confusion": true/false, "reason": "...", "confused_turns": [turn_ids]}}
4. If no confusion, set has_confusion to false and confused_turns to []
5. Be strict - only flag clear cases where user is acting like an assistant, not normal polite user behavior
"""


def _format_user_messages(user_messages: List[Dict[str, Any]]) -> str:
    """Format user messages for the prompt."""
    lines = []
    for msg in user_messages:
        turn_id = msg.get("turn_id", "?")
        content = msg.get("content", "")
        lines.append(f"Turn {turn_id}: {content}")
    return "\n".join(lines) if lines else "(no user messages)"


def evaluate_role_confusion(
    conversation_path: Path,
    *,
    model: str = "gpt-4.1-mini",
    api_key: Optional[str] = None,
) -> RoleConfusionEvaluation:
    """Evaluate whether the user agent confused its role and acted like an assistant."""
    context = load_role_confusion_context(conversation_path)
    
    if not context.user_messages:
        return RoleConfusionEvaluation(
            has_confusion=False,
            reason="No user messages found in conversation",
            confused_turns=[],
        )
    
    user_messages_text = _format_user_messages(context.user_messages)
    
    prompt = PROMPT_TEMPLATE.format(user_messages=user_messages_text)
    
    client = LLMClient(model=model, api_key=api_key)
    response_text = client.chat_completion(
        messages=[
            {"role": "system", "content": "You are a precise evaluation assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
    ).strip()
    
    try:
        parsed = json.loads(response_text)
        has_confusion = parsed.get("has_confusion")
        reason = parsed.get("reason")
        confused_turns = parsed.get("confused_turns", [])
        
        # Ensure confused_turns is a list of integers
        if isinstance(confused_turns, list):
            confused_turns = [int(t) for t in confused_turns if isinstance(t, (int, str)) and str(t).isdigit()]
        else:
            confused_turns = []
    except Exception:
        parsed = None
        has_confusion = None
        reason = None
        confused_turns = []
    
    return RoleConfusionEvaluation(
        has_confusion=has_confusion if isinstance(has_confusion, bool) else None,
        reason=reason if isinstance(reason, str) else None,
        confused_turns=confused_turns,
        raw_response=parsed or response_text,
    )

