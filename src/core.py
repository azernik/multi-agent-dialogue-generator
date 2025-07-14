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
        self.client = openai.OpenAI(
            api_key=api_key or os.getenv('OPENAI_API_KEY'),
            **kwargs
        )
        
    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Make API call and return raw response content"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content
