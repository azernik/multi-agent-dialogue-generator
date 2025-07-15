from abc import ABC, abstractmethod
from typing import Dict, Any, List
import json
from core import ConversationContext, Message, MessageRole, LLMClient

class BaseAgent(ABC):
    def __init__(self, system_prompt: str, llm_client: LLMClient):
        self.system_prompt = system_prompt
        self.llm_client = llm_client
    
    def generate_response(self, context: ConversationContext) -> str:
        """Generate response for this agent given the conversation context"""
        messages = self.build_prompt(context)
        self._log_agent_flow(messages)
        response = self.llm_client.chat_completion(messages)
        self._log_agent_flow(messages, response)
        return response
    
    def _log_agent_flow(self, messages, response=None, agent_name=None):
        """Helper method to log agent input/output flow"""
        if hasattr(self, 'flow_logger') and self.flow_logger:
            if agent_name is None:
                agent_name = self.__class__.__name__.replace('Agent', '').upper()
            
            if response is None:  # Input logging
                if messages:
                    last_msg = messages[-1]
                    self.flow_logger.write(f"=== {agent_name} AGENT (IN) ===\n{last_msg}\n")
            else:  # Output logging
                self.flow_logger.write(f"=== {agent_name} AGENT (OUT) ===\n{response}\n\n")
    
    def _add_conversation_history(self, messages: List[Dict[str, str]], context: ConversationContext):
        """Helper method to add conversation history to messages list"""
        for msg in context.messages:
            messages.append({
                "role": "user" if msg.role == MessageRole.USER else "assistant",
                "content": msg.content
            })
    
    @abstractmethod
    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        """Build prompt for this agent - must be implemented by subclasses"""
        pass
    


class SystemAgent(BaseAgent):
    def __init__(self, system_prompt: str, llm_client: LLMClient, tools: Dict[str, Any]):
        super().__init__(system_prompt, llm_client)
        self.tools = tools
    

    
    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        """System prompt + tool definitions + conversation history"""
        messages = []
        
        # System prompt with tool definitions
        system_content = f"{self.system_prompt}\n\nAvailable Tools:\n{json.dumps(context.agent_config.get('tools', {}), indent=2)}"
        messages.append({"role": "system", "content": system_content})
        
        # Conversation history
        self._add_conversation_history(messages, context)
        
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
    

    
    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        """User prompt + user context + conversation history"""
        messages = []
        
        # System prompt with user context
        system_content = f"{self.system_prompt}\n\nObjective: {self.user_context.get('objective', '')}\nUser behavior: {self.user_context.get('behavior', '')}"
        messages.append({"role": "system", "content": system_content})
        
        # Conversation history
        self._add_conversation_history(messages, context)
        
        return messages

class ToolAgent(BaseAgent):
    def __init__(self, system_prompt: str, llm_client: LLMClient, tools: Dict[str, Any]):
        super().__init__(system_prompt, llm_client)
        self.tools = tools
    

    
    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        """Tool prompt + tool definitions + current tool call"""
        messages = []
        
        # System prompt with tool definitions
        system_content = f"{self.system_prompt}\n\nTool Definitions:\n{json.dumps(context.agent_config.get('tools', {}), indent=2)}"
        messages.append({"role": "system", "content": system_content})
        
        # Tool call history
        self._add_conversation_history(messages, context)
        
        return messages 