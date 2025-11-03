from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ParsedSection:
    tag: str
    start: int
    end: int
    content: str


@dataclass
class ParsedAction:
    """Structured representation of an assistant micro-step."""

    think: Optional[ParsedSection] = None
    plan: Optional[ParsedSection] = None
    action: Optional[ParsedSection] = None
    action_type: Optional[str] = None
    action_name: Optional[str] = None
    action_body: str = ""
    extra_action_blocks: int = 0
    non_enclosed_segments: List[str] = field(default_factory=list)
    parse_errors: List[str] = field(default_factory=list)

    def has_plan(self) -> bool:
        return self.plan is not None

    def has_action(self) -> bool:
        return self.action is not None


ACTION_OPEN_RE = re.compile(r"<action\b([^>]*)>", re.IGNORECASE)
ACTION_CLOSE_RE = re.compile(r"</action>", re.IGNORECASE)
TAG_RE = re.compile(r"<(/?)(\w+)[^>]*>")


def _extract_tag(text: str, tag: str) -> Optional[ParsedSection]:
    """Find first occurrence of <tag>...</tag> and return section info."""
    open_tag = f"<{tag}>"
    close_tag = f"</{tag}>"
    start = text.find(open_tag)
    if start == -1:
        return None
    content_start = start + len(open_tag)
    end = text.find(close_tag, content_start)
    if end == -1:
        return ParsedSection(tag=tag, start=start, end=-1, content=text[content_start:])
    return ParsedSection(tag=tag, start=start, end=end + len(close_tag), content=text[content_start:end])


def _strip_prefix(text: str, prefix_len: int) -> str:
    return text[prefix_len:].lstrip() if prefix_len > 0 else text


def parse_action_blocks(raw: str) -> ParsedAction:
    """Parse think/plan/action blocks from the assistant output."""
    parsed = ParsedAction()
    working = raw.strip("\n")

    think = _extract_tag(working, "think")
    if think:
        parsed.think = think
        before_think = working[: think.start]
        if before_think.strip():
            parsed.non_enclosed_segments.append(before_think)
        working_after_think = working[think.end :]
    else:
        parsed.parse_errors.append("missing_think_block")
        working_after_think = working

    # Attempt to extract plan from remaining text
    plan = _extract_tag(working_after_think, "plan")
    if plan:
        parsed.plan = plan
        between = working_after_think[: plan.start]
        if between.strip():
            parsed.non_enclosed_segments.append(between)
        working_after_plan = working_after_think[plan.end :]
    else:
        working_after_plan = working_after_think

    # Parse action blocks explicitly
    action_matches = list(ACTION_OPEN_RE.finditer(working_after_plan))
    if not action_matches:
        parsed.parse_errors.append("missing_action_block")
        if working_after_plan.strip():
            parsed.non_enclosed_segments.append(working_after_plan)
        return parsed

    parsed.extra_action_blocks = max(0, len(action_matches) - 1)
    first_match = action_matches[0]
    action_start = first_match.start()
    action_open_end = first_match.end()
    close_match = ACTION_CLOSE_RE.search(working_after_plan, action_open_end)
    if not close_match:
        parsed.parse_errors.append("action_missing_close")
        action_body = working_after_plan[action_open_end:]
        action_end = len(working_after_plan)
    else:
        action_end = close_match.end()
        action_body = working_after_plan[action_open_end : close_match.start()]
        # Capture trailing content after </action>
        tail = working_after_plan[close_match.end() :]
        if tail.strip():
            parsed.non_enclosed_segments.append(tail)

    header = first_match.group(1)
    action_section = ParsedSection(
        tag="action",
        start=think.end + action_start if think else action_start,
        end=think.end + action_end if think else action_end,
        content=working_after_plan[action_start:action_end],
    )
    parsed.action = action_section
    parsed.action_body = action_body.strip()

    # Parse attributes from header
    attributes = _parse_action_attributes(header)
    parsed.action_type = attributes.get("type")
    parsed.action_name = attributes.get("name")

    between_plan_action = working_after_plan[:action_start]
    if between_plan_action.strip():
        parsed.non_enclosed_segments.append(between_plan_action)

    return parsed


def _parse_action_attributes(raw_header: str) -> dict:
    attrs: dict = {}
    for match in re.finditer(r'(\w+)\s*=\s*"([^"]*)"', raw_header or ""):
        key, value = match.group(1), match.group(2)
        attrs[key] = value
    return attrs


def parse_action_body_json(body: str) -> Optional[dict]:
    """Parse action body JSON if possible."""
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None
