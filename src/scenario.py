from dataclasses import dataclass, field
from typing import Dict, Any
import json
import os
from pathlib import Path

@dataclass
class ExampleScenario:
    name: str
    tools: Dict[str, Any]         # Structured tool definitions
    user_agent: Dict[str, Any] = field(default_factory=dict)  # User agent config
    tool_agent: Dict[str, Any] = field(default_factory=dict)  # Tool agent config
    behavior_types: Dict[str, Any] = field(default_factory=dict)  # Global behavior type index
    
    @classmethod
    def load(cls, example_path: str) -> 'ExampleScenario':
        """Load example scenario from scenario.json file"""
        example_dir = Path(example_path)
        name = example_dir.name
        
        # Load the single JSON file
        scenario_file = example_dir / "scenario.json"
        with open(scenario_file, 'r') as f:
            scenario_data = json.load(f)
        
        # Prefer DRY domain-level toolset if specified
        tools: Dict[str, Any] = {}
        domain_ref = scenario_data.get('domain_ref', {}) or {}
        toolset_path = domain_ref.get('toolset_path')
        if toolset_path:
            toolset_file = (example_dir / toolset_path).resolve()
            with open(toolset_file, 'r') as tf:
                toolset_data = json.load(tf)
            if isinstance(toolset_data, dict) and 'tools' in toolset_data and isinstance(toolset_data['tools'], dict):
                tools = toolset_data['tools']
            else:
                tools = toolset_data if isinstance(toolset_data, dict) else {}
        else:
            tools = scenario_data.get('tools', {})
        
        # Load global behavior types catalog if available
        behavior_types_index: Dict[str, Any] = {}
        catalog_path = _resolve_behavior_catalog_path(example_dir)
        if catalog_path:
            with open(catalog_path, 'r') as cf:
                catalog = json.load(cf)
                types_list = catalog.get('types', []) if isinstance(catalog, dict) else []
                for t in types_list:
                    tid = t.get('type_id')
                    if tid:
                        behavior_types_index[tid] = {
                            'agent': t.get('agent'),
                            'description': t.get('description', '')
                        }
        
        return cls(
            name=name,
            tools=tools,
            user_agent=scenario_data.get('user_agent', {}),
            tool_agent=scenario_data.get('tool_agent', {}),
            behavior_types=behavior_types_index
        )

def _resolve_behavior_catalog_path(example_dir: Path) -> Path | None:
    """Find data/catalogs/behavior_types.json by walking up from the example_dir."""
    # Try repo-root/data/catalogs/behavior_types.json
    repo_root = Path(__file__).resolve().parent.parent  # src/ -> repo root
    candidate = repo_root / 'data' / 'catalogs' / 'behavior_types.json'
    if candidate.exists():
        return candidate
    # Else walk up from example_dir
    cur = example_dir.resolve()
    for parent in [cur] + list(cur.parents):
        cand = parent.parent / 'data' / 'catalogs' / 'behavior_types.json'
        if cand.exists():
            return cand
    return None

def load_system_prompts(prompts_dir: str, version: str = "v1") -> Dict[str, str]:
    """Load system prompts for each agent type"""
    prompts_path = Path(prompts_dir)
    prompts = {}
    for agent_type in ['system_agent', 'user_agent', 'tool_agent']:
        prompt_file = prompts_path / agent_type / f"{version}.txt"
        with open(prompt_file, 'r') as f:
            prompts[agent_type] = f.read().strip()
    return prompts 