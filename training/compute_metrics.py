#!/usr/bin/env python3
"""
Compute success metrics from prediction files.

This is a low-level tool that analyzes one or more prediction JSONL files
and computes success rates, domain breakdowns, and impossibility breakdowns.

Success Definition:
- For each example, success = valid_syntax && type_match && 
  (if gold_type == 'tool' then name_match && args_match else True)
  
This means:
- Syntax must be valid (parseable)
- Type must match (tool vs say)
- For tool actions: both name and args must match
- For say actions: only syntax and type need to match
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional


def compute_success(metrics: Dict, gold_type: str) -> bool:
    """
    Compute per-example success based on metrics.
    
    Args:
        metrics: Dict with valid_syntax, type_match, name_match, args_match
        gold_type: "tool" or "say"
    
    Returns:
        bool: True if example is successful
    """
    if not metrics.get("valid_syntax", False):
        return False
    
    if not metrics.get("type_match", False):
        return False
    
    if gold_type == "tool":
        return metrics.get("name_match", False) and metrics.get("args_match", False)
    else:
        return True


def analyze_predictions_file(predictions_path: Path) -> Dict:
    """
    Analyze a single predictions file and compute metrics.
    
    Returns:
        Dict with overall metrics and breakdowns by domain/impossibility
    """
    results = []
    
    with open(predictions_path, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                results.append(data)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON line: {e}")
                continue
    
    if not results:
        return {
            "error": "No valid results found in file",
            "count": 0
        }
    
    successes = []
    domain_successes = defaultdict(lambda: {"total": 0, "success": 0})
    impossible_successes = defaultdict(lambda: {"total": 0, "success": 0})
    
    for result in results:
        metrics = result.get("metrics", {})
        gold_type = result.get("gold_type", "")
        metadata = result.get("metadata", {})
        
        success = compute_success(metrics, gold_type)
        successes.append(success)
        
        domain = metadata.get("domain")
        if domain is None:
            domain = "apigen_unknown"
        domain_successes[domain]["total"] += 1
        if success:
            domain_successes[domain]["success"] += 1
        
        if "impossible" in metadata:
            impossible = metadata.get("impossible", False)
            impossible_key = "impossible" if impossible else "possible"
            impossible_successes[impossible_key]["total"] += 1
            if success:
                impossible_successes[impossible_key]["success"] += 1
    
    has_impossibility_variation = len(impossible_successes) > 1
    overall_success_rate = sum(successes) / len(successes) if successes else 0.0
    
    domain_rates = {}
    has_domain_variation = len(domain_successes) > 1
    if has_domain_variation:
        for domain, counts in domain_successes.items():
            domain_rates[domain] = {
                "success_rate": counts["success"] / counts["total"] if counts["total"] > 0 else 0.0,
                "total": counts["total"],
                "success": counts["success"]
            }
    
    impossible_rates = {}
    if has_impossibility_variation:
        for key, counts in impossible_successes.items():
            impossible_rates[key] = {
                "success_rate": counts["success"] / counts["total"] if counts["total"] > 0 else 0.0,
                "total": counts["total"],
                "success": counts["success"]
            }
    
    result_dict = {
        "count": len(results),
        "overall_success_rate": overall_success_rate,
        "raw_metrics": {
            "valid_syntax": sum(r.get("metrics", {}).get("valid_syntax", False) for r in results) / len(results),
            "type_match": sum(r.get("metrics", {}).get("type_match", False) for r in results) / len(results),
            "tool_name_match": sum(r.get("metrics", {}).get("name_match", False) for r in results if r.get("gold_type") == "tool") / max(1, sum(1 for r in results if r.get("gold_type") == "tool")),
            "tool_args_match": sum(r.get("metrics", {}).get("args_match", False) for r in results if r.get("gold_type") == "tool") / max(1, sum(1 for r in results if r.get("gold_type") == "tool")),
        }
    }
    
    if has_domain_variation:
        result_dict["by_domain"] = domain_rates
    
    if has_impossibility_variation:
        result_dict["by_impossibility"] = impossible_rates
    
    return result_dict


def main():
    parser = argparse.ArgumentParser(
        description="Analyze prediction files to compute success metrics"
    )
    parser.add_argument(
        "--predictions",
        type=str,
        nargs="+",
        required=True,
        help="Path(s) to prediction JSONL file(s)"
    )
    parser.add_argument(
        "--label",
        type=str,
        default=None,
        help="Label for this analysis (e.g., '32b_epoch1')"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path (default: print to stdout)"
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="json",
        help="Output format: json or table"
    )
    
    args = parser.parse_args()
    
    all_results = {}
    
    for pred_path in args.predictions:
        path = Path(pred_path)
        if not path.exists():
            print(f"Warning: File not found: {path}", file=sys.stderr)
            continue
        
        label = args.label or path.stem
        if args.format == "json":
            print(f"Analyzing: {label}", file=sys.stderr)
            print(f"  File: {path}", file=sys.stderr)
        else:
            print(f"Analyzing: {label}")
            print(f"  File: {path}")
        
        result = analyze_predictions_file(path)
        all_results[label] = result
        
        if "error" in result:
            if args.format == "json":
                print(f"  Error: {result['error']}", file=sys.stderr)
            else:
                print(f"  Error: {result['error']}")
            continue
        
        if args.format == "json":
            print(f"  Count: {result['count']}", file=sys.stderr)
            print(f"  Overall Success Rate: {result['overall_success_rate']:.4f}", file=sys.stderr)
        else:
            print(f"  Count: {result['count']}")
            print(f"  Overall Success Rate: {result['overall_success_rate']:.4f}")
            print()
    
    if args.format == "table":
        print_table(all_results)
    else:
        output = json.dumps(all_results, indent=2)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            if args.format != "json":
                print(f"Results saved to: {args.output}")
        else:
            print(output)


def print_table(results: Dict):
    """Print results in a table format."""
    print("\n" + "=" * 100)
    print("ANALYSIS RESULTS")
    print("=" * 100)
    
    for label, result in results.items():
        if "error" in result:
            print(f"\n{label}: ERROR - {result['error']}")
            continue
        
        print(f"\n{label}:")
        print(f"  Total Examples: {result['count']}")
        print(f"  Overall Success Rate: {result['overall_success_rate']:.4f} ({result['overall_success_rate']*100:.2f}%)")
        
        print(f"\n  Raw Metrics:")
        raw = result['raw_metrics']
        print(f"    Valid Syntax: {raw['valid_syntax']:.4f}")
        print(f"    Type Match: {raw['type_match']:.4f}")
        print(f"    Tool Name Match: {raw['tool_name_match']:.4f}")
        print(f"    Tool Args Match: {raw['tool_args_match']:.4f}")
        
        if result.get('by_domain'):
            print(f"\n  By Domain:")
            for domain, stats in sorted(result['by_domain'].items()):
                print(f"    {domain}: {stats['success_rate']:.4f} ({stats['success']}/{stats['total']})")
        elif not result.get('by_domain') and result.get('count', 0) > 0:
            print(f"\n  By Domain: (skipped - no variation, all examples in same domain)")
        
        if result.get('by_impossibility'):
            print(f"\n  By Impossibility:")
            for key, stats in sorted(result['by_impossibility'].items()):
                print(f"    {key}: {stats['success_rate']:.4f} ({stats['success']}/{stats['total']})")
        elif not result.get('by_impossibility') and result.get('count', 0) > 0:
            print(f"\n  By Impossibility: (skipped - no variation, all examples have same impossibility status)")
    
    print("\n" + "=" * 100)


if __name__ == "__main__":
    main()
