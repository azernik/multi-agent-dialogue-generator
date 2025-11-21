#!/usr/bin/env python3
"""
Migration script to convert scenario directory structure to flattened file structure.

Before: return_order/os_ro_001/scenario.json
After:  return_order/os_ro_001__persona_025.json

This script:
1. Finds all scenario directories with scenario.json files
2. Extracts persona from scenario.json
3. Moves scenario.json up one level with new name including persona
4. Deletes the now-empty directory
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Optional


def extract_persona_from_scenario(scenario_file: Path) -> Optional[str]:
    """Extract persona ID from scenario.json file."""
    with open(scenario_file, 'r') as f:
        data = json.load(f)
    
    # Try new format first
    persona_id = data.get("persona")
    if persona_id:
        return persona_id
    
    # Fallback: try old format
    personas = data.get("personas", {})
    if isinstance(personas, dict):
        entries = personas.get("entries", [])
        if entries:
            entry = entries[0]
            if isinstance(entry, dict):
                return entry.get("id")
            elif isinstance(entry, str):
                return entry
    
    return None


def migrate_scenario_directory(scenario_dir: Path, dry_run: bool = False) -> bool:
    """Migrate a single scenario directory to flattened file structure.
    
    Returns True if successful, False otherwise.
    """
    scenario_file = scenario_dir / "scenario.json"
    
    if not scenario_file.exists():
        print(f"  ⚠️  Skipping {scenario_dir.name}: no scenario.json found", file=sys.stderr)
        return False
    
    # Extract persona from scenario.json
    persona_id = extract_persona_from_scenario(scenario_file)
    
    # Build new filename: {scenario_id}__{persona_id}.json
    scenario_id = scenario_dir.name
    if persona_id:
        new_filename = f"{scenario_id}__{persona_id}.json"
    else:
        new_filename = f"{scenario_id}.json"
    
    new_file_path = scenario_dir.parent / new_filename
    
    if new_file_path.exists():
        print(f"  ⚠️  Skipping {scenario_dir.name}: {new_filename} already exists", file=sys.stderr)
        return False
    
    if dry_run:
        print(f"  [DRY RUN] Would migrate: {scenario_dir.name}/scenario.json -> {new_filename}", file=sys.stderr)
        print(f"    Would update toolset_path: ../../tools.json -> ../tools.json", file=sys.stderr)
        return True
    
    # Read scenario.json and update toolset_path if needed
    with open(scenario_file, 'r') as f:
        scenario_data = json.load(f)
    
    # Fix toolset_path: was ../../tools.json (2 levels up), now should be ../tools.json (1 level up)
    domain_ref = scenario_data.get('domain_ref', {}) or {}
    toolset_path = domain_ref.get('toolset_path', '')
    if toolset_path == '../../tools.json':
        scenario_data['domain_ref']['toolset_path'] = '../tools.json'
        print(f"    Updated toolset_path: ../../tools.json -> ../tools.json", file=sys.stderr)
    
    # Write updated content to new location
    try:
        with open(new_file_path, 'w') as f:
            json.dump(scenario_data, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Migrated: {scenario_dir.name}/scenario.json -> {new_filename}", file=sys.stderr)
        
        # Delete the old scenario.json file
        scenario_file.unlink()
        
        # Delete the now-empty directory
        try:
            scenario_dir.rmdir()
            print(f"    Deleted empty directory: {scenario_dir.name}", file=sys.stderr)
        except OSError as e:
            print(f"    ⚠️  Could not delete directory {scenario_dir.name}: {e}", file=sys.stderr)
        
        return True
    except Exception as e:
        print(f"  ✗ Error migrating {scenario_dir.name}: {e}", file=sys.stderr)
        return False


def find_scenario_directories(root_path: Path) -> list[Path]:
    """Find all scenario directories containing scenario.json files."""
    scenarios = []
    
    for item in root_path.rglob("scenario.json"):
        # Skip if in a directory that looks like it's already migrated (has __ in name)
        parent_dir = item.parent
        if "__" in parent_dir.name:
            continue
        scenarios.append(parent_dir)
    
    return sorted(set(scenarios))


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Migrate scenario directories to flattened file structure"
    )
    parser.add_argument(
        "target",
        help="Path to domain directory, use_case directory, or specific scenario directory"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually doing it"
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively search for scenarios in subdirectories"
    )
    
    args = parser.parse_args()
    
    target_path = Path(args.target).resolve()
    
    if not target_path.exists():
        print(f"Error: Path not found: {target_path}", file=sys.stderr)
        sys.exit(1)
    
    # Find scenario directories
    if args.recursive or target_path.is_dir():
        scenarios = find_scenario_directories(target_path)
    elif target_path.is_file() and target_path.name == "scenario.json":
        scenarios = [target_path.parent]
    else:
        print(f"Error: Invalid target path: {target_path}", file=sys.stderr)
        sys.exit(1)
    
    if not scenarios:
        print(f"No scenario directories found in {target_path}", file=sys.stderr)
        sys.exit(0)
    
    print(f"Found {len(scenarios)} scenario(s) to migrate", file=sys.stderr)
    if args.dry_run:
        print("[DRY RUN MODE - no files will be changed]", file=sys.stderr)
    print("", file=sys.stderr)
    
    success_count = 0
    for scenario_dir in scenarios:
        if migrate_scenario_directory(scenario_dir, dry_run=args.dry_run):
            success_count += 1
    
    print(f"\n{'Would migrate' if args.dry_run else 'Migrated'} {success_count}/{len(scenarios)} scenario(s)", file=sys.stderr)
    
    if success_count < len(scenarios):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

