#!/usr/bin/env python3
"""
Generate scenario files for personas based on their use_cases.
Uses LLM with domain-specific format examples for accurate scenario structure.

Usage:
    python src/generate_scenarios_v2.py --start-persona 56 --count 5
    python src/generate_scenarios_v2.py --persona-ids persona_056 persona_057
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from core import LLMClient


# Mapping from use_case strings to (domain, use_case_folder, prefix, example_file)
# Must match AVAILABLE_USE_CASES in generate_personas.py
USE_CASE_REGISTRY = {
    # Banking (3 use cases)
    "banking.check_account_balance": (
        "banking", "check_account_balance", "ba",
        "ba_001__persona_005.json"
    ),
    "banking.dispute_charge": (
        "banking", "dispute_charge", "ba",
        "ba_001__persona_010.json"
    ),
    "banking.report_card_lost_or_stolen": (
        "banking", "report_card_lost_or_stolen", "ba_rc",
        "ba_rc_001__persona_040.json"
    ),
    
    # Calendar Assistant (4 use cases)
    "calendar.outdoor_event": (
        "calendar_assistant", "outdoor_event", "ca_oe",
        "ca_oe_001__persona_005.json"
    ),
    "calendar.recurring_one_on_one": (
        "calendar_assistant", "recurring_one_on_one", "ca_ro",
        "ca_ro_001__persona_004.json"
    ),
    "calendar.reschedule_meeting": (
        "calendar_assistant", "reschedule_meeting", "ca_rm",
        "ca_rm_001__persona_004.json"
    ),
    "calendar.schedule_meeting": (
        "calendar_assistant", "schedule_meeting", "ca_sm",
        "ca_sm_001__persona_002.json"
    ),
    
    # Online Shopping (3 use cases)
    "online_shopping.cancel_order": (
        "online_shopping", "cancel_order", "os_co",
        "os_co_001__persona_001.json"
    ),
    "online_shopping.return_order": (
        "online_shopping", "return_order", "os_ro",
        "os_ro_001__persona_025.json"
    ),
    "online_shopping.track_order": (
        "online_shopping", "track_order", "os_to",
        "os_to_001__persona_005.json"
    ),
    
    # Restaurant Booking (1 use case)
    "restaurant_booking.dine_in": (
        "restaurant_booking", "dine_in", "rb",
        "rb_001__persona_002.json"
    ),
    
    # Travel (2 use cases)
    "travel.book_flight": (
        "travel", "book_flight", "tr_bf",
        "tr_bf_001__persona_010.json"
    ),
    "travel.book_hotel": (
        "travel", "book_hotel", "tr_bh",
        "tr_bh_001__persona_005.json"
    ),
}


SCENARIO_GENERATION_PROMPT = """You are generating a realistic task scenario for a multi-agent dialogue simulation.

PERSONA INFORMATION:
{persona_info}

TASK: Generate a scenario for the use case "{use_case}" in the "{domain}" domain.

IMPORTANT: Follow the EXACT format and structure of this example scenario below. 
Keep the same field names, nested structure, and data types. 
Generate realistic data that matches the persona's background, location, and occupation.

EXAMPLE SCENARIO TO FOLLOW:
{example_scenario}

INSTRUCTIONS:
1. Use the scenario_id: {scenario_id}
2. Use the persona_id: {persona_id}
3. Keep the same structure as the example
4. Generate realistic constraints, preferences, and seed data
5. Make sure dates are in the future (2025-12 or later)
6. Use persona's hometown, email, occupation for realistic context
7. Generate 2-4 options in seed data (restaurants, flights, hotels, etc.)

Return ONLY valid JSON matching the exact structure of the example."""


def load_personas(catalog_path: Path) -> List[Dict[str, Any]]:
    """Load personas from catalog file."""
    with open(catalog_path, 'r') as f:
        catalog = json.load(f)
    return catalog.get('personas', [])


def load_example_scenario(domains_path: Path, domain: str, use_case_folder: str, example_file: str) -> Optional[Dict[str, Any]]:
    """Load an example scenario file to use as template."""
    example_path = domains_path / domain / use_case_folder / example_file
    
    if not example_path.exists():
        return None
    
    try:
        with open(example_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load example {example_path}: {e}")
        return None


def get_next_scenario_number(domain_folder: Path, prefix: str) -> int:
    """Find the next available scenario number in a domain folder."""
    if not domain_folder.exists():
        return 1
    
    max_num = 0
    pattern = re.compile(rf"{re.escape(prefix)}_(\d+)__persona_\d+\.json")
    
    for file in domain_folder.glob("*.json"):
        match = pattern.match(file.name)
        if match:
            num = int(match.group(1))
            max_num = max(max_num, num)
    
    return max_num + 1


def generate_scenario(
    persona: Dict[str, Any],
    use_case: str,
    scenario_number: int,
    example_scenario: Dict[str, Any],
    llm_client: LLMClient
) -> Optional[Dict[str, Any]]:
    """Generate a scenario using LLM with example scenario as template."""
    if use_case not in USE_CASE_REGISTRY:
        return None
    
    domain, use_case_folder, prefix, _ = USE_CASE_REGISTRY[use_case]
    scenario_id = f"{prefix}_{scenario_number:03d}"
    
    # Prepare persona info
    persona_info = f"""
ID: {persona['id']}
Name: {persona['name']}
Age: {persona['age']}
Occupation: {persona['occupation']}
Hometown: {persona['hometown']}
Bio: {persona['bio']}
Writing Style: {persona.get('writing_style', 'casual')}
Email: {persona.get('email', 'user@example.com')}
Phone: {persona.get('phone', '+1-555-0000')}
"""
    
    # Build prompt
    prompt = SCENARIO_GENERATION_PROMPT.format(
        persona_info=persona_info,
        use_case=use_case,
        domain=domain,
        example_scenario=json.dumps(example_scenario, indent=2),
        scenario_id=scenario_id,
        persona_id=persona['id']
    )
    
    # Call LLM
    messages = [
        {"role": "system", "content": "You are a scenario generation assistant. Output only valid JSON that matches the example format exactly."},
        {"role": "user", "content": prompt}
    ]
    
    try:
        response_text = llm_client.chat_completion(messages, temperature=0.7, max_completion_tokens=2000)
        response_text = response_text.strip()
        
        # Strip out thinking tags if present
        if '<think>' in response_text:
            think_end = response_text.find('</think>')
            if think_end != -1:
                response_text = response_text[think_end + 8:].strip()
        
        # Parse JSON response - handle markdown code blocks
        if '```' in response_text:
            json_match = re.search(r'```(?:json)?\s*(.*?)```', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(1).strip()
        
        # Find JSON object
        json_start = response_text.find('{')
        json_end = response_text.rfind('}')
        if json_start != -1 and json_end != -1:
            response_text = response_text[json_start:json_end+1]
        
        scenario_data = json.loads(response_text)
        
        # Ensure correct IDs
        if 'metadata' in scenario_data:
            scenario_data['metadata']['scenario_id'] = scenario_id
        scenario_data['persona'] = persona['id']
        
        return scenario_data
        
    except json.JSONDecodeError as e:
        print(f"\n    JSON parse error: {e}")
        print(f"    Response preview: {response_text[:300]}")
        return None
    except Exception as e:
        print(f"\n    Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Generate scenarios for personas using LLM with domain-specific examples"
    )
    parser.add_argument(
        '--personas',
        default='data/personas/catalog.json',
        help='Path to persona catalog JSON file'
    )
    parser.add_argument(
        '--domains-dir',
        default='data/domains',
        help='Path to domains directory'
    )
    parser.add_argument(
        '--start-persona',
        type=int,
        help='Starting persona number (e.g., 56 for persona_056)'
    )
    parser.add_argument(
        '--count',
        type=int,
        help='Number of personas to process (starting from start-persona)'
    )
    parser.add_argument(
        '--persona-ids',
        nargs='+',
        help='Specific persona IDs to process (e.g., persona_056 persona_057)'
    )
    parser.add_argument(
        '--model',
        default='gpt-5.1',
        help='LLM model to use (default: gpt-5.1)'
    )
    parser.add_argument(
        '--api-key',
        help='OpenAI API key (default: OPENAI_API_KEY env var)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be generated without actually creating files'
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing scenario files'
    )
    
    args = parser.parse_args()
    
    # Initialize LLM client
    api_key = args.api_key or os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("Error: OpenAI API key required. Set OPENAI_API_KEY or use --api-key")
        return 1
    
    llm_client = LLMClient(model=args.model, api_key=api_key)
    
    # Load personas
    print(f"Loading personas from {args.personas}...")
    personas = load_personas(Path(args.personas))
    print(f"Found {len(personas)} personas in catalog")
    
    # Filter personas based on arguments
    if args.persona_ids:
        personas = [p for p in personas if p['id'] in args.persona_ids]
        print(f"Filtered to {len(personas)} specific personas")
    elif args.start_persona is not None:
        start_idx = args.start_persona - 1
        if args.count:
            personas = personas[start_idx:start_idx + args.count]
        else:
            personas = personas[start_idx:]
        print(f"Processing personas from index {args.start_persona}, count: {len(personas)}")
    
    if not personas:
        print("No personas to process")
        return 1
    
    # Process each persona
    total_scenarios = 0
    skipped_scenarios = 0
    domains_path = Path(args.domains_dir)
    
    for persona in personas:
        persona_id = persona['id']
        use_cases = persona.get('use_cases', [])
        
        if not use_cases:
            print(f"\n⊘ {persona_id} ({persona['name']}): No use cases")
            continue
        
        print(f"\n{'='*60}")
        print(f"Processing {persona_id}: {persona['name']}")
        print(f"Use cases: {len(use_cases)}")
        
        for use_case in use_cases:
            # Map use case to domain
            if use_case not in USE_CASE_REGISTRY:
                print(f"  ⚠ Unknown use case: {use_case}")
                continue
            
            domain, use_case_folder, prefix, example_file = USE_CASE_REGISTRY[use_case]
            domain_path = domains_path / domain / use_case_folder
            
            # Load example scenario
            example_scenario = load_example_scenario(domains_path, domain, use_case_folder, example_file)
            if not example_scenario:
                print(f"  ⚠ No example scenario found for {use_case}")
                continue
            
            # Get next scenario number
            scenario_num = get_next_scenario_number(domain_path, prefix)
            
            # Generate filename
            filename = f"{prefix}_{scenario_num:03d}__{persona_id}.json"
            output_path = domain_path / filename
            
            # Check if file exists
            if output_path.exists() and not args.overwrite:
                print(f"  ⊙ Skipping {use_case}: {filename} already exists")
                skipped_scenarios += 1
                continue
            
            if args.dry_run:
                print(f"  [DRY RUN] Would create: {output_path}")
                continue
            
            print(f"  Generating {use_case}...", end=' ', flush=True)
            
            try:
                scenario = generate_scenario(
                    persona,
                    use_case,
                    scenario_num,
                    example_scenario,
                    llm_client
                )
                
                if scenario:
                    # Create directory if it doesn't exist
                    domain_path.mkdir(parents=True, exist_ok=True)
                    
                    # Write scenario file
                    with open(output_path, 'w') as f:
                        json.dump(scenario, f, indent=2, ensure_ascii=False)
                        f.write('\n')  # Add trailing newline
                    
                    print(f"✓ {filename}")
                    total_scenarios += 1
                else:
                    print(f"✗ Failed to generate")
                    
            except Exception as e:
                print(f"✗ Error: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    print(f"\n{'='*60}")
    print(f"✓ Generated {total_scenarios} scenarios")
    if skipped_scenarios > 0:
        print(f"⊙ Skipped {skipped_scenarios} existing scenarios")
    return 0


if __name__ == '__main__':
    sys.exit(main())

