from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum
import openai
import os

class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"

@dataclass
class Message:
    role: MessageRole
    content: str

@dataclass
class ConversationContext:
    messages: List[Message]
    agent_config: Dict[str, Any]
    turn_number: int

class LLMClient:
    def __init__(self, model: str, api_key: str = None, **kwargs):
        self.model = model
        # Handle both old and new OpenAI client formats
        try:
            self.client = openai.OpenAI(
                api_key=api_key or os.getenv('OPENAI_API_KEY'),
                **kwargs
            )
        except AttributeError:
            # Fallback to old format
            openai.api_key = api_key or os.getenv('OPENAI_API_KEY')
            self.client = openai
        
    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Make API call and return raw response content"""
        try:
            # New OpenAI client format
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                **kwargs
            )
            return response.choices[0].message.content
        except AttributeError:
            # Old OpenAI client format
            response = self.client.ChatCompletion.create(
                model=self.model,
                messages=messages,
                **kwargs
            )
            return response.choices[0].message.content
