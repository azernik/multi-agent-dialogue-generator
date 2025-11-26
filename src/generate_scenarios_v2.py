#!/usr/bin/env python3
"""
Generate scenario files for personas based on their use_cases.
Uses domain-specific generators for accurate scenario structure.

Usage:
    python src/generate_scenarios_v2.py --start-persona 56 --count 5
    python src/generate_scenarios_v2.py --persona-ids persona_056 persona_057
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import domain-specific generators
from scenario_generators import banking, calendar_assistant, online_shopping, restaurant_booking, travel


# Mapping from use_case strings to (domain, use_case_folder, prefix, generator_function)
USE_CASE_REGISTRY = {
    # Banking
    "banking.check_account_balance": (
        "banking", "check_account_balance", "ba",
        banking.generate_check_account_balance
    ),
    "banking.dispute_charge": (
        "banking", "dispute_charge", "ba",
        banking.generate_dispute_charge
    ),
    "banking.report_card_lost_or_stolen": (
        "banking", "report_card_lost_or_stolen", "ba_rc",
        banking.generate_report_card_lost_or_stolen
    ),
    
    # Calendar Assistant
    "calendar.reschedule_meeting": (
        "calendar_assistant", "reschedule_meeting", "ca_rm",
        calendar_assistant.generate_reschedule_meeting
    ),
    "calendar.schedule_community_workshop": (
        "calendar_assistant", "schedule_meeting", "ca_sm",
        calendar_assistant.generate_schedule_meeting
    ),
    "calendar.schedule_cross_functional_team_meeting": (
        "calendar_assistant", "schedule_meeting", "ca_sm",
        calendar_assistant.generate_schedule_meeting
    ),
    "calendar.schedule_outdoor_event": (
        "calendar_assistant", "outdoor_event", "ca_oe",
        calendar_assistant.generate_outdoor_event
    ),
    "calendar.schedule_recurring_one_on_one_meeting": (
        "calendar_assistant", "recurring_one_on_one", "ca_ro",
        calendar_assistant.generate_recurring_one_on_one
    ),
    
    # Online Shopping
    "online_shopping.order_gardening_supplies": (
        "online_shopping", "track_order", "os_to",
        online_shopping.generate_track_order
    ),
    "online_shopping.order_gift": (
        "online_shopping", "track_order", "os_to",
        online_shopping.generate_track_order
    ),
    "online_shopping.return_order": (
        "online_shopping", "return_order", "os_ro",
        online_shopping.generate_return_order
    ),
    "online_shopping.cancel_order": (
        "online_shopping", "cancel_order", "os_co",
        online_shopping.generate_cancel_order
    ),
    
    # Restaurant Booking
    "restaurant_booking.dine_in_brunch": (
        "restaurant_booking", "dine_in", "rb",
        restaurant_booking.generate_dine_in
    ),
    "restaurant_booking.dine_in_dinner": (
        "restaurant_booking", "dine_in", "rb",
        restaurant_booking.generate_dine_in
    ),
    "restaurant_booking.plan_group_dinner": (
        "restaurant_booking", "dine_in", "rb",
        restaurant_booking.generate_dine_in
    ),
    "restaurant_booking.plan_special_occasion": (
        "restaurant_booking", "dine_in", "rb",
        restaurant_booking.generate_dine_in
    ),
    
    # Travel
    "travel.book_flight": (
        "travel", "book_flight", "tr_bf",
        travel.generate_book_flight
    ),
    "travel.book_hotel": (
        "travel", "book_hotel", "tr_bh",
        travel.generate_book_hotel
    ),
    "travel.change_flight": (
        "travel", "book_flight", "tr_bf",
        travel.generate_book_flight
    ),
    "travel.check_flight_status": (
        "travel", "book_flight", "tr_bf",
        travel.generate_book_flight
    ),
}


def load_personas(catalog_path: Path) -> List[Dict[str, Any]]:
    """Load personas from catalog file."""
    with open(catalog_path, 'r') as f:
        catalog = json.load(f)
    return catalog.get('personas', [])


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
    generator_func: Callable
) -> Optional[Dict[str, Any]]:
    """Generate a scenario using the domain-specific generator."""
    if use_case not in USE_CASE_REGISTRY:
        return None
    
    domain, use_case_folder, prefix, _ = USE_CASE_REGISTRY[use_case]
    scenario_id = f"{prefix}_{scenario_number:03d}"
    
    # Add temporary hint for generators that need it
    persona_copy = persona.copy()
    persona_copy['_temp_use_case'] = use_case
    
    try:
        scenario = generator_func(persona_copy, scenario_id)
        return scenario
    except Exception as e:
        print(f"\n    Error in generator: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Generate scenarios for personas using domain-specific templates"
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
            
            domain, use_case_folder, prefix, generator_func = USE_CASE_REGISTRY[use_case]
            domain_path = domains_path / domain / use_case_folder
            
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
                    generator_func
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

