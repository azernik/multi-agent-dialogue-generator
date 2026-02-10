#!/usr/bin/env python3
"""
Update sft_test.jsonl using the list of scenario IDs in test_split.json.

Reads test_split.json, scans the conversation input directory for JSONs whose
scenario_id is in that list, and regenerates sft_test.jsonl using the same
sample-creation logic as prepare_data.py. Use this after updating test_split.json
with new unique scenario IDs so that the test set includes samples for those IDs.

Run from repo root, e.g.:
  python training/update_sft_test_from_split.py
  python training/update_sft_test_from_split.py --input_dir data/valid_outputs/v2 --output_dir training/data
"""

import json
import argparse
import sys
from pathlib import Path

# Repo root and paths so script works from repo root or training/
repo_root = Path(__file__).resolve().parent.parent
training_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "src"))
sys.path.insert(0, str(training_dir))

from prepare_data import (
    load_conversation,
    extract_metadata,
    create_samples_from_conversation,
    get_system_prompt,
)
from scenario import resolve_scenario_id, ExampleScenario, extract_scenario_id_from_filename

# Scenario ID prefix -> domain folder name under data/domains
_SCENARIO_PREFIX_TO_DOMAIN = {
    "ba": "banking",
    "ca": "calendar_assistant",
    "hs": "home_services",
    "os": "online_shopping",
    "rb": "restaurant_booking",
    "tr": "travel",
}


def _load_domain_tools_fallback(scenario_id: str):
    """When scenario file is missing, load tools from domain's tools.json if possible."""
    prefix = scenario_id.split("_")[0] if scenario_id else None
    domain_folder = _SCENARIO_PREFIX_TO_DOMAIN.get(prefix) if prefix else None
    if not domain_folder:
        return None
    tools_path = repo_root / "data" / "domains" / domain_folder / "tools.json"
    if not tools_path.exists():
        return None
    try:
        with open(tools_path, "r") as f:
            data = json.load(f)
        return data.get("tools") if isinstance(data, dict) else None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Update sft_test.jsonl from test_split.json using prepare_data logic"
    )
    parser.add_argument(
        "--input_dir",
        type=str,
        default="data/valid_outputs/v2",
        help="Directory containing conversation JSONs (same as prepare_data.py)",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="training/data",
        help="Directory containing test_split.json and where sft_test.jsonl is written",
    )
    parser.add_argument(
        "--split_file",
        type=str,
        default="training/data/test_split.json",
        help="Path to test_split.json (relative to repo root or absolute)",
    )
    args = parser.parse_args()

    # Resolve paths relative to repo root when not absolute
    input_path = Path(args.input_dir)
    if not input_path.is_absolute():
        input_path = repo_root / input_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    split_file = Path(args.split_file)
    if not split_file.is_absolute():
        split_file = repo_root / split_file

    if not split_file.exists():
        print(f"Error: Split file not found: {split_file}")
        sys.exit(1)

    with open(split_file, "r") as f:
        raw_split = json.load(f)
    test_scenario_ids = set(raw_split) if isinstance(raw_split, list) else set(raw_split.keys())

    print(f"Loaded {len(test_scenario_ids)} scenario IDs from {split_file}")

    def normalize_scenario_id(name: str) -> str:
        """Use short scenario ID for matching (e.g. 'domain.ca_rm_006' -> 'ca_rm_006')."""
        if not name:
            return name
        if "." in name:
            return name.split(".")[-1].strip()
        return name.strip()

    json_files = list(input_path.glob("**/*.json"))
    print(f"Scanning {len(json_files)} conversation files in {input_path}...")

    test_samples = []
    seen_scenarios = set()
    failed = 0

    for json_file in sorted(json_files):
        try:
            conv_data = load_conversation(json_file)
            scenario_name = conv_data.get("config", {}).get("scenario_name")
            if not scenario_name:
                extracted = extract_scenario_id_from_filename(json_file.name)
                scenario_name = extracted.split("__")[-1] if extracted else None
            scenario_name = normalize_scenario_id(scenario_name) if scenario_name else None
            if not scenario_name or scenario_name not in test_scenario_ids:
                continue

            try:
                scenario_path = resolve_scenario_id(scenario_name)
                scenario = ExampleScenario.load(scenario_path)
                tools = scenario.tools
            except Exception as e:
                tools = _load_domain_tools_fallback(scenario_name)
                if not tools:
                    print(f"Warning: Could not resolve scenario '{scenario_name}' for {json_file.name}: {e}")
                    failed += 1
                    continue

            metadata = extract_metadata(conv_data, tools, scenario_name)
            # Always use v3 system prompt for SFT data
            system_prompt = get_system_prompt("v3", base_path=repo_root)
            samples = create_samples_from_conversation(conv_data, system_prompt, tools, metadata)
            test_samples.extend(samples)
            seen_scenarios.add(scenario_name)
        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            failed += 1

    output_dir.mkdir(parents=True, exist_ok=True)
    test_file = output_dir / "new_sft_test.jsonl"
    with open(test_file, "w") as f:
        for sample in test_samples:
            f.write(json.dumps(sample) + "\n")

    print(f"\nWrote {len(test_samples)} test samples to {test_file}")
    print(f"Scenarios with data: {len(seen_scenarios)}")
    if failed:
        print(f"Failed/skipped: {failed}")
    missing = test_scenario_ids - seen_scenarios
    if missing:
        print(f"Scenario IDs in split with no conversations in input_dir: {len(missing)}")
        if len(missing) <= 20:
            print("  ", sorted(missing))
        else:
            print("  (first 20)", sorted(missing)[:20])


if __name__ == "__main__":
    main()
