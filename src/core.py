from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import openai
import os
import random

class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

@dataclass
class Message:
    role: MessageRole
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ConversationContext:
    messages: List[Message]
    agent_config: Dict[str, Any]
    turn_number: int

class LLMClient:
    def __init__(self, model: str, api_key: str = None, **kwargs):
        self.model = model
        # Create OpenAI client
        self.client = openai.OpenAI(
            api_key=api_key or os.getenv('OPENAI_API_KEY'),
            **kwargs
        )
        
    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Make API call and return raw response content
        
        Migrated to Responses API:
        - Separates system messages (→ instructions) from conversation messages (→ input)
        - Uses stateless mode (store=false) for synthetic data generation
        - Disables tool calls (no tools parameter)
        """
        # Separate system messages from conversation messages
        instructions_parts = []
        conversation_messages = []
        
        for msg in messages:
            if msg.get("role") == "system":
                # Collect all system messages into instructions
                instructions_parts.append(msg.get("content", ""))
            else:
                # Keep user/assistant messages for conversation
                conversation_messages.append({
                    "role": msg.get("role"),
                    "content": msg.get("content", "")
                })
        
        # Combine system messages into single instructions string
        instructions = "\n\n".join(instructions_parts) if instructions_parts else None
        
        # Add cache-busting variation to prevent prompt caching from causing identical outputs
        # This adds a small random variation that doesn't affect the meaning but prevents cache hits
        cache_buster = f"\n\n[Variation: {random.random():.10f}]"
        if instructions:
            instructions = instructions + cache_buster
        else:
            # If no instructions, add to the last user message to prevent caching
            if conversation_messages:
                last_msg = conversation_messages[-1]
                last_msg["content"] = last_msg.get("content", "") + cache_buster
        
        # Prepare input: use conversation messages if available
        # Note: Responses API input can be a list of messages or a string
        input_messages = conversation_messages if conversation_messages else []
        
        # Extract temperature and other kwargs (excluding tools if present)
        api_kwargs = {k: v for k, v in kwargs.items() if k != "tools"}
        
        # Build API call parameters
        api_params = {
            "model": self.model,
            "store": False,  # Stateless mode for synthetic data generation
            **api_kwargs
        }
        
        # Add input (required) - use messages list or empty list as fallback
        if input_messages:
            api_params["input"] = input_messages
        else:
            # Fallback: empty user message if no conversation messages
            api_params["input"] = [{"role": "user", "content": ""}]
        
        # Add instructions only if present (optional parameter)
        if instructions:
            api_params["instructions"] = instructions

        if self.model == "gpt-5.1":
            api_params["reasoning"] = {"effort": "none"}
            api_params["text"] = {"verbosity": "low"}
        
        try:
            # Use Responses API
            # Check if responses API is available
            if not hasattr(self.client, 'responses'):
                raise AttributeError("Responses API not available")
            
            # Debug: log temperature if present
            if 'temperature' in api_params:
                import logging
                logging.getLogger(__name__).debug(f"API call with temperature={api_params['temperature']}")
            
            response = self.client.responses.create(**api_params)
            
            # Extract response content - Use output_text convenience property
            # Then strip everything before the first <think> tag
            # This handles cases where the model outputs JSON or other text before the structured format
            
            if hasattr(response, 'output_text') and response.output_text is not None:
                text = response.output_text
                # Find the first occurrence of <think>
                marker = '<think>'
                idx = text.find(marker)
                if idx != -1:
                    # Strip everything before the marker
                    return text[idx:]
                # If marker not found, return as-is (shouldn't happen, but be safe)
                return text
            
            # Fallback: manually extract from output array if output_text not available
            if hasattr(response, 'output') and isinstance(response.output, list):
                texts = []
                for item in response.output:
                    if hasattr(item, 'content') and hasattr(item, 'role') and item.role == 'assistant':
                        for content_item in item.content:
                            if hasattr(content_item, 'text') and content_item.text:
                                texts.append(content_item.text)
                
                if texts:
                    combined_text = '\n'.join(texts)
                    # Strip everything before the first <think>
                    marker = '<think>'
                    idx = combined_text.find(marker)
                    if idx != -1:
                        return combined_text[idx:]
                    return combined_text
            
            # Final fallback: return empty string
            return ""
        except (AttributeError, Exception) as e:
            # Fallback to old chat completions API if responses API not available or fails
            # This allows graceful degradation if Responses API is not yet available
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    **kwargs
                )
                return response.choices[0].message.content
            except Exception as fallback_error:
                # If both APIs fail, raise the original Responses API error
                raise e from fallback_error
