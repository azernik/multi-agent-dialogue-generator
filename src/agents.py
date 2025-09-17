from abc import ABC, abstractmethod
from typing import Dict, Any, List
import json
from core import ConversationContext, Message, MessageRole, LLMClient

class BaseAgent(ABC):
    def __init__(self, system_prompt: str, llm_client: LLMClient):
        self.system_prompt = system_prompt
        self.llm_client = llm_client
    
    def generate_response(self, context: ConversationContext) -> str:
        messages = self.build_prompt(context)
        self._log_agent_flow(messages)
        response = self.llm_client.chat_completion(messages)
        self._log_agent_flow(messages, response)
        return response
    
    def _log_agent_flow(self, messages, response=None, agent_name=None):
        if hasattr(self, 'flow_logger') and self.flow_logger:
            if agent_name is None:
                agent_name = self.__class__.__name__.replace('Agent', '').upper()
            if response is None:
                if messages:
                    last_msg = messages[-1]
                    self.flow_logger.write(f"=== {agent_name} AGENT (IN) ===\n{last_msg}\n")
            else:
                self.flow_logger.write(f"=== {agent_name} AGENT (OUT) ===\n{response}\n\n")
    
    def _add_conversation_history(self, messages: List[Dict[str, str]], context: ConversationContext):
        for msg in context.messages:
            messages.append({
                "role": "user" if msg.role == MessageRole.USER else "assistant",
                "content": msg.content
            })
    
    @abstractmethod
    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        pass
    

class SystemAgent(BaseAgent):
    def __init__(self, system_prompt: str, llm_client: LLMClient, tools: Dict[str, Any]):
        super().__init__(system_prompt, llm_client)
        self.tools = tools
    
    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        messages = []
        system_content = f"{self.system_prompt}\n\nAvailable Tools:\n{json.dumps(context.agent_config.get('tools', {}), indent=2)}"
        messages.append({"role": "system", "content": system_content})
        self._add_conversation_history(messages, context)
        return messages
    
    def get_user_facing_message(self, system_response: str) -> str:
        lines = system_response.split('\n')
        for line in lines:
            if line.strip().startswith('say('):
                start = line.find('say("') + 5
                end = line.rfind('")')
                if start > 4 and end > start:
                    return line[start:end]
        return ""

class UserAgent(BaseAgent):
    def __init__(self, system_prompt: str, llm_client: LLMClient, user_context: Dict[str, Any]):
        super().__init__(system_prompt, llm_client)
    
    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        messages = []
        ua = context.agent_config or {}
        objective = ua.get('objective', '')
        initial_message = ua.get('initial_message', '')
        persona = ua.get('persona', '')
        slots = ua.get('slots', {})
        injected_behaviors = ua.get('injected_behaviors', [])
        
        # Enrich behaviors for prompt clarity
        def summarize_behaviors(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            result = []
            for b in items:
                if not isinstance(b, dict):
                    continue
                summary = {
                    "id": b.get("id"),
                    "type_id": b.get("type_id"),
                    "instructions": b.get("instructions", "")
                }
                if b.get("type_description"):
                    summary["type_description"] = b["type_description"]
                if b.get("type_expected_recovery"):
                    summary["type_expected_recovery"] = b["type_expected_recovery"]
                result.append(summary)
            return result
        
        behaviors_summary = summarize_behaviors(injected_behaviors)
        
        parts = [self.system_prompt]
        if objective:
            parts.append(f"\n\nObjective: {objective}")
        if persona:
            parts.append(f"\nPersona: {persona}")
        if slots:
            parts.append(f"\nTarget slots: {json.dumps(slots)}")
        if behaviors_summary:
            parts.append(f"\nInjected behaviors: {json.dumps(behaviors_summary, ensure_ascii=False)}")
        
        system_content = ''.join(parts)
        messages.append({"role": "system", "content": system_content})
        
        # Add conversation history with periodic system prompt reinforcement
        reinforcement_interval = 8  # Reinforce every 8 messages
        for i, msg in enumerate(context.messages):
            # Add periodic system prompt reinforcement
            if i > 0 and i % reinforcement_interval == 0:
                messages.append({"role": "system", "content": system_content})
            
            # Add the actual message
            messages.append({
                "role": "user" if msg.role == MessageRole.USER else "assistant",
                "content": msg.content
            })
        
        if not context.messages and initial_message:
            messages.append({"role": "user", "content": initial_message})
        return messages

class ToolAgent(BaseAgent):
    def __init__(self, system_prompt: str, llm_client: LLMClient, tools: Dict[str, Any]):
        super().__init__(system_prompt, llm_client)
        self.tools = tools
    
    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        messages = []
        system_content = f"{self.system_prompt}\n\nTool Definitions:\n{json.dumps(context.agent_config.get('tools', {}), indent=2)}"
        ta = context.agent_config.get('tool_agent', {}) if context.agent_config else {}
        injected_behaviors = ta.get('injected_behaviors', [])
        
        # Summarize behaviors for tool agent prompt
        def summarize_behaviors(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            result = []
            for b in items:
                if not isinstance(b, dict):
                    continue
                summary = {
                    "id": b.get("id"),
                    "type_id": b.get("type_id"),
                    "instructions": b.get("instructions", "")
                }
                if b.get("type_description"):
                    summary["type_description"] = b["type_description"]
                result.append(summary)
            return result
        
        behaviors_summary = summarize_behaviors(injected_behaviors)
        if behaviors_summary:
            system_content += f"\n\nInjected behaviors: {json.dumps(behaviors_summary, ensure_ascii=False)}"
        
        messages.append({"role": "system", "content": system_content})
        self._add_conversation_history(messages, context)
        return messages 