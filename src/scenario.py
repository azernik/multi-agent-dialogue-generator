from dataclasses import dataclass
from typing import Dict, Any
import json
import os
from pathlib import Path

@dataclass
class ExampleScenario:
    name: str
    tools: Dict[str, Any]         # Structured tool definitions
    user_context: Dict[str, Any]  # User context configuration
    
    @classmethod
    def load(cls, example_path: str) -> 'ExampleScenario':
        """Load example scenario from scenario.json file"""
        example_dir = Path(example_path)
        name = example_dir.name
        
        # Load the single JSON file
        scenario_file = example_dir / "scenario.json"
        with open(scenario_file, 'r') as f:
            scenario_data = json.load(f)
        
        return cls(
            name=name,
            tools=scenario_data.get('tools', {}),
            user_context=scenario_data.get('user_context', {})
        )

def load_system_prompts(prompts_dir: str) -> Dict[str, str]:
    """Load system prompts for each agent type"""
    prompts_path = Path(prompts_dir)
    prompts = {}
    
    # Load each agent's system prompt
    for agent_type in ['system_agent', 'user_agent', 'tool_agent']:
        prompt_file = prompts_path / agent_type / "v1.txt"
        with open(prompt_file, 'r') as f:
            prompts[agent_type] = f.read().strip()
    
    return prompts 