from abc import ABC, abstractmethod
from typing import Dict, Any, List
import json
from core import ConversationContext, Message, MessageRole, LLMClient

class BaseAgent(ABC):
    def __init__(self, system_prompt: str, llm_client: LLMClient):
        self.system_prompt = system_prompt
        self.llm_client = llm_client
    
    @abstractmethod
    def generate_response(self, context: ConversationContext) -> str:
        """Generate response for this agent given the conversation context"""
        pass
    
    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        """Build proper message list with system prompt + conversation history"""
        messages = []
        
        # Add system prompt only once at the beginning
        messages.append({"role": "system", "content": self.system_prompt})
        
        # Add conversation history as proper message objects
        for msg in context.messages:
            messages.append({
                "role": "user" if msg.role == MessageRole.USER else "assistant",
                "content": msg.content
            })
        
        return messages

class SystemAgent(BaseAgent):
    def __init__(self, system_prompt: str, llm_client: LLMClient, tools: Dict[str, Any]):
        super().__init__(system_prompt, llm_client)
        self.tools = tools
    
    def generate_response(self, context: ConversationContext) -> str:
        """Generate structured response with <think>, <plan>, say(), tool_call()"""
        messages = self.build_prompt(context)
        
        # Log input to system agent
        if hasattr(self, 'flow_logger') and self.flow_logger:
            # Only log the last message (immediate input)
            if messages:
                last_msg = messages[-1]
                self.flow_logger.write(f"=== SYSTEM AGENT (IN) ===\n{last_msg}\n")
        
        response = self.llm_client.chat_completion(messages)
        
        # Log output from system agent
        if hasattr(self, 'flow_logger') and self.flow_logger:
            self.flow_logger.write(f"=== SYSTEM AGENT (OUT) ===\n{response}\n\n")
        
        return response
    
    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        """System prompt + tool definitions + conversation history"""
        messages = []
        
        # System prompt with tool definitions
        system_content = f"{self.system_prompt}\n\nAvailable Tools:\n{json.dumps(context.agent_config.get('tools', {}), indent=2)}"
        messages.append({"role": "system", "content": system_content})
        
        # Conversation history
        for msg in context.messages:
            messages.append({
                "role": "user" if msg.role == MessageRole.USER else "assistant",
                "content": msg.content
            })
        
        return messages
    
    def get_user_facing_message(self, system_response: str) -> str:
        """Extract say() content from system response"""
        # Simple extraction - let system agent handle complex parsing
        lines = system_response.split('\n')
        for line in lines:
            if line.strip().startswith('say('):
                # Extract content between say("...") 
                start = line.find('say("') + 5
                end = line.rfind('")')
                if start > 4 and end > start:
                    return line[start:end]
        return ""

class UserAgent(BaseAgent):
    def __init__(self, system_prompt: str, llm_client: LLMClient, user_context: Dict[str, Any]):
        super().__init__(system_prompt, llm_client)
        self.user_context = user_context
    
    def generate_response(self, context: ConversationContext) -> str:
        """Generate natural user response following behavioral directives"""
        messages = self.build_prompt(context)
        
        # Log input to user agent
        if hasattr(self, 'flow_logger') and self.flow_logger:
            # Only log the last message (immediate input)
            if messages:
                last_msg = messages[-1]
                self.flow_logger.write(f"=== USER AGENT (IN) ===\n{last_msg}\n")
        
        response = self.llm_client.chat_completion(messages)
        
        # Log output from user agent
        if hasattr(self, 'flow_logger') and self.flow_logger:
            self.flow_logger.write(f"=== USER AGENT (OUT) ===\n{response}\n\n")
        
        return response
    
    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        """User prompt + user context + conversation history"""
        messages = []
        
        # System prompt with user context
        system_content = f"{self.system_prompt}\n\nObjective: {self.user_context.get('objective', '')}\nUser behavior: {self.user_context.get('behavior', '')}"
        messages.append({"role": "system", "content": system_content})
        
        # Conversation history
        for msg in context.messages:
            messages.append({
                "role": "user" if msg.role == MessageRole.USER else "assistant",
                "content": msg.content
            })
        
        return messages

class ToolAgent(BaseAgent):
    def __init__(self, system_prompt: str, llm_client: LLMClient, tools: Dict[str, Any]):
        super().__init__(system_prompt, llm_client)
        self.tools = tools
    
    def generate_response(self, context: ConversationContext) -> str:
        """Generate tool result response"""
        messages = self.build_prompt(context)
        
        # Log input to tool agent
        if hasattr(self, 'flow_logger') and self.flow_logger:
            # Only log the last message (immediate input)
            if messages:
                last_msg = messages[-1]
                self.flow_logger.write(f"=== TOOL AGENT (IN) ===\n{last_msg}\n")
        
        response = self.llm_client.chat_completion(messages)
        
        # Log output from tool agent
        if hasattr(self, 'flow_logger') and self.flow_logger:
            self.flow_logger.write(f"=== TOOL AGENT (OUT) ===\n{response}\n\n")
        
        return response
    
    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        """Tool prompt + tool definitions + current tool call"""
        messages = []
        
        # System prompt with tool definitions
        system_content = f"{self.system_prompt}\n\nTool Definitions:\n{json.dumps(context.agent_config.get('tools', {}), indent=2)}"
        messages.append({"role": "system", "content": system_content})
        
        # Tool call history
        for msg in context.messages:
            messages.append({
                "role": "user" if msg.role == MessageRole.USER else "assistant",
                "content": msg.content
            })
        
        return messages 