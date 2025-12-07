from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Dict, Any, List
import json
from core import ConversationContext, Message, MessageRole, LLMClient

class BaseAgent(ABC):
    def __init__(self, system_prompt: str, llm_client: LLMClient):
        self.system_prompt = system_prompt
        self.llm_client = llm_client
        self.prompt_recorder = None
    
    def generate_response(self, context: ConversationContext, **api_kwargs) -> str:
        messages = self.build_prompt(context)
        if self.prompt_recorder:
            try:
                self.prompt_recorder(
                    self.__class__.__name__,
                    deepcopy(messages),
                    context
                )
            except Exception:
                # Recorder issues should not break simulation; log if available.
                if hasattr(self, 'flow_logger') and self.flow_logger:
                    self.flow_logger.write(
                        f"[WARN] Failed to record prompts for {self.__class__.__name__}\n"
                    )
        self._log_agent_flow(messages)
        response = self.llm_client.chat_completion(messages, **api_kwargs)
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
    
    def generate_response(self, context: ConversationContext, **api_kwargs) -> str:
        # Pass available tools to LLM client (needed for HF model formatting)
        tools = context.agent_config.get('tools', {})
        return super().generate_response(context, tools=tools, **api_kwargs)

    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        messages = []
        system_content = f"{self.system_prompt}\n\nAvailable Tools:\n{json.dumps(context.agent_config.get('tools', {}), indent=2)}"
        messages.append({"role": "system", "content": system_content})
        self._add_conversation_history(messages, context)
        return messages
    
    def get_user_facing_message(self, system_response: str) -> str:
        # Parse <action type="say">...</action>, tolerating missing closing tag
        text = system_response or ""
        start = text.find('<action')
        if start == -1:
            return ""
        # Find end of opening tag
        open_end = text.find('>', start)
        if open_end == -1:
            return ""
        header = text[start + len('<action'):open_end]
        if 'type="say"' not in header:
            return ""
        end_tag = '</action>'
        end = text.find(end_tag, open_end + 1)
        if end != -1:
            body = text[open_end + 1:end].strip()
        else:
            # No closing tag; treat the rest of the text as the body
            body = text[open_end + 1:].strip()
        return body

class UserAgent(BaseAgent):
    def __init__(self, system_prompt: str, llm_client: LLMClient, user_context: Dict[str, Any], temperature: float = 1.1):
        super().__init__(system_prompt, llm_client)
        self.user_context = user_context
        self.temperature = temperature

    def generate_response(self, context: ConversationContext) -> str:
        # Pass temperature to add diversity to user agent responses
        # return super().generate_response(context, temperature=self.temperature)
        return super().generate_response(context)

    def build_prompt(self, context: ConversationContext) -> List[Dict[str, str]]:
        messages = []
        ua = context.agent_config or {}
        task = ua.get('task', {}) if isinstance(ua.get('task'), dict) else {}
        objective = ua.get('objective') or task.get('objective', '') or task.get('description', '')
        persona_note = ua.get('user_persona', '')
        persona_details = ua.get('persona') if isinstance(ua.get('persona'), dict) else None
        slots = ua.get('slots') or task.get('slots', {}) or {}
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

        # Substitute writing style and sample messages in the system prompt template
        system_prompt_text = self.system_prompt
        if persona_details:
            writing_style = persona_details.get('writing_style', '')
            samples = persona_details.get('sample_messages') or []
            sample_messages_list = '\n'.join(f"- {msg}" for msg in samples)

            system_prompt_text = system_prompt_text.replace('{writing_style}', writing_style)
            system_prompt_text = system_prompt_text.replace('{sample_messages_list}', sample_messages_list)

        parts = [system_prompt_text]
        if objective:
            parts.append(f"\n\nObjective: {objective}")
        if persona_note:
            parts.append(f"\nPersona: {persona_note}")
        if persona_details:
            persona_lines: List[str] = []
            name = persona_details.get("name")
            age = persona_details.get("age")
            occupation = persona_details.get("occupation")
            hometown = persona_details.get("hometown")

            opener_chunks: List[str] = []
            if name:
                opener_chunks.append(name)
            descriptors: List[str] = []
            if isinstance(age, (int, str)) and f"{age}".strip():
                descriptors.append(f"{age}-year-old")
            if occupation:
                descriptors.append(occupation)
            if hometown:
                descriptors.append(f"from {hometown}")

            if opener_chunks or descriptors:
                opener = "You are"
                if opener_chunks:
                    opener += f" {opener_chunks[0]}"
                if descriptors:
                    opener += ", " + " ".join(descriptors)
                opener += "."
                persona_lines.append(opener)

            bio = persona_details.get('bio')
            if bio:
                persona_lines.append("People describe you like this:")
                persona_lines.append(bio)

            email = persona_details.get('email')
            phone = persona_details.get('phone')
            if email or phone:
                persona_lines.append("You share contact details freely when it's helpful:")
                if email:
                    persona_lines.append(f"- Email: {email}")
                if phone:
                    persona_lines.append(f"- Phone: {phone}")

            if persona_lines:
                parts.append("\nPersona Context:\n" + "\n".join(persona_lines))

        if slots:
            parts.append(f"\nInformation you have available (provide naturally when asked, give the minimum required): {json.dumps(slots)}")
        if behaviors_summary:
            parts.append(f"\nInjected behaviors: {json.dumps(behaviors_summary, ensure_ascii=False)}")
        
        system_content = ''.join(parts)
        messages.append({"role": "system", "content": system_content})

        # Add role boundary reminder before assistant messages to prevent role confusion
        for i, msg in enumerate(context.messages):   
            if msg.role == MessageRole.ASSISTANT:
                messages.append({
                    "role": "system", 
                    "content": "REMINDER: You are the USER. The message below is from the ASSISTANT. Answer their questions—don't ask questions or offer help yourself."
                })
            
            # Add the actual message
            messages.append({
                "role": "user" if msg.role == MessageRole.USER else "assistant",
                "content": msg.content
            })

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
        
        # Include scenario context (task slots + seed data) if present
        scenario_context = context.agent_config.get('scenario_context')
        if scenario_context:
            context_parts = []
            if scenario_context.get('task_slots'):
                context_parts.append(f"Task context (user's known information): {json.dumps(scenario_context['task_slots'], indent=2)}")
            if scenario_context.get('seed_data'):
                context_parts.append(f"Available data in this scenario: {json.dumps(scenario_context['seed_data'], indent=2)}")
            if context_parts:
                system_content += f"\n\nScenario Context:\n" + "\n".join(context_parts)
                system_content += "\n\nIMPORTANT: When generating tool responses, use the scenario context to ensure your responses align with the user's known information and the available data. For example, if the user is looking for an order from a specific date, return orders that match that date from the seed data."
        
        messages.append({"role": "system", "content": system_content})
        self._add_conversation_history(messages, context)
        return messages 
