#!/usr/bin/env python3
"""
Orchestrator script to run multiple scenarios in a use case or domain directory.

Usage:
    python src/orchestrate.py data/domains/online_shopping/return_order
    python src/orchestrate.py data/domains/online_shopping --use-case return_order
    python src/orchestrate.py data/domains/online_shopping/return_order/os_ro_001  # single scenario
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


def find_scenario_directories(target_path: Path, use_case: Optional[str] = None) -> List[Path]:
    """Find all scenario directories containing scenario.json files."""
    scenarios = []
    
    if not target_path.exists():
        raise FileNotFoundError(f"Path not found: {target_path}")
    
    # If it's a single scenario directory (has scenario.json)
    if target_path.is_dir() and (target_path / "scenario.json").exists():
        return [target_path]
    
    # If use_case is specified, look in that subdirectory
    if use_case:
        use_case_path = target_path / use_case
        if not use_case_path.exists():
            raise FileNotFoundError(f"Use case directory not found: {use_case_path}")
        target_path = use_case_path
    
    # Find all subdirectories containing scenario.json
    for item in target_path.iterdir():
        if item.is_dir():
            scenario_file = item / "scenario.json"
            if scenario_file.exists():
                scenarios.append(item)
    
    if not scenarios:
        raise ValueError(f"No scenario directories found in {target_path}")
    
    return sorted(scenarios)


def load_scenario_personas(scenario_path: Path) -> List[Optional[str]]:
    """Load persona IDs from scenario.json. Returns list of persona IDs or [None] if none specified."""
    scenario_file = scenario_path / "scenario.json"
    with open(scenario_file, 'r') as f:
        data = json.load(f)
    
    personas = data.get("personas", {})
    entries = personas.get("entries", [])
    
    if not entries:
        return [None]  # No personas specified, will use default
    
    persona_ids = []
    for entry in entries:
        if isinstance(entry, dict):
            persona_id = entry.get("id")
            if persona_id:
                persona_ids.append(persona_id)
        elif isinstance(entry, str):
            persona_ids.append(entry)
    
    return persona_ids if persona_ids else [None]


def extract_output_directory(stderr: str) -> Optional[Path]:
    """Extract output directory path from simulate.py stderr output."""
    # simulate.py prints: "Conversation file: data/outputs/..."
    match = re.search(r'Conversation file: (.+?)/conversation\.json', stderr)
    if match:
        repo_root = Path(__file__).resolve().parent.parent
        output_rel = match.group(1)
        return repo_root / output_rel
    return None


def check_eval_success(output_dir: Path) -> Optional[bool]:
    """Check if eval.json exists and SUCCESS is true."""
    eval_file = output_dir / "eval.json"
    if not eval_file.exists():
        return None
    
    try:
        with open(eval_file, 'r') as f:
            eval_data = json.load(f)
        return eval_data.get("SUCCESS") is True
    except (json.JSONDecodeError, KeyError):
        return None


def copy_to_valid_outputs(
    output_dir: Path,
    scenario_path: Path,
    persona_id: Optional[str],
    valid_outputs_root: Path
) -> Optional[Path]:
    """Copy successful simulation to valid_outputs directory. Returns destination path."""
    # Extract domain/use_case/scenario_id from scenario_path
    parts = scenario_path.resolve().parts
    try:
        domains_idx = parts.index("domains")
        if domains_idx + 3 <= len(parts):
            domain = parts[domains_idx + 1]
            use_case = parts[domains_idx + 2]
            scenario_id = parts[domains_idx + 3]
        else:
            # Fallback: use scenario name
            domain = "unknown"
            use_case = "unknown"
            scenario_id = scenario_path.name
    except ValueError:
        # Fallback if "domains" not in path
        domain = "unknown"
        use_case = "unknown"
        scenario_id = scenario_path.name
    
    # Create destination structure: valid_outputs/<domain>/<use_case>/<scenario_id>__<persona>__<timestamp>/
    persona_str = persona_id or "default"
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dest_dir = valid_outputs_root / domain / use_case / f"{scenario_id}__{persona_str}__{timestamp}"
    
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy key files
    files_to_copy = ["conversation.json", "eval.json"]
    copied_files = []
    
    for filename in files_to_copy:
        src_file = output_dir / filename
        if src_file.exists():
            dest_file = dest_dir / filename
            shutil.copy2(src_file, dest_file)
            copied_files.append(filename)
    
    if copied_files:
        return dest_dir
    return None


def run_scenario(
    scenario_path: Path,
    persona_id: Optional[str],
    base_args: List[str],
    dry_run: bool = False,
    copy_valid: bool = False,
    valid_outputs_root: Optional[Path] = None
) -> Dict[str, Any]:
    """Run a single scenario and return result summary."""
    scenario_name = scenario_path.name
    persona_str = persona_id or "default"
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Running scenario: {scenario_name} (persona: {persona_str})", file=sys.stderr)
    
    cmd = [
        sys.executable,
        str(Path(__file__).parent / "simulate.py"),
        str(scenario_path),
    ] + base_args
    
    if persona_id:
        cmd.extend(["--persona-id", persona_id])
    
    if dry_run:
        print(f"  Command: {' '.join(cmd)}", file=sys.stderr)
        return {
            "scenario": scenario_name,
            "persona": persona_id,
            "status": "dry_run",
            "success": None
        }
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout per scenario
        )
        
        # Try to extract success status from stderr (where simulate.py prints it)
        success = None
        eval_success = None
        copied_to_valid = None
        
        if result.returncode == 0:
            # Check for [DONE_SUCCESS] or [DONE_FAILURE] in output
            if "[DONE_SUCCESS]" in result.stderr or "[DONE_SUCCESS]" in result.stdout:
                success = True
            elif "[DONE_FAILURE]" in result.stderr or "[DONE_FAILURE]" in result.stdout:
                success = False
            else:
                # Check return code - 0 typically means success
                success = True
            
            # Extract output directory and check eval if --run-eval was used
            output_dir = extract_output_directory(result.stderr)
            if output_dir and output_dir.exists():
                eval_success = check_eval_success(output_dir)
                
                # Copy to valid_outputs if eval succeeded and flag is set
                if copy_valid and eval_success is True and valid_outputs_root:
                    copied_to_valid = copy_to_valid_outputs(
                        output_dir, scenario_path, persona_id, valid_outputs_root
                    )
                    if copied_to_valid:
                        print(f"  ✓ Copied to valid_outputs: {copied_to_valid.relative_to(valid_outputs_root)}", file=sys.stderr)
        else:
            success = False
        
        return {
            "scenario": scenario_name,
            "persona": persona_id,
            "status": "completed",
            "success": success,
            "eval_success": eval_success,
            "copied_to_valid": str(copied_to_valid) if copied_to_valid else None,
            "returncode": result.returncode,
            "stdout": result.stdout[-500:] if result.stdout else "",  # Last 500 chars
            "stderr": result.stderr[-500:] if result.stderr else ""
        }
    except subprocess.TimeoutExpired:
        return {
            "scenario": scenario_name,
            "persona": persona_id,
            "status": "timeout",
            "success": False
        }
    except Exception as e:
        return {
            "scenario": scenario_name,
            "persona": persona_id,
            "status": "error",
            "success": False,
            "error": str(e)
        }


def main():
    parser = argparse.ArgumentParser(
        description="Orchestrate running multiple scenarios in a use case or domain directory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all scenarios in a use case
  python src/orchestrate.py data/domains/online_shopping/return_order
  
  # Run all scenarios in a domain (all use cases)
  python src/orchestrate.py data/domains/online_shopping
  
  # Run specific use case within a domain
  python src/orchestrate.py data/domains/online_shopping --use-case return_order
  
  # Run single scenario
  python src/orchestrate.py data/domains/online_shopping/return_order/os_ro_001
  
  # Dry run to see what would be executed
  python src/orchestrate.py data/domains/online_shopping/return_order --dry-run
        """
    )
    parser.add_argument(
        "target_path",
        help="Path to scenario directory, use case directory, or domain directory"
    )
    parser.add_argument(
        "--use-case",
        help="If target_path is a domain, specify use case to run (e.g., 'return_order')"
    )
    parser.add_argument(
        "--persona-id",
        help="Override persona ID for all scenarios (if not specified, uses personas from scenario.json)"
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="LLM model to use (default: gpt-4o-mini)"
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=20,
        help="Maximum conversation turns (default: 20)"
    )
    parser.add_argument(
        "--run-eval",
        action="store_true",
        help="Run evaluation after each conversation"
    )
    parser.add_argument(
        "--eval-model",
        default="gpt-4.1-mini",
        help="Model for evaluation (default: gpt-4.1-mini)"
    )
    parser.add_argument(
        "--skip-faithfulness",
        action="store_true",
        help="Skip faithfulness evaluation"
    )
    parser.add_argument(
        "--skip-role-confusion",
        action="store_true",
        help="Skip role confusion evaluation"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be run without actually running scenarios"
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for summary JSON (default: outputs root)"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Number of scenarios to run in parallel (default: 1, sequential)"
    )
    parser.add_argument(
        "--copy-valid",
        action="store_true",
        help="Copy successful simulations (SUCCESS=true in eval) to valid_outputs directory"
    )
    parser.add_argument(
        "--valid-outputs-dir",
        help="Directory for valid outputs (default: data/valid_outputs)"
    )
    
    args = parser.parse_args()
    
    target_path = Path(args.target_path).resolve()
    
    # Find all scenario directories
    try:
        scenarios = find_scenario_directories(target_path, args.use_case)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(scenarios)} scenario(s) to run", file=sys.stderr)
    
    # Determine valid_outputs root
    if args.copy_valid:
        if args.valid_outputs_dir:
            valid_outputs_root = Path(args.valid_outputs_dir).resolve()
        else:
            repo_root = Path(__file__).resolve().parent.parent
            valid_outputs_root = repo_root / "data" / "valid_outputs"
        
        if not args.run_eval:
            print("Warning: --copy-valid requires --run-eval to check eval results", file=sys.stderr)
            args.copy_valid = False
            valid_outputs_root = None
    else:
        valid_outputs_root = None
    
    # Build base arguments for simulate.py
    base_args = [
        "--model", args.model,
        "--max-turns", str(args.max_turns),
    ]
    
    if args.run_eval:
        base_args.append("--run-eval")
        base_args.extend(["--eval-model", args.eval_model])
        if args.skip_faithfulness:
            base_args.append("--skip-faithfulness")
        if args.skip_role_confusion:
            base_args.append("--skip-role-confusion")
    
    # Collect results
    results = []
    start_time = datetime.now()
    
    # Run each scenario
    for scenario_path in scenarios:
        # If persona_id override is specified, use it; otherwise load from scenario
        if args.persona_id:
            persona_ids = [args.persona_id]
        else:
            persona_ids = load_scenario_personas(scenario_path)
        
        # Run for each persona
        for persona_id in persona_ids:
            result = run_scenario(
                scenario_path, 
                persona_id, 
                base_args, 
                args.dry_run,
                copy_valid=args.copy_valid,
                valid_outputs_root=valid_outputs_root
            )
            results.append(result)
            
            # Print immediate feedback
            if not args.dry_run:
                status_icon = "✓" if result.get("success") else "✗" if result.get("success") is False else "?"
                print(f"  {status_icon} {result['scenario']} ({result['persona'] or 'default'}) - {result['status']}", file=sys.stderr)
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Summary statistics
    total = len(results)
    completed = sum(1 for r in results if r["status"] == "completed")
    successful = sum(1 for r in results if r.get("success") is True)
    failed = sum(1 for r in results if r.get("success") is False)
    errors = sum(1 for r in results if r["status"] in ["error", "timeout"])
    eval_successful = sum(1 for r in results if r.get("eval_success") is True)
    copied_to_valid = sum(1 for r in results if r.get("copied_to_valid") is not None)
    
    # Print summary
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Summary:", file=sys.stderr)
    print(f"  Total scenarios: {total}", file=sys.stderr)
    print(f"  Completed: {completed}", file=sys.stderr)
    print(f"  Successful: {successful}", file=sys.stderr)
    print(f"  Failed: {failed}", file=sys.stderr)
    print(f"  Errors/Timeouts: {errors}", file=sys.stderr)
    if args.run_eval:
        print(f"  Eval SUCCESS=true: {eval_successful}", file=sys.stderr)
    if args.copy_valid:
        print(f"  Copied to valid_outputs: {copied_to_valid}", file=sys.stderr)
    if not args.dry_run:
        print(f"  Duration: {duration:.1f}s ({duration/60:.1f} minutes)", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)
    
    # Save summary JSON
    summary = {
        "timestamp": datetime.now().isoformat(),
        "target_path": str(target_path),
        "use_case": args.use_case,
        "total_scenarios": total,
        "completed": completed,
        "successful": successful,
        "failed": failed,
        "errors": errors,
        "eval_successful": eval_successful if args.run_eval else None,
        "copied_to_valid": copied_to_valid if args.copy_valid else None,
        "valid_outputs_root": str(valid_outputs_root) if args.copy_valid else None,
        "duration_seconds": duration if not args.dry_run else None,
        "results": results
    }
    
    # Determine output location
    if args.output_dir:
        output_path = Path(args.output_dir) / "orchestration_summary.json"
    else:
        # Use outputs root
        repo_root = Path(__file__).resolve().parent.parent
        outputs_root = repo_root / "data" / "outputs"
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = outputs_root / f"orchestration_{timestamp}.json"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"Summary saved to: {output_path}", file=sys.stderr)
    
    # Exit with error code if any failures
    if failed > 0 or errors > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

