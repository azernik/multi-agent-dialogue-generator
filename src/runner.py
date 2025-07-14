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
        self.user_history: List[Message] = []      # User <-> System (say() only)
        self.system_history: List[Message] = []    # Full conversation including tool results
        self.tool_history: List[Message] = []      # Tool call <-> Tool response history
        
        self.logger.info(f"ConversationRunner initialized with max_turns={max_turns}")
        self.logger.info(f"Scenario: {scenario.name}")
        self.logger.info(f"Available tools: {list(scenario.tools.keys())}")
        
    def run_conversation(self) -> ConversationResult:
        """Main conversation loop - orchestrates the entire conversation"""
        had_tool_calls = False
        self.logger.info("Starting conversation loop")
        
        for turn in range(self.max_turns):
            self.logger.info(f"=== TURN {turn + 1} ===")
            
            # === USER TURN ===
            user_message = self.process_user_turn(turn)
            
            # Check termination after user message
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
                    termination_reason=termination_reason
                )
            
            # === SYSTEM TURN ===
            self.logger.info("Processing system turn")
            system_message, had_tool_call = self.process_system_turn(turn)
            if had_tool_call:
                had_tool_calls = True
            
            # Check termination after system message
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
                    termination_reason=termination_reason
                )
        
        # Max turns reached
        return ConversationResult(
            system_transcript=self.system_history.copy(),
            user_transcript=self.user_history.copy(),
            tool_transcript=self.tool_history.copy(),
            metadata={"total_turns": self.max_turns, "scenario": self.scenario.name, "had_tool_calls": had_tool_calls},
            success=False,
            termination_reason="max_turns_reached"
        )
        
    def process_user_turn(self, turn_number: int) -> Message:
        """Process a single user turn"""
        user_context = self.build_user_context(turn_number)
        user_response = self.user_agent.generate_response(user_context)
        self.logger.info(f"\nuser_agent response: {user_response}\n")
        user_message = Message(MessageRole.USER, user_response)
        
        # Update relevant histories
        self.user_history.append(user_message)
        self.system_history.append(user_message)
        
        return user_message
        
    def process_system_turn(self, turn_number: int) -> Tuple[Message, bool]:
        """Process a single system turn, handle tool calls if present"""
        had_tool_call = False
        
        # Keep looping until system agent produces a user-facing message
        while True:
            system_context = self.build_system_context(turn_number)
            system_response = self.system_agent.generate_response(system_context)
            self.logger.info(f"\nsystem_agent response: {system_response}\n")
            
            # Check if this is a tool call or a say() call
            if self.has_tool_call(system_response):
                had_tool_call = True
                
                # Add the system response with tool call to system history
                self.system_history.append(Message(MessageRole.ASSISTANT, system_response))
                
                # Process the tool call
                tool_result = self.process_tool_call(system_response, turn_number)
                
                # Add tool result to system history
                self.system_history.append(Message(MessageRole.ASSISTANT, tool_result))
                
                # Continue the loop - system agent gets another turn
                continue
                
            else:
                # Extract user-facing message from system response
                user_facing_message = self.system_agent.get_user_facing_message(system_response)
                
                # Create message objects
                system_message = Message(MessageRole.ASSISTANT, user_facing_message)
                full_system_message = Message(MessageRole.ASSISTANT, system_response)
                
                # Update histories
                self.user_history.append(system_message)          # User sees clean say() message
                self.system_history.append(full_system_message)   # System sees full response
            
            return system_message, had_tool_call
        
    def process_tool_call(self, system_response: str, turn_number: int) -> str:
        """Process a tool call and return tool result"""
        tool_context = self.build_tool_context(system_response, turn_number)
        tool_result = self.tool_agent.generate_response(tool_context)
        self.logger.info(f"\ntool_agent response: {tool_result}\n")
        
        # Extract just the tool call for clean tool history
        tool_call_only = self.extract_tool_call(system_response)
        
        # Update tool history
        self.tool_history.append(Message(MessageRole.USER, tool_call_only))
        self.tool_history.append(Message(MessageRole.ASSISTANT, tool_result))
        
        return tool_result
        
    def check_termination(self, last_message: Message, turn_number: int) -> Optional[Tuple[str, bool]]:
        """Check if conversation should terminate. Returns (reason, success) or None"""
        
        # Check for user completion tokens
        if last_message.role == MessageRole.USER:
            content = last_message.content
            if '[DONE_SUCCESS]' in content:
                return ("user_task_complete", True)
            elif '[DONE_FAILURE]' in content:
                return ("user_task_complete", False)
        
        # Check for max turns
        if turn_number >= self.max_turns - 1:
            return ("max_turns_reached", False)
        
        return None
        
    def build_user_context(self, turn_number: int) -> ConversationContext:
        """Build context for UserAgent - clean conversation history"""
        context = ConversationContext(
            messages=self.user_history,
            agent_config=self.scenario.user_context,
            turn_number=turn_number
        )
        return context
        
    def build_system_context(self, turn_number: int) -> ConversationContext:
        """Build context for SystemAgent - full conversation with tool results"""
        context = ConversationContext(
            messages=self.system_history,
            agent_config={"tools": self.scenario.tools},
            turn_number=turn_number
        )
        return context
        
    def build_tool_context(self, system_response: str, turn_number: int) -> ConversationContext:
        """Build context for ToolAgent - tool call history"""
        # Extract just the tool call for clean context
        tool_call_only = self.extract_tool_call(system_response)
        
        # Add current tool call to context
        current_tool_call = Message(MessageRole.USER, tool_call_only)
        tool_context_messages = self.tool_history + [current_tool_call]
        
        context = ConversationContext(
            messages=tool_context_messages,
            agent_config={"tools": self.scenario.tools},
            turn_number=turn_number
        )
        return context
        
    def has_tool_call(self, system_response: str) -> bool:
        """Check if system response contains a tool call (any function call after </plan> that's not say())"""
        # Extract everything after the last </plan> tag
        plan_end = system_response.rfind('</plan>')
        if plan_end == -1:
            return False
        
        action_section = system_response[plan_end + len('</plan>'):].strip()
        
        # Look for function calls that are not say()
        lines = action_section.split('\n')
        for line in lines:
            line = line.strip()
            if '(' in line and ')' in line and not line.startswith('say('):
                # This is a function call that's not say()
                return True
        return False
    
    def extract_tool_call(self, system_response: str) -> str:
        """Extract the tool call from system response (function call after </plan> that's not say())"""
        # Extract everything after the last </plan> tag
        plan_end = system_response.rfind('</plan>')
        if plan_end == -1:
            return ""
        
        action_section = system_response[plan_end + len('</plan>'):].strip()
        
        # Look for function calls that are not say()
        lines = action_section.split('\n')
        for line in lines:
            line = line.strip()
            if '(' in line and ')' in line and not line.startswith('say('):
                # This is our tool call
                return line
        return "" 