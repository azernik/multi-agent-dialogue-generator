from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
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

class ConversationRunner:
    def __init__(self, 
                 scenario: ExampleScenario,
                 system_agent: SystemAgent,
                 user_agent: UserAgent, 
                 tool_agent: ToolAgent,
                 max_turns: int = 20):
        self.scenario = scenario
        self.system_agent = system_agent
        self.user_agent = user_agent
        self.tool_agent = tool_agent
        self.max_turns = max_turns
        self.logger = logging.getLogger(__name__)
        
        # Three separate conversation histories
        self.user_history: List[Message] = []
        self.system_history: List[Message] = []
        self.tool_history: List[Message] = []
        # Aggregated per-system-turn traces for training/export
        self.turn_traces: List[Dict[str, Any]] = []
        
        self.logger.info(f"ConversationRunner initialized with max_turns={max_turns}")
        self.logger.info(f"Scenario: {scenario.name}")
        self.logger.info(f"Available tools: {list(scenario.tools.keys())}")
        
    def run_conversation(self) -> ConversationResult:
        had_tool_calls = False
        self.logger.info("Starting conversation loop")
        
        for turn in range(self.max_turns):
            self.logger.info(f"=== TURN {turn + 1} ===")
            user_message = self.process_user_turn(turn)
            termination_result = self.check_termination(user_message, turn)
            if termination_result:
                termination_reason, success = termination_result
                self.logger.info(f"Conversation terminated after user message. Reason: {termination_reason}, Success: {success}")
                return ConversationResult(
                    system_transcript=self.system_history.copy(),
                    user_transcript=self.user_history.copy(),
                    tool_transcript=self.tool_history.copy(),
                    metadata={"total_turns": turn + 1, "scenario": self.scenario.name, "had_tool_calls": had_tool_calls},
                    success=success,
                    termination_reason=termination_reason,
                    turn_traces=self.turn_traces.copy()
                )
            
            self.logger.info("Processing system turn")
            system_message, had_tool_call = self.process_system_turn(turn)
            if had_tool_call:
                had_tool_calls = True
            termination_result = self.check_termination(system_message, turn)
            if termination_result:
                termination_reason, success = termination_result
                self.logger.info(f"Conversation terminated after system message. Reason: {termination_reason}, Success: {success}")
                return ConversationResult(
                    system_transcript=self.system_history.copy(),
                    user_transcript=self.user_history.copy(),
                    tool_transcript=self.tool_history.copy(),
                    metadata={"total_turns": turn + 1, "scenario": self.scenario.name, "had_tool_calls": had_tool_calls},
                    success=success,
                    termination_reason=termination_reason,
                    turn_traces=self.turn_traces.copy()
                )
        
        return ConversationResult(
            system_transcript=self.system_history.copy(),
            user_transcript=self.user_history.copy(),
            tool_transcript=self.tool_history.copy(),
            metadata={"total_turns": self.max_turns, "scenario": self.scenario.name, "had_tool_calls": had_tool_calls},
            success=False,
            termination_reason="max_turns_reached",
            turn_traces=self.turn_traces.copy()
        )
        
    def process_user_turn(self, turn_number: int) -> Message:
        user_context = self.build_user_context(turn_number)
        user_response = self.user_agent.generate_response(user_context)
        self.logger.info(f"\nuser_agent response: {user_response}\n")
        user_message = Message(MessageRole.USER, user_response)
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
        while True:
            # Build context and get assistant output for the current micro-step
            system_context = self.build_system_context(turn_number)
            system_response = self.system_agent.generate_response(system_context)
            self.logger.info(f"\nsystem_agent response: {system_response}\n")
            system_messages_raw.append(system_response)
            if self.has_tool_call(system_response):
                had_tool_call = True
                self.system_history.append(Message(MessageRole.ASSISTANT, system_response))
                # Record the tool call line in actions_structured
                tool_call_only = self.extract_tool_call(system_response)
                if tool_call_only:
                    actions_structured.append({ 'type': 'tool_call', 'raw': tool_call_only })
                tool_result = self.process_tool_call(system_response, turn_number)
                self.system_history.append(Message(MessageRole.TOOL, tool_result))
                tool_results.append(tool_result)
                continue
            else:
                user_facing_message = self.system_agent.get_user_facing_message(system_response)
                system_message = Message(MessageRole.ASSISTANT, user_facing_message, metadata={"turn_id": turn_id})
                self.user_history.append(system_message)
                self.system_history.append(full_system_message)
                # Record final say action
                actions_structured.append({ 'type': 'say', 'text': user_facing_message })
                # Build turn trace for export
                turn_trace: Dict[str, Any] = {
                    'history_before': pre_turn_user_history,
                    'system_messages_raw': system_messages_raw,
                    'actions_structured': actions_structured,
                    'tool_results': tool_results,
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
        agent_config = {"tools": self.scenario.tools, "tool_agent": ta_cfg}
        return ConversationContext(
            messages=tool_context_messages,
            agent_config=agent_config,
            turn_number=turn_number
        )

    def build_tool_context_from_call(self, tool_call: str, turn_number: int) -> ConversationContext:
        current_tool_call = Message(MessageRole.USER, tool_call)
        tool_context_messages = self.tool_history + [current_tool_call]
        ta_cfg = self._enrich_behaviors({"injected_behaviors": self.scenario.tool_agent.get('injected_behaviors', [])}, self.scenario.behavior_types)
        agent_config = {"tools": self.scenario.tools, "tool_agent": ta_cfg}
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
        
    def _parse_actions(self, system_response: str, is_first_micro_step: bool) -> List[Dict[str, Any]]:
        """Parse assistant response into ordered actions: tool or say.
        First micro-step prefers parsing after </plan>; later steps parse from the start.
        """
        text = system_response or ""
        start_idx = 0
        if is_first_micro_step:
            plan_end = text.rfind('</plan>')
            if plan_end != -1:
                start_idx = plan_end + len('</plan>')
        action_section = text[start_idx:].strip()
        if not action_section:
            return []
        actions: List[Dict[str, Any]] = []
        for raw in action_section.split('\n'):
            line = raw.strip()
            if not line:
                continue
            # Say terminator
            if line.startswith('say(') and line.endswith(')'):
                # naive extract text inside the outermost quotes
                text_start = line.find('"')
                text_end = line.rfind('"')
                say_text = line[text_start + 1:text_end] if text_start != -1 and text_end > text_start else ''
                actions.append({"type": "say", "text": say_text})
                # We still parse remaining lines in case they exist, but say will terminate the turn when executed
                continue
            # Tool call heuristic: looks like name(args), not starting with say(
            if '(' in line and ')' in line and not line.startswith('say('):
                name_part = line.split('(', 1)[0].strip()
                if name_part:
                    actions.append({"type": "tool", "name": name_part, "call": line})
                continue
            # Ignore other lines (think/plan/etc.)
        return actions