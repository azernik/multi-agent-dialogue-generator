from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from copy import deepcopy
import json
import logging
from core import Message, MessageRole, ConversationContext
from agents import SystemAgent, UserAgent, ToolAgent
from scenario import ExampleScenario

@dataclass
class ConversationResult:
    system_transcript: List[Message]    # Full system agent conversation (PRIMARY)
    user_transcript: List[Message]      # User agent's clean conversation
    tool_transcript: List[Message]      # Tool agent's call/response history
    metadata: Dict[str, Any]
    success: bool
    termination_reason: str
    turn_traces: List[Dict[str, Any]] = None

DEFAULT_SYSTEM_GREETING = "Hi there! How can I help you today?"


class ConversationRunner:
    def __init__(self, 
                 scenario: ExampleScenario,
                 system_agent: SystemAgent,
                 user_agent: UserAgent, 
                 tool_agent: ToolAgent,
                 max_turns: int = 20,
                 persona: Optional[Dict[str, Any]] = None,
                 task_override: Optional[Dict[str, Any]] = None,
                 system_greeting: Optional[str] = DEFAULT_SYSTEM_GREETING):
        self.scenario = scenario
        self.system_agent = system_agent
        self.user_agent = user_agent
        self.tool_agent = tool_agent
        self.max_turns = max_turns
        self.persona = persona
        self.task_context = task_override or scenario.task
        self.logger = logging.getLogger(__name__)
        
        # Three separate conversation histories
        self.user_history: List[Message] = []
        self.system_history: List[Message] = []
        self.tool_history: List[Message] = []
        # Aggregated per-system-turn traces for training/export
        self.turn_traces: List[Dict[str, Any]] = []

        # Logging disabled for cleaner output - only agent responses are logged

        if system_greeting:
            greeting_msg = Message(
                MessageRole.ASSISTANT,
                system_greeting,
                metadata={"turn_id": 0, "system_greeting": True}
            )
            self.system_history.append(greeting_msg)
            self.user_history.append(greeting_msg)
        
    def run_conversation(self) -> ConversationResult:
        had_tool_calls = False
        
        for turn in range(self.max_turns):
            user_message = self.process_user_turn(turn)
            termination_result = self.check_termination(user_message, turn)
            if termination_result:
                termination_reason, success = termination_result
                # Termination logged silently - check result for details
                return ConversationResult(
                    system_transcript=self.system_history.copy(),
                    user_transcript=self.user_history.copy(),
                    tool_transcript=self.tool_history.copy(),
                    metadata={
                        "total_turns": turn + 1,
                        "scenario": self.scenario.name,
                        "had_tool_calls": had_tool_calls,
                        "persona_id": self.persona.get('id') if self.persona else None
                    },
                    success=success,
                    termination_reason=termination_reason,
                    turn_traces=self.turn_traces.copy()
                )
            
            system_message, had_tool_call = self.process_system_turn(turn)
            if had_tool_call:
                had_tool_calls = True
            termination_result = self.check_termination(system_message, turn)
            if termination_result:
                termination_reason, success = termination_result
                # Termination logged silently - check result for details
                return ConversationResult(
                    system_transcript=self.system_history.copy(),
                    user_transcript=self.user_history.copy(),
                    tool_transcript=self.tool_history.copy(),
                    metadata={
                        "total_turns": turn + 1,
                        "scenario": self.scenario.name,
                        "had_tool_calls": had_tool_calls,
                        "persona_id": self.persona.get('id') if self.persona else None
                    },
                    success=success,
                    termination_reason=termination_reason,
                    turn_traces=self.turn_traces.copy()
                )
        
        return ConversationResult(
            system_transcript=self.system_history.copy(),
            user_transcript=self.user_history.copy(),
            tool_transcript=self.tool_history.copy(),
            metadata={
                "total_turns": self.max_turns,
                "scenario": self.scenario.name,
                "had_tool_calls": had_tool_calls,
                "persona_id": self.persona.get('id') if self.persona else None
            },
            success=False,
            termination_reason="max_turns_reached",
            turn_traces=self.turn_traces.copy()
        )
        
    def process_user_turn(self, turn_number: int) -> Message:
        user_context = self.build_user_context(turn_number)
        user_response = self.user_agent.generate_response(user_context)
        self.logger.info(f"\nuser_agent response: {user_response}\n")
        turn_id = turn_number + 1
        user_message = Message(MessageRole.USER, user_response, metadata={"turn_id": turn_id})
        self.user_history.append(user_message)
        self.system_history.append(user_message)
        return user_message
        
    def process_system_turn(self, turn_number: int) -> Tuple[Message, bool]:
        had_tool_call = False
        # Accumulators for this system turn
        pre_turn_user_history = [
            { 'role': msg.role.value, 'content': msg.content }
            for msg in self.user_history
        ]
        system_messages_raw: List[str] = []
        actions_structured: List[Dict[str, Any]] = []
        tool_results: List[str] = []
        steps: List[Dict[str, Any]] = []
        turn_id = turn_number + 1
        while True:
            # Build context and get assistant output for the current micro-step
            system_context = self.build_system_context(turn_number)
            system_response = self.system_agent.generate_response(system_context)
            self.logger.info(f"\nsystem_agent response: {system_response}\n")
            system_messages_raw.append(system_response)
            if self.has_tool_call(system_response):
                had_tool_call = True
                self.system_history.append(
                    Message(MessageRole.ASSISTANT, system_response, metadata={
                        'turn_id': turn_id,
                        'micro_step_index': len(steps)
                    })
                )
                # Record the tool call line in actions_structured
                tool_call_only = self.extract_tool_call(system_response)
                if tool_call_only:
                    actions_structured.append({ 'type': 'tool_call', 'raw': tool_call_only })
                tool_result = self.process_tool_call(system_response, turn_number)
                self.system_history.append(
                    Message(MessageRole.TOOL, tool_result, metadata={
                        'turn_id': turn_id,
                        'micro_step_index': len(steps)
                    })
                )
                tool_results.append(tool_result)
                # Normalize tool call for structured action (best-effort)
                action_name, action_args = self._normalize_tool_call(tool_call_only)
                # Append structured step (tool)
                steps.append({
                    'step_index': len(steps) + 1,
                    'output_raw': system_response,
                    'action_structured': {
                        'type': 'tool_call',
                        **({ 'name': action_name } if action_name else {}),
                        **({ 'args': action_args } if action_args is not None else {}),
                        'raw': tool_call_only
                    },
                    'observation': self._build_observation(tool_result)
                })
                continue
            else:
                user_facing_message = self.system_agent.get_user_facing_message(system_response)
                system_message = Message(MessageRole.ASSISTANT, user_facing_message, metadata={'turn_id': turn_id})
                full_system_message = Message(
                    MessageRole.ASSISTANT,
                    system_response,
                    metadata={
                        'turn_id': turn_id,
                        'micro_step_index': len(steps)
                    }
                )
                self.user_history.append(system_message)
                self.system_history.append(full_system_message)
                # Record final say action
                actions_structured.append({ 'type': 'say', 'text': user_facing_message })
                # Append structured step (say)
                steps.append({
                    'step_index': len(steps) + 1,
                    'output_raw': system_response,
                    'action_structured': { 'type': 'say', 'text': user_facing_message },
                    'observation': None
                })
                # Build turn trace for export (new minimal schema)
                last_user_text = self.user_history[-2].content if len(self.user_history) >= 2 else ''
                turn_trace: Dict[str, Any] = {
                    'turn_id': turn_id,
                    'user': last_user_text,
                    'assistant': {
                        'steps': steps
                    },
                    'termination': {
                        'final_in_conversation': ('[DONE_SUCCESS]' in user_facing_message) or ('[DONE_FAILURE]' in user_facing_message)
                    }
                }
                self.turn_traces.append(turn_trace)
            return system_message, had_tool_call
        
    def process_tool_call(self, system_response: str, turn_number: int) -> str:
        tool_context = self.build_tool_context(system_response, turn_number)
        tool_result = self.tool_agent.generate_response(tool_context)
        self.logger.info(f"\ntool_agent response: {tool_result}\n")
        tool_call_only = self.extract_tool_call(system_response)
        self.tool_history.append(Message(MessageRole.USER, tool_call_only))
        self.tool_history.append(Message(MessageRole.ASSISTANT, tool_result))
        return tool_result
        
    def check_termination(self, last_message: Message, turn_number: int) -> Optional[Tuple[str, bool]]:
        if last_message.role == MessageRole.USER:
            content = last_message.content
            if '[DONE_SUCCESS]' in content:
                return ("user_task_complete", True)
            elif '[DONE_FAILURE]' in content:
                return ("user_task_complete", False)
        if turn_number >= self.max_turns - 1:
            return ("max_turns_reached", False)
        return None
        
    def build_user_context(self, turn_number: int) -> ConversationContext:
        ua = self._enrich_behaviors(self.scenario.user_agent, self.scenario.behavior_types)
        ua = dict(ua)
        if self.task_context:
            ua['task'] = deepcopy(self.task_context)
            task_slots = self.task_context.get('slots', {})
            if task_slots:
                ua.setdefault('slots', deepcopy(task_slots))
            task_desc = self.task_context.get('description')
            if task_desc:
                ua.setdefault('objective', task_desc)
        if self.persona:
            ua['persona'] = deepcopy(self.persona)
        return ConversationContext(
            messages=self.user_history,
            agent_config=ua,
            turn_number=turn_number
        )
        
    def build_system_context(self, turn_number: int) -> ConversationContext:
        return ConversationContext(
            messages=self.system_history,
            agent_config={"tools": self.scenario.tools},
            turn_number=turn_number
        )
        
    def build_tool_context(self, system_response: str, turn_number: int) -> ConversationContext:
        tool_call_only = self.extract_tool_call(system_response)
        current_tool_call = Message(MessageRole.USER, tool_call_only)
        tool_context_messages = self.tool_history + [current_tool_call]
        ta_cfg = self._enrich_behaviors({"injected_behaviors": self.scenario.tool_agent.get('injected_behaviors', [])}, self.scenario.behavior_types)
        
        # Include scenario context: task slots and tool_agent seed data (if present)
        scenario_context = {}
        if self.task_context and self.task_context.get('slots'):
            scenario_context['task_slots'] = self.task_context['slots']
        tool_agent_context = self.scenario.tool_agent.get('context', {})
        if tool_agent_context.get('seed'):
            scenario_context['seed_data'] = tool_agent_context['seed']
        
        agent_config = {
            "tools": self.scenario.tools,
            "tool_agent": ta_cfg,
            "scenario_context": scenario_context if scenario_context else None
        }
        return ConversationContext(
            messages=tool_context_messages,
            agent_config=agent_config,
            turn_number=turn_number
        )

    def build_tool_context_from_call(self, tool_call: str, turn_number: int) -> ConversationContext:
        current_tool_call = Message(MessageRole.USER, tool_call)
        tool_context_messages = self.tool_history + [current_tool_call]
        ta_cfg = self._enrich_behaviors({"injected_behaviors": self.scenario.tool_agent.get('injected_behaviors', [])}, self.scenario.behavior_types)
        
        # Include scenario context: task slots and tool_agent seed data (if present)
        scenario_context = {}
        if self.task_context and self.task_context.get('slots'):
            scenario_context['task_slots'] = self.task_context['slots']
        tool_agent_context = self.scenario.tool_agent.get('context', {})
        if tool_agent_context.get('seed'):
            scenario_context['seed_data'] = tool_agent_context['seed']
        
        agent_config = {
            "tools": self.scenario.tools,
            "tool_agent": ta_cfg,
            "scenario_context": scenario_context if scenario_context else None
        }
        return ConversationContext(
            messages=tool_context_messages,
            agent_config=agent_config,
            turn_number=turn_number
        )
    
    def _enrich_behaviors(self, cfg: Dict[str, Any], behavior_types: Dict[str, Any]) -> Dict[str, Any]:
        cfg = dict(cfg) if cfg else {}
        enriched: List[Dict[str, Any]] = []
        for b in cfg.get('injected_behaviors', []) or []:
            btype = behavior_types.get(b.get('type_id')) if isinstance(b, dict) else None
            if btype:
                enriched.append({
                    **b,
                    "type_description": btype.get('description', '')
                })
            else:
                enriched.append(b)
        if enriched:
            cfg['injected_behaviors'] = enriched
        return cfg
        
    def has_tool_call(self, system_response: str) -> bool:
        """Detect whether the assistant emitted a tool call.
        Prefer explicit <action type="tool" ...> tags; else fallback to heuristic.
        """
        if self._parse_action_tag(system_response).get('type') == 'tool':
            return True
        text = system_response or ""
        # Prefer the action section after </plan>
        plan_end = text.rfind('</plan>')
        action_section = text[plan_end + len('</plan>'):] if plan_end != -1 else text
        allowed_tools = set(self.scenario.tools.keys())
        candidate = None
        for raw in action_section.split('\n'):
            line = raw.strip()
            if not line:
                continue
            if line.startswith('say(') and line.endswith(')'):
                continue
            if '(' in line and ')' in line:
                name = line.split('(', 1)[0].strip()
                if name in allowed_tools and (' ' not in name) and ('=' not in name):
                    candidate = line
        return candidate is not None
    
    def extract_tool_call(self, system_response: str) -> str:
        """Extract a normalized tool call.
        Prefer explicit <action type="tool" name>...</action> tag; else use heuristic
        to find the LAST valid tool call line (matching known tools) after </plan>.
        """
        tag = self._parse_action_tag(system_response)
        if tag.get('type') == 'tool' and tag.get('name'):
            # Reconstruct a raw call line from tag JSON if possible
            args_obj = tag.get('args')
            if isinstance(args_obj, dict):
                try:
                    return f"{tag['name']}({json.dumps(args_obj, separators=(',', ':'))})"
                except Exception:
                    pass
            return tag.get('raw', '') or ''
        text = system_response or ""
        plan_end = text.rfind('</plan>')
        action_section = text[plan_end + len('</plan>'):] if plan_end != -1 else text
        allowed_tools = set(self.scenario.tools.keys())
        candidates: List[str] = []
        for raw in action_section.split('\n'):
            line = raw.strip()
            if not line:
                continue
            if line.startswith('say('):
                continue
            if '(' in line and ')' in line:
                name = line.split('(', 1)[0].strip()
                if name in allowed_tools and (' ' not in name) and ('=' not in name):
                    candidates.append(line)
        if candidates:
            return candidates[-1]
        # Fallback: scan entire text if nothing found (handles malformed plan tags)
        if plan_end != -1:
            for raw in text.split('\n'):
                line = raw.strip()
                if not line or line.startswith('say('):
                    continue
                if '(' in line and ')' in line:
                    name = line.split('(', 1)[0].strip()
                    if name in allowed_tools and (' ' not in name) and ('=' not in name):
                        candidates.append(line)
        return candidates[-1] if candidates else ""

    def _parse_action_tag(self, text: str) -> Dict[str, Any]:
        """Parse <action ...>...</action> blocks. Returns dict with keys:
        { type: 'tool'|'say'|None, name?, args?, raw? }
        Tolerates missing closing </action> for say actions.
        """
        if not text:
            return {}
        start = text.find('<action')
        if start == -1:
            return {}
        # Find end of opening tag
        open_end = text.find('>', start)
        if open_end == -1:
            return {}
        header = text[start + len('<action'):open_end]
        # Determine type and optional name
        type_val = None
        name_val = None
        if 'type="tool"' in header:
            type_val = 'tool'
        elif 'type="say"' in header:
            type_val = 'say'
        npos = header.find('name="')
        if npos != -1:
            nend = header.find('"', npos + 6)
            if nend != -1:
                name_val = header[npos + 6:nend]
        end_tag = '</action>'
        end = text.find(end_tag, open_end + 1)
        # Compute body depending on type and presence of closing tag
        if type_val == 'say':
            body = text[open_end + 1:end].strip() if end != -1 else text[open_end + 1:].strip()
            return { 'type': 'say', 'raw': body, 'text': body }
        if type_val == 'tool' and name_val and end != -1:
            body = text[open_end + 1:end].strip()
            result: Dict[str, Any] = { 'type': 'tool', 'raw': body, 'name': name_val }
            try:
                result['args'] = json.loads(body)
            except Exception:
                pass
            return result
        return {}

    def _normalize_tool_call(self, call_line: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Attempt to split a call line into (name, args) with JSON args when possible.
        Returns (name, args_dict_or_None).
        Examples:
          check_availability({"a":1}) -> ("check_availability", {"a":1})
          check_availability(restaurant_id="A") -> ("check_availability", None)
        """
        if not call_line or '(' not in call_line or ')' not in call_line:
            return None, None
        name = call_line.split('(', 1)[0].strip()
        inner = call_line[call_line.find('(') + 1: call_line.rfind(')')].strip()
        if inner.startswith('{') and inner.endswith('}'):
            try:
                return name, json.loads(inner)
            except Exception:
                return name, None
        return name, None

    def _build_observation(self, tool_result: str) -> Dict[str, Any]:
        """Return { raw, parsed } where parsed is JSON if possible, else None.
        Strips simple code fences.
        """
        raw = tool_result or ""
        text = raw.strip()
        # Strip ```json ... ``` or ``` ... ``` fences
        if text.startswith('```'):
            # remove first line fence and last ``` if present
            lines = text.split('\n')
            # drop first line
            body = '\n'.join(lines[1:])
            if body.endswith('```'):
                body = body[: -3]
            text = body.strip()
        parsed = None
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        return { 'raw': raw, 'parsed': parsed }
