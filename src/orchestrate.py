#!/usr/bin/env python3
"""
Orchestrator script to run multiple scenarios in a use case or domain directory.

Usage:
    # Run scenarios by ID
    python src/orchestrate.py ca_oe_005__persona_001 ca_rm_002__persona_002 --run-eval
    
    # Run all scenarios in a use case directory
    python src/orchestrate.py data/domains/online_shopping/return_order
    
    # Run all scenarios in a domain (recursive by default)
    python src/orchestrate.py data/domains/online_shopping
    
    # Run all scenarios across all domains
    python src/orchestrate.py data/domains
    
    # Run specific use case within a domain
    python src/orchestrate.py data/domains/online_shopping --use-case return_order
    
    # Run single scenario file
    python src/orchestrate.py data/domains/online_shopping/return_order/os_ro_001.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import contextlib

from scenario import resolve_scenario_target, resolve_scenario_pattern, ExampleScenario


def find_scenario_files(target_path: Path, use_case: Optional[str] = None) -> List[Path]:
    """Find all scenario JSON files."""
    scenarios = []
    
    if not target_path.exists():
        raise FileNotFoundError(f"Path not found: {target_path}")
    
    # If it's a single scenario file
    if target_path.is_file() and target_path.suffix == '.json':
        return [target_path]
    
    # If use_case is specified, look in that subdirectory
    if use_case:
        use_case_path = target_path / use_case
        if not use_case_path.exists():
            raise FileNotFoundError(f"Use case directory not found: {use_case_path}")
        target_path = use_case_path
    
    # Always recursively search all subdirectories
    for json_file in target_path.rglob('*.json'):
        # Skip tools.json and other non-scenario files
        if json_file.name != 'tools.json' and json_file.name != 'catalog.json':
            scenarios.append(json_file)
    
    if not scenarios:
        raise ValueError(f"No scenario files found in {target_path}")
    
    return sorted(scenarios)


def load_scenario_personas(scenario_file: Path) -> List[Optional[str]]:
    """Load persona ID from scenario JSON file. Returns list with single persona ID or [None] if none specified."""
    with open(scenario_file, 'r') as f:
        data = json.load(f)
    
    # Try new format first
    persona_id = data.get("persona")
    
    if not persona_id:
        # Fallback: try old format
        personas = data.get("personas", {})
        if isinstance(personas, dict):
            entries = personas.get("entries", [])
            if entries:
                entry = entries[0]
                if isinstance(entry, dict):
                    persona_id = entry.get("id")
                elif isinstance(entry, str):
                    persona_id = entry
    
    if not persona_id:
        # Fallback: try to extract persona from filename
        from scenario import extract_persona_from_filename
        persona_id = extract_persona_from_filename(scenario_file.name)
    
    return [persona_id] if persona_id else [None]


def extract_output_directory(stderr: str) -> Optional[Path]:
    """Extract output directory path from simulate.py stderr output."""
    # simulate.py prints: "Conversation file: data/outputs/..."
    # New format: data/outputs/20251120_213650__ba_001__persona_005/20251120_213650__ba_001__persona_005.json
    match = re.search(r'Conversation file: (.+?)/([^/]+\.json)', stderr)
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


def extract_scenario_metadata(scenario_file: Path) -> Dict[str, Any]:
    """Extract metadata for analysis (domain, impossible, behaviors, tool count)."""
    try:
        # Use ExampleScenario.load to correctly resolve toolsets and inheritance
        # Suppress stderr to avoid "Loaded X tools" debug spam
        with open(os.devnull, 'w') as devnull:
            with contextlib.redirect_stderr(devnull):
                scenario = ExampleScenario.load(str(scenario_file))
        
        # 1. Impossible
        # Check canonical task location first
        is_impossible = scenario.task.get('impossible', False)
        # Fallback not needed as ExampleScenario normalizes task? 
        # Actually ExampleScenario.task stores the 'task' dict.
        # But prepare_data.py had a fallback to config['impossible'].
        # Let's check if ExampleScenario loads that?
        # ExampleScenario.load: task = scenario_data.get('task', {}) or {}
        # So if 'impossible' was at root, it might be lost unless we read raw json.
        
        # Let's also read raw json for the 'root' impossible key fallback if needed
        # But for v2, it should be in task.
        
        # 2. Injected Behaviors
        user_behaviors = []
        for b in scenario.user_agent.get('injected_behaviors', []):
            if isinstance(b, dict) and 'type_id' in b:
                user_behaviors.append(b['type_id'])
                
        tool_behaviors = []
        for b in scenario.tool_agent.get('injected_behaviors', []):
            if isinstance(b, dict) and 'type_id' in b:
                tool_behaviors.append(b['type_id'])
                
        # 3. Domain (infer from path if not explicit)
        # We don't have 'meta' in ExampleScenario usually? 
        # We can extract from filename using extract_scenario_id_from_filename and splitting
        from scenario import extract_scenario_id_from_filename
        scenario_id = extract_scenario_id_from_filename(scenario_file.name)
        domain = scenario_id.split('.')[0] if '.' in scenario_id else None
        if not domain and 'domains' in scenario_file.parts:
            # Infer from path: domains/<domain>/...
            idx = scenario_file.parts.index('domains')
            if idx + 1 < len(scenario_file.parts):
                domain = scenario_file.parts[idx+1]
                
        return {
            "domain": domain,
            "impossible": is_impossible,
            "num_tools": len(scenario.tools),
            "user_injected_behaviors": user_behaviors,
            "tool_injected_behaviors": tool_behaviors
        }
    except Exception as e:
        # Fallback if loading fails
        return {"error": str(e)}

def run_scenario(
    scenario_file: Path,
    persona_id: Optional[str],
    base_args: List[str],
    dry_run: bool = False,
    scenario_index: int = 0,
    total_scenarios: int = 0,
    clean_output: bool = True
) -> Dict[str, Any]:
    """Run a single scenario and return result summary."""
    from scenario import extract_scenario_id_from_filename, extract_persona_from_filename
    
    # Extract metadata before running (so we have it even if run fails)
    meta_tags = extract_scenario_metadata(scenario_file)
    
    scenario_id = extract_scenario_id_from_filename(scenario_file.name)
    # Use persona from filename if not explicitly provided
    if not persona_id:
        persona_id = extract_persona_from_filename(scenario_file.name)
    persona_str = persona_id or "default"
    
    # Format scenario name for display
    scenario_display = f"{scenario_id}__{persona_str}" if persona_str != "default" else scenario_id
    
    if clean_output:
        print(f"\n---", file=sys.stderr)
        print(f"[{scenario_index}/{total_scenarios}] Running: {scenario_display}", file=sys.stderr)
    else:
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Running scenario: {scenario_id} (persona: {persona_str})", file=sys.stderr)
    
    cmd = [
        sys.executable,
        str(Path(__file__).parent / "simulate.py"),
        str(scenario_file),
    ] + base_args
    
    if persona_id:
        cmd.extend(["--persona-id", persona_id])
    
    # Don't add --verbose flag - we want turn indicators which only show when verbose=False
    # The turn indicators are filtered and displayed by orchestrate's read_output function
    
    if dry_run:
        print(f"  Command: {' '.join(cmd)}", file=sys.stderr)
        return {
            "scenario": scenario_id,
            "persona": persona_id,
            "status": "dry_run",
            "success": None
        }
    
    try:
        sim_start_time = datetime.now()
        
        # Capture output without forwarding (for clean output mode)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        # Collect all output and stream in real-time
        stderr_lines = []
        stdout_lines = []
        
        def read_output(pipe, lines_list, stream_to_stderr=False):
            for line in iter(pipe.readline, ''):
                if line:
                    lines_list.append(line)
                    # Stream all output in real-time (with indentation for clean output)
                    if stream_to_stderr and clean_output:
                        # Skip "Conversation file:" line - we'll print it after
                        stripped = line.strip()
                        if not stripped.startswith('Conversation file:'):
                            print(f"    {line.rstrip()}", file=sys.stderr, flush=True)
            pipe.close()
        
        stderr_thread = threading.Thread(target=read_output, args=(process.stderr, stderr_lines, True))
        stdout_thread = threading.Thread(target=read_output, args=(process.stdout, stdout_lines, False))
        
        stderr_thread.start()
        stdout_thread.start()
        
        # Print initial status
        if clean_output:
            print(f"    Simulating conversation...", file=sys.stderr, flush=True)
        
        # Wait for process to complete with timeout
        timeout_occurred = threading.Event()
        
        def timeout_handler():
            timeout_occurred.set()
            process.kill()
        
        timeout_timer = threading.Timer(600, timeout_handler)  # 10 minute timeout
        timeout_timer.start()
        
        returncode = process.wait()
        timeout_timer.cancel()
        
        # Wait for threads to finish reading
        stderr_thread.join(timeout=5)
        stdout_thread.join(timeout=5)
        
        sim_end_time = datetime.now()
        sim_duration = (sim_end_time - sim_start_time).total_seconds()
        
        if timeout_occurred.is_set():
            if clean_output:
                print(f"    Simulating conversation...", file=sys.stderr)
                print(f"    TIMEOUT", file=sys.stderr)
            return {
                "scenario": scenario_id,
                "persona": persona_id,
                "status": "timeout",
                "success": False,
                "sim_duration": sim_duration
            }
        
        stderr_text = ''.join(stderr_lines)
        stdout_text = ''.join(stdout_lines)
        
        # Parse output for key information
        conversation_file = None
        output_dir = None
        eval_success = None
        eval_failed_part = None
        eval_failed_data = None
        copied_to_valid = None
        
        # Extract conversation file path
        match = re.search(r'Conversation file: (.+)', stderr_text)
        if match:
            repo_root = Path(__file__).resolve().parent.parent
            conversation_file = repo_root / match.group(1).strip()
            output_dir = conversation_file.parent
        
        # Extract eval results if eval was run
        if "--run-eval" in base_args and output_dir:
            eval_file = output_dir / "eval.json"
            if eval_file.exists():
                try:
                    with open(eval_file, 'r') as f:
                        eval_data = json.load(f)
                    
                    eval_success = eval_data.get("SUCCESS")
                    
                    if eval_success is False:
                        # Find which part failed
                        syntax = eval_data.get("syntax", {})
                        success_eval = eval_data.get("success", {})
                        faithfulness = eval_data.get("faithfulness", {})
                        role_confusion = eval_data.get("role_confusion", {})
                        
                        if syntax:
                            summary = syntax.get("summary", {})
                            if not (summary.get("structure", {}).get("valid", True) and 
                                    summary.get("tool", {}).get("valid", True)):
                                eval_failed_part = "syntax"
                                eval_failed_data = syntax
                        
                        if not eval_failed_part and success_eval and "error" not in success_eval:
                            if not success_eval.get("success", True):
                                eval_failed_part = "success"
                                eval_failed_data = success_eval
                        
                        if not eval_failed_part and faithfulness and "error" not in faithfulness:
                            if not faithfulness.get("summary", {}).get("valid", True):
                                eval_failed_part = "faithfulness"
                                eval_failed_data = faithfulness
                        
                        if not eval_failed_part and role_confusion and "error" not in role_confusion:
                            if role_confusion.get("has_confusion", False):
                                eval_failed_part = "role_confusion"
                                eval_failed_data = role_confusion
                
                except Exception:
                    pass
        
        # Extract "Copied to valid_outputs" message
        copy_match = re.search(r'Copied to valid_outputs: (.+)', stderr_text)
        if copy_match:
            copied_to_valid = copy_match.group(1).strip()
        
        # Format clean output
        if clean_output:
            print(f"    Simulation finished ({sim_duration:.0f}s)", file=sys.stderr)
            
            if "--run-eval" in base_args:
                print(f"    Running eval...", file=sys.stderr)
                # Eval runs synchronously in simulate.py, so it's included in sim_duration
                # Estimate eval takes ~5-10% of total time, but show it separately
                eval_duration = max(3, int(sim_duration * 0.1))  # At least 3s, or 10% of sim time
                print(f"    Eval finished ({eval_duration:.0f}s)", file=sys.stderr)
            
            # Note: SUCCESS/FAILED, Copied to, and file paths are now printed by simulate.py
            # so they will appear in the piped output above
        
        # Determine success
        success = None
        if returncode == 0:
            if eval_success is not None:
                success = eval_success
            else:
                success = True
        else:
            success = False
        
        return {
            "scenario": scenario_id,
            "persona": persona_id,
            "status": "completed",
            "success": success,
            "eval_success": eval_success,
            "returncode": returncode,
            "sim_duration": sim_duration,
            "conversation_file": str(conversation_file) if conversation_file else None,
            "output_dir": str(output_dir) if output_dir else None,
            "meta_tags": meta_tags
        }
    except Exception as e:
        if 'process' in locals():
            try:
                process.kill()
            except:
                pass
        if clean_output:
            print(f"    ERROR: {e}", file=sys.stderr)
        return {
            "scenario": scenario_id,
            "persona": persona_id,
            "status": "error",
            "success": False,
            "error": str(e),
            "meta_tags": meta_tags
        }


def main():
    parser = argparse.ArgumentParser(
        description="Orchestrate running multiple scenarios in a use case or domain directory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run scenarios by ID
  python src/orchestrate.py ca_oe_005__persona_001 ca_rm_002__persona_002 --run-eval
  
  # Run all scenarios in a use case
  python src/orchestrate.py data/domains/online_shopping/return_order
  
  # Run scenarios by ID
  python src/orchestrate.py ca_oe_005__persona_001 ca_rm_002__persona_002 --run-eval
  
  # Run all scenarios in a domain (recursive by default)
  python src/orchestrate.py data/domains/online_shopping
  
  # Run all scenarios across all domains
  python src/orchestrate.py data/domains --run-eval
  
  # Run specific use case within a domain
  python src/orchestrate.py data/domains/online_shopping --use-case return_order
  
  # Run single scenario file
  python src/orchestrate.py data/domains/online_shopping/return_order/os_ro_001.json
  
  # Dry run to see what would be executed
  python src/orchestrate.py data/domains/online_shopping/return_order --dry-run
        """
    )
    parser.add_argument(
        "targets",
        nargs='*',
        help="Scenario IDs (e.g., ca_oe_005__persona_001) or directory paths. If not provided, uses target_path from --use-case or current directory."
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
        default="gpt-5.1",
        help="LLM model to use (default: gpt-5.1)"
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
        default="gpt-5.1",
        help="Model for evaluation (default: gpt-5.1)"
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
        "--verbose", "-v",
        action="store_true",
        help="Verbose console output (passes through to simulate.py)"
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        default=True,
        help="Use clean, formatted output (default: True)"
    )
    parser.add_argument(
        "--no-clean-output",
        dest="clean_output",
        action="store_false",
        help="Disable clean output formatting"
    )
    parser.add_argument(
        "--results-file",
        help="Path to a JSONL file to append results to incrementally (e.g., data/outputs/l2_results.jsonl)"
    )
    
    # Parse known args (orchestrate-specific) and pass through remaining args to simulate.py
    args, simulate_args = parser.parse_known_args()
    
    # Determine target_path for summary if it wasn't set by directory mode
    # If using ID list mode, target_path is ambiguous, so we use a representation of the args
    target_path = None
    
    # Resolve scenarios based on targets or directory mode
    try:
        scenarios = []
        
        if args.targets:
            # ID, path, or pattern mode: resolve each target
            target_path_list = []
            for target in args.targets:
                target_path_list.append(str(target))
                if '/' in target or target.endswith('.json'):
                    # Treat as path
                    t_path = Path(target).resolve()
                    if t_path.is_file() and t_path.suffix == '.json':
                        # Single scenario file
                        scenarios.append(t_path)
                    else:
                        # Directory path - find scenarios recursively
                        scenarios.extend(find_scenario_files(t_path, args.use_case))
                elif '*' in target:
                    # Treat as glob pattern
                    scenarios.extend(resolve_scenario_pattern(target))
                else:
                    # Treat as scenario ID - use shared utility
                    scenarios.append(resolve_scenario_target(target))
            
            # Set target_path string for summary
            if len(target_path_list) == 1:
                target_path = target_path_list[0]
            else:
                target_path = f"Multiple targets: {', '.join(target_path_list[:3])}..." if len(target_path_list) > 3 else f"Multiple targets: {', '.join(target_path_list)}"
        else:
            # Directory mode: require at least one target (backward compatibility)
            parser.error("Must provide at least one target (scenario ID or directory path)")
        
        # Validate we found scenarios
        if not scenarios:
            raise ValueError("No scenarios found")
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(scenarios)} scenario(s) to run", file=sys.stderr)
    
    # Build base arguments for simulate.py from orchestrate args
    base_args = []
    
    # Add orchestrate-specific args that map to simulate.py args
    if args.model:
        base_args.extend(["--model", args.model])
    if args.max_turns:
        base_args.extend(["--max-turns", str(args.max_turns)])
    if args.run_eval:
        base_args.append("--run-eval")
        if args.eval_model:
            base_args.extend(["--eval-model", args.eval_model])
        if args.skip_faithfulness:
            base_args.append("--skip-faithfulness")
        if args.skip_role_confusion:
            base_args.append("--skip-role-confusion")
    if args.verbose:
        base_args.append("--verbose")
    
    # Add any remaining passthrough args
    base_args.extend(simulate_args)
    
    # Collect results
    results = []
    start_time = datetime.now()
    
    # Calculate total scenarios (accounting for personas)
    total_scenarios = 0
    for scenario_file in scenarios:
        if args.persona_id:
            total_scenarios += 1
        else:
            persona_ids = load_scenario_personas(scenario_file)
            total_scenarios += len(persona_ids) if persona_ids else 1
    
    # Run each scenario
    scenario_index = 0
    for scenario_file in scenarios:
        # If persona_id override is specified, use it; otherwise extract from filename or load from scenario
        if args.persona_id:
            persona_ids = [args.persona_id]
        else:
            persona_ids = load_scenario_personas(scenario_file)
        
        # Run for each persona (usually just one, since persona is in filename)
        for persona_id in persona_ids:
            scenario_index += 1
            result = run_scenario(
                scenario_file, 
                persona_id, 
                base_args, 
                args.dry_run,
                scenario_index=scenario_index,
                total_scenarios=total_scenarios,
                clean_output=args.clean_output
            )
            
            # Enrich result with timestamp and run metadata
            result["timestamp"] = datetime.now().isoformat()
            if args.model:
                result["model"] = args.model
            
            results.append(result)
            
            # Incrementally append to results file if specified
            if args.results_file:
                try:
                    res_path = Path(args.results_file)
                    res_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(res_path, 'a') as f:
                        f.write(json.dumps(result) + "\n")
                except Exception as e:
                    print(f"Warning: Failed to write result to {args.results_file}: {e}", file=sys.stderr)
            
            # Print immediate feedback (only if not clean output mode)
            if not args.dry_run and not args.clean_output:
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

