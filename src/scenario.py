from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import json
import sys
from pathlib import Path


def extract_scenario_id_from_filename(filename: str) -> str:
    """Extract scenario ID from filename, removing persona suffix if present.
    
    Examples:
        'os_ro_001__persona_025.json' -> 'os_ro_001'
        'os_ro_001.json' -> 'os_ro_001'
        'os_ro_001' -> 'os_ro_001'
    """
    # Remove .json extension if present
    base = filename.replace('.json', '')
    # Remove persona suffix if present (format: __persona_XXX)
    if '__persona_' in base:
        base = base.split('__persona_')[0]
    return base


def extract_persona_from_filename(filename: str) -> Optional[str]:
    """Extract persona ID from filename if present.
    
    Examples:
        'os_ro_001__persona_025.json' -> 'persona_025'
        'os_ro_001.json' -> None
    """
    base = filename.replace('.json', '')
    if '__persona_' in base:
        return 'persona_' + base.split('__persona_')[1]
    return None


def parse_scenario_filename(filename: str) -> Dict[str, Optional[str]]:
    """Parse scenario filename into components.
    
    Returns dict with: scenario_id, persona_id, domain, use_case, pattern_id
    """
    base = filename.replace('.json', '')
    persona_id = extract_persona_from_filename(filename)
    scenario_id = extract_scenario_id_from_filename(filename)
    
    # Parse scenario_id format: {domain}_{use_case}_{pattern_id}
    # e.g., 'os_ro_001' -> domain='os', use_case='ro', pattern_id='001'
    parts = scenario_id.split('_')
    domain = parts[0] if len(parts) > 0 else None
    use_case = parts[1] if len(parts) > 1 else None
    pattern_id = '_'.join(parts[2:]) if len(parts) > 2 else None
    
    return {
        'scenario_id': scenario_id,
        'persona_id': persona_id,
        'domain': domain,
        'use_case': use_case,
        'pattern_id': pattern_id
    }


def resolve_scenario_id(scenario_id: str) -> Path:
    """Find scenario file by ID in data/domains directory.
    
    Args:
        scenario_id: Scenario ID (e.g., 'ca_oe_005__persona_001' or 'ca_oe_005')
    
    Returns:
        Path to the scenario file
        
    Raises:
        FileNotFoundError: If no scenario found
        ValueError: If multiple scenarios match
    """
    # Get repo root (assuming scenario.py is in src/)
    repo_root = Path(__file__).resolve().parent.parent
    domains_dir = repo_root / "data" / "domains"
    
    if not domains_dir.exists():
        raise FileNotFoundError(f"Domains directory not found: {domains_dir}")
    
    # Search for matching file (with or without .json extension)
    pattern = f"**/{scenario_id}.json"
    matches = list(domains_dir.glob(pattern))
    
    if len(matches) == 0:
        # Try without .json extension in case user didn't include it
        pattern = f"**/{scenario_id}"
        matches = list(domains_dir.glob(pattern))
        # Filter to only JSON files
        matches = [m for m in matches if m.suffix == '.json']
    
    # Filter out tools.json and catalog.json
    matches = [m for m in matches if m.name not in ('tools.json', 'catalog.json')]
    
    if len(matches) == 0:
        raise FileNotFoundError(f"No scenario found for ID: {scenario_id}")
    if len(matches) > 1:
        raise ValueError(f"Multiple scenarios found for ID '{scenario_id}': {[str(m) for m in matches]}")
    
    return matches[0]


def resolve_scenario_pattern(pattern: str) -> List[Path]:
    """Find scenario files matching a glob pattern (e.g., 'ca_ro_002*').
    
    Args:
        pattern: Glob pattern with * wildcard (e.g., 'ca_ro_002*')
        
    Returns:
        List of matching scenario file paths
        
    Raises:
        FileNotFoundError: If no scenarios match the pattern
    """
    # Get repo root (assuming scenario.py is in src/)
    repo_root = Path(__file__).resolve().parent.parent
    domains_dir = repo_root / "data" / "domains"
    
    if not domains_dir.exists():
        raise FileNotFoundError(f"Domains directory not found: {domains_dir}")
    
    # Search for matching files
    search_pattern = f"**/{pattern}.json"
    matches = list(domains_dir.glob(search_pattern))
    
    if len(matches) == 0:
        # Try without .json extension
        search_pattern = f"**/{pattern}"
        matches = list(domains_dir.glob(search_pattern))
        # Filter to only JSON files
        matches = [m for m in matches if m.suffix == '.json']
    
    # Filter out tools.json and catalog.json
    matches = [m for m in matches if m.name not in ('tools.json', 'catalog.json')]
    
    if len(matches) == 0:
        raise FileNotFoundError(f"No scenarios found matching pattern: {pattern}")
    
    return sorted(matches)


def resolve_scenario_target(target: str) -> Path:
    """Resolve a target (path or ID) to a scenario file path.
    
    Args:
        target: Either a file path (relative or absolute) or scenario ID
        
    Returns:
        Path to the scenario file
        
    Raises:
        FileNotFoundError: If path doesn't exist or ID not found
        ValueError: If multiple scenarios match an ID (use resolve_scenario_pattern for wildcards)
    """
    if '/' in target or target.endswith('.json'):
        # Treat as path
        return Path(target).resolve()
    elif '*' in target:
        # Treat as glob pattern - but this function returns single Path, so raise error
        raise ValueError(f"Wildcard pattern '{target}' matches multiple files. Use resolve_scenario_pattern() instead.")
    else:
        # Treat as scenario ID
        return resolve_scenario_id(target)


@dataclass
class ExampleScenario:
    name: str
    tools: Dict[str, Any]         # Structured tool definitions
    task: Dict[str, Any] = field(default_factory=dict)        # Canonical task definition
    user_agent: Dict[str, Any] = field(default_factory=dict)  # User agent config
    tool_agent: Dict[str, Any] = field(default_factory=dict)  # Tool agent config
    behavior_types: Dict[str, Any] = field(default_factory=dict)  # Global behavior type index
    persona_id: Optional[str] = None  # Persona ID (e.g., "persona_025")
    
    @classmethod
    def load(cls, example_path: str) -> 'ExampleScenario':
        """Load example scenario from JSON file path.
        
        Args:
            example_path: Path to scenario JSON file (e.g., 'data/domains/online_shopping/return_order/os_ro_001__persona_025.json')
        """
        scenario_file = Path(example_path)
        if not scenario_file.exists():
            raise FileNotFoundError(f"Scenario file not found: {scenario_file}")
        
        # Extract scenario ID from filename (without persona suffix)
        filename = scenario_file.name
        name = extract_scenario_id_from_filename(filename)
        
        # Load the JSON file
        with open(scenario_file, 'r') as f:
            scenario_data = json.load(f)
        
        # Prefer DRY domain-level toolset if specified
        tools: Dict[str, Any] = {}
        domain_ref = scenario_data.get('domain_ref', {}) or {}
        toolset_path = domain_ref.get('toolset_path')
        if toolset_path:
            # Resolve toolset path relative to scenario file's directory
            toolset_file = (scenario_file.parent / toolset_path).resolve()
            print(f"[DEBUG] Loading toolset from: {toolset_file}", file=sys.stderr)
            with open(toolset_file, 'r') as tf:
                toolset_data = json.load(tf)
            if isinstance(toolset_data, dict) and 'tools' in toolset_data and isinstance(toolset_data['tools'], dict):
                tools = toolset_data['tools']
            else:
                tools = toolset_data if isinstance(toolset_data, dict) else {}
        else:
            tools = scenario_data.get('tools', {})
            
        print(f"[DEBUG] Loaded {len(tools)} tools.", file=sys.stderr)
        
        # Load global behavior types catalog if available
        behavior_types_index: Dict[str, Any] = {}
        catalog_path = _resolve_behavior_catalog_path(scenario_file.parent)
        if catalog_path:
            with open(catalog_path, 'r') as cf:
                catalog = json.load(cf)
                types_list = catalog.get('types', []) if isinstance(catalog, dict) else []
                for t in types_list:
                    tid = t.get('type_id')
                    if tid:
                        behavior_types_index[tid] = {
                            'agent': t.get('agent'),
                            'description': t.get('objective', '')
                        }
        
        # Load canonical task definition; fallback to legacy fields if absent
        task = scenario_data.get('task', {}) or {}
        if not task:
            legacy_ua = scenario_data.get('user_agent', {}) or {}
            task = {
                'objective': legacy_ua.get('objective', ''),
                'slots': legacy_ua.get('slots', {})
            }

        # Load persona ID (new format: simple string, fallback to old format for compatibility)
        persona_id = scenario_data.get('persona')
        if not persona_id:
            # Fallback: try to extract from old "personas" format
            personas_cfg = scenario_data.get('personas') or {}
            if isinstance(personas_cfg, dict):
                entries = personas_cfg.get('entries', [])
                if entries and isinstance(entries[0], dict):
                    persona_id = entries[0].get('id')
                elif entries and isinstance(entries[0], str):
                    persona_id = entries[0]
            # Fallback: try to extract from filename
            if not persona_id:
                persona_id = extract_persona_from_filename(filename)

        return cls(
            name=name,
            tools=tools,
            task=task,
            user_agent=scenario_data.get('user_agent', {}),
            tool_agent=scenario_data.get('tool_agent', {}),
            behavior_types=behavior_types_index,
            persona_id=persona_id
        )

def _resolve_behavior_catalog_path(scenario_dir: Path) -> Path | None:
    """Find data/catalogs/behavior_types.json by walking up from the scenario file's directory."""
    # Try repo-root/data/catalogs/behavior_types.json
    repo_root = Path(__file__).resolve().parent.parent  # src/ -> repo root
    candidate = repo_root / 'data' / 'catalogs' / 'behavior_types.json'
    if candidate.exists():
        return candidate
    # Else walk up from scenario directory
    cur = scenario_dir.resolve()
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
