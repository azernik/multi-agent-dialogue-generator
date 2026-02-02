#!/usr/bin/env python3
"""
Failure Analysis and Auto-Fix Script

This script:
1. Scans all failed evaluations in data/outputs/fail/
2. Categorizes failures by type (syntax, success, faithfulness, role_confusion)
3. Attempts to fix issues where possible (primarily syntax)
4. Reruns evaluations after fixes
5. Generates a comprehensive analysis report

Usage:
    python scripts/analyze_and_fix_failures.py [--dry-run] [--fix-syntax] [--output report.json]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Import evaluation modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from eval.syntax import evaluate_conversation, load_conversation_artifact
from eval.success import evaluate_success
from eval.faithfulness import evaluate_faithfulness
from eval.role_confusion import evaluate_role_confusion


@dataclass
class FailureAnalysis:
    """Analysis of a single failed conversation."""
    conversation_id: str
    source_path: Path
    eval_path: Path
    
    # Failure flags
    syntax_failed: bool = False
    success_failed: bool = False
    faithfulness_failed: bool = False
    role_confusion_failed: bool = False
    
    # Detailed failure info
    syntax_errors: Dict[str, Any] = field(default_factory=dict)
    success_reason: Optional[str] = None
    faithfulness_issues: List[Dict[str, Any]] = field(default_factory=list)
    role_confusion_turns: List[int] = field(default_factory=list)
    role_confusion_reason: Optional[str] = None
    
    # Fix status
    fixable: bool = False
    fix_attempted: bool = False
    fix_successful: bool = False
    fix_notes: List[str] = field(default_factory=list)


@dataclass
class AnalysisReport:
    """Overall analysis report."""
    total_failures: int = 0
    by_type: Dict[str, int] = field(default_factory=lambda: {
        "syntax": 0,
        "success": 0,
        "faithfulness": 0,
        "role_confusion": 0
    })
    by_combination: Counter = field(default_factory=Counter)
    
    # Pattern analysis
    syntax_error_patterns: Counter = field(default_factory=Counter)
    success_failure_patterns: List[str] = field(default_factory=list)
    faithfulness_issue_types: Counter = field(default_factory=Counter)
    
    # Fix results
    fixable_count: int = 0
    fix_attempted_count: int = 0
    fix_successful_count: int = 0
    
    # Individual analyses
    analyses: List[FailureAnalysis] = field(default_factory=list)


def scan_failed_evaluations(fail_dir: Path) -> List[Path]:
    """Scan for all eval.json files in fail directory."""
    eval_files = []
    for subdir in fail_dir.iterdir():
        if subdir.is_dir():
            eval_file = subdir / "eval.json"
            if eval_file.exists():
                eval_files.append(eval_file)
    return sorted(eval_files)


def analyze_failure(eval_path: Path) -> FailureAnalysis:
    """Analyze a single failure from eval.json."""
    eval_data = json.loads(eval_path.read_text())
    
    # Find corresponding conversation file
    source_path = Path(eval_data["source_path"])
    if not source_path.exists():
        # Try in same directory as eval
        conv_name = eval_path.parent.name + ".json"
        source_path = eval_path.parent / conv_name
    
    analysis = FailureAnalysis(
        conversation_id=eval_data["conversation_id"],
        source_path=source_path,
        eval_path=eval_path
    )
    
    # Check syntax
    syntax = eval_data.get("syntax", {})
    if not syntax.get("summary", {}).get("structure", {}).get("valid", True):
        analysis.syntax_failed = True
        analysis.syntax_errors = {
            "error_turns": syntax.get("error_turns", []),
            "failure_counts": syntax.get("summary", {}).get("structure", {}).get("failure_counts", {})
        }
        # Syntax errors are potentially fixable
        if "structure_invalid_block_format" in analysis.syntax_errors.get("failure_counts", {}):
            analysis.fixable = True
            analysis.fix_notes.append("Syntax: structure_invalid_block_format may be fixable")
    
    # Check success
    success = eval_data.get("success", {})
    if success and not success.get("success", False):
        analysis.success_failed = True
        analysis.success_reason = success.get("reason", "")
    
    # Check faithfulness
    faithfulness = eval_data.get("faithfulness", {})
    if faithfulness and not faithfulness.get("summary", {}).get("valid", True):
        analysis.faithfulness_failed = True
        analysis.faithfulness_issues = faithfulness.get("error_turns", [])
    
    # Check role confusion
    role_confusion = eval_data.get("role_confusion", {})
    if role_confusion and role_confusion.get("has_confusion", False):
        analysis.role_confusion_failed = True
        analysis.role_confusion_turns = role_confusion.get("confused_turns", [])
        analysis.role_confusion_reason = role_confusion.get("reason", "")
    
    return analysis


def fix_syntax_errors(conversation_path: Path, syntax_errors: Dict[str, Any]) -> bool:
    """Attempt to fix syntax errors in conversation JSON.
    
    Returns True if any fixes were applied.
    """
    if not conversation_path.exists():
        return False
    
    # Load conversation
    conv_data = json.loads(conversation_path.read_text())
    messages = conv_data.get("messages", [])
    
    fixed = False
    error_turns = {et["turn_id"]: et for et in syntax_errors.get("error_turns", [])}
    
    for message in messages:
        if message.get("role") != "assistant":
            continue
        
        turn_id = message.get("turn_id")
        if turn_id not in error_turns:
            continue
        
        steps = message.get("steps", [])
        error_steps = {s["index"]: s for s in error_turns[turn_id].get("steps", [])}
        
        for step in steps:
            step_index = step.get("step_index")
            if step_index not in error_steps:
                continue
            
            output_raw = step.get("output_raw", "")
            if not output_raw:
                continue
            
            # Try to fix common issues
            fixed_output = fix_block_format(output_raw)
            if fixed_output != output_raw:
                step["output_raw"] = fixed_output
                fixed = True
    
    if fixed:
        # Backup original
        backup_path = conversation_path.with_suffix(".json.backup")
        shutil.copy2(conversation_path, backup_path)
        
        # Write fixed version
        conversation_path.write_text(json.dumps(conv_data, indent=2, ensure_ascii=False))
    
    return fixed


def fix_block_format(text: str) -> str:
    """Fix common block format issues in assistant output."""
    original = text
    
    # Fix unclosed think blocks
    if "<think>" in text and "</think>" not in text:
        # Find where think should end (before plan or action)
        think_start = text.find("<think>")
        plan_start = text.find("<plan>", think_start)
        action_start = text.find("<action", think_start)
        
        close_pos = None
        if plan_start != -1:
            close_pos = plan_start
        elif action_start != -1:
            close_pos = action_start
        
        if close_pos:
            text = text[:close_pos] + "</think>\n" + text[close_pos:]
    
    # Fix unclosed plan blocks
    if "<plan>" in text and "</plan>" not in text:
        plan_start = text.find("<plan>")
        action_start = text.find("<action", plan_start)
        
        if action_start != -1:
            text = text[:action_start] + "</plan>\n" + text[action_start:]
    
    # Fix malformed think/plan blocks with content issues
    # Sometimes there are multiple newlines or formatting issues
    text = re.sub(r'<think>\s*\n\s*</think>', '<think>\n</think>', text)
    
    # Fix extra whitespace between blocks
    text = re.sub(r'</think>\s*\n\s*\n\s*<plan>', '</think>\n<plan>', text)
    text = re.sub(r'</plan>\s*\n\s*\n\s*<action', '</plan>\n<action', text)
    
    return text


def rerun_evaluation(conversation_path: Path, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Rerun full evaluation on a conversation."""
    if not conversation_path.exists():
        return {"error": "Conversation file not found"}
    
    try:
        # Syntax evaluation
        artifact = load_conversation_artifact(conversation_path)
        syntax_result = evaluate_conversation(artifact)
        
        # Success evaluation
        success_result = None
        try:
            success_eval = evaluate_success(conversation_path, api_key=api_key)
            success_result = {
                "success": success_eval.success,
                "reason": success_eval.reason,
            }
        except Exception as e:
            success_result = {"error": str(e)}
        
        # Faithfulness evaluation
        faithfulness_result = None
        try:
            faith_report = evaluate_faithfulness(conversation_path, api_key=api_key)
            faithfulness_result = faith_report.to_dict()
        except Exception as e:
            faithfulness_result = {"error": str(e)}
        
        # Role confusion evaluation
        role_result = None
        try:
            role_eval = evaluate_role_confusion(conversation_path, api_key=api_key)
            role_result = {
                "has_confusion": role_eval.has_confusion,
                "reason": role_eval.reason,
                "confused_turns": role_eval.confused_turns,
            }
        except Exception as e:
            role_result = {"error": str(e)}
        
        # Determine overall success
        syntax_dict = syntax_result.to_dict()
        overall_success = True
        
        if not (syntax_dict.get("summary", {}).get("structure", {}).get("valid", False) and
                syntax_dict.get("summary", {}).get("tool", {}).get("valid", False)):
            overall_success = False
        
        if success_result and "error" not in success_result:
            if not success_result.get("success", False):
                overall_success = False
        
        if faithfulness_result and "error" not in faithfulness_result:
            if not faithfulness_result.get("summary", {}).get("valid", False):
                overall_success = False
        
        if role_result and "error" not in role_result:
            if role_result.get("has_confusion", False):
                overall_success = False
        
        return {
            "SUCCESS": overall_success,
            "syntax": syntax_dict,
            "success": success_result,
            "faithfulness": faithfulness_result,
            "role_confusion": role_result,
        }
    
    except Exception as e:
        return {"error": str(e)}


def generate_report(report: AnalysisReport, output_path: Optional[Path] = None) -> str:
    """Generate human-readable analysis report."""
    lines = []
    lines.append("=" * 80)
    lines.append("FAILURE ANALYSIS REPORT")
    lines.append("=" * 80)
    lines.append("")
    
    lines.append(f"Total Failed Conversations: {report.total_failures}")
    lines.append("")
    
    lines.append("Failures by Type:")
    for ftype, count in sorted(report.by_type.items()):
        pct = (count / report.total_failures * 100) if report.total_failures > 0 else 0
        lines.append(f"  {ftype:20s}: {count:4d} ({pct:5.1f}%)")
    lines.append("")
    
    lines.append("Top Failure Combinations:")
    for combo, count in report.by_combination.most_common(10):
        pct = (count / report.total_failures * 100) if report.total_failures > 0 else 0
        lines.append(f"  {combo:40s}: {count:4d} ({pct:5.1f}%)")
    lines.append("")
    
    if report.syntax_error_patterns:
        lines.append("Syntax Error Patterns:")
        for error, count in report.syntax_error_patterns.most_common(10):
            lines.append(f"  {error:40s}: {count:4d}")
        lines.append("")
    
    if report.faithfulness_issue_types:
        lines.append("Faithfulness Issue Types:")
        for issue_type, count in report.faithfulness_issue_types.most_common(10):
            lines.append(f"  {issue_type:40s}: {count:4d}")
        lines.append("")
    
    lines.append("Fix Summary:")
    lines.append(f"  Fixable: {report.fixable_count}")
    lines.append(f"  Fix Attempted: {report.fix_attempted_count}")
    lines.append(f"  Fix Successful: {report.fix_successful_count}")
    if report.fix_attempted_count > 0:
        success_rate = (report.fix_successful_count / report.fix_attempted_count * 100)
        lines.append(f"  Success Rate: {success_rate:.1f}%")
    lines.append("")
    
    # Sample failures for investigation
    lines.append("=" * 80)
    lines.append("SAMPLE FAILURES FOR INVESTIGATION")
    lines.append("=" * 80)
    lines.append("")
    
    # Group by failure type
    by_type: Dict[str, List[FailureAnalysis]] = defaultdict(list)
    for analysis in report.analyses:
        if analysis.syntax_failed:
            by_type["syntax"].append(analysis)
        if analysis.success_failed:
            by_type["success"].append(analysis)
        if analysis.faithfulness_failed:
            by_type["faithfulness"].append(analysis)
        if analysis.role_confusion_failed:
            by_type["role_confusion"].append(analysis)
    
    for ftype, analyses in sorted(by_type.items()):
        lines.append(f"\n{ftype.upper()} FAILURES (showing first 3):")
        lines.append("-" * 80)
        for analysis in analyses[:3]:
            lines.append(f"\nConversation: {analysis.conversation_id}")
            lines.append(f"Path: {analysis.source_path}")
            
            if ftype == "syntax" and analysis.syntax_errors:
                lines.append(f"  Syntax errors: {analysis.syntax_errors.get('failure_counts', {})}")
                lines.append(f"  Error turns: {[t['turn_id'] for t in analysis.syntax_errors.get('error_turns', [])]}")
            
            if ftype == "success" and analysis.success_reason:
                lines.append(f"  Success reason: {analysis.success_reason[:200]}")
            
            if ftype == "faithfulness" and analysis.faithfulness_issues:
                lines.append(f"  Issues in turns: {[i['turn_id'] for i in analysis.faithfulness_issues]}")
                for issue in analysis.faithfulness_issues[:2]:
                    reason = issue.get("issues", [{}])[0].get("reason", "")
                    lines.append(f"    Turn {issue['turn_id']}: {reason[:150]}")
            
            if ftype == "role_confusion":
                lines.append(f"  Confused turns: {analysis.role_confusion_turns}")
                if analysis.role_confusion_reason:
                    lines.append(f"  Reason: {analysis.role_confusion_reason[:200]}")
    
    report_text = "\n".join(lines)
    
    if output_path:
        output_path.write_text(report_text)
        print(f"Report saved to: {output_path}")
    
    return report_text


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze and attempt to fix failed evaluations."
    )
    parser.add_argument(
        "--fail-dir",
        type=Path,
        default=Path("data/outputs/fail"),
        help="Directory containing failed evaluations (default: data/outputs/fail)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze only, don't attempt fixes",
    )
    parser.add_argument(
        "--fix-syntax",
        action="store_true",
        help="Attempt to fix syntax errors",
    )
    parser.add_argument(
        "--reeval",
        action="store_true",
        help="Re-evaluate fixed conversations",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for analysis report",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Output path for JSON analysis data",
    )
    parser.add_argument(
        "--api-key",
        help="OpenAI API key for re-evaluation",
    )
    args = parser.parse_args(argv)
    
    print("Scanning for failed evaluations...")
    eval_files = scan_failed_evaluations(args.fail_dir)
    print(f"Found {len(eval_files)} failed evaluations")
    
    if not eval_files:
        print("No failures found!")
        return 0
    
    print("\nAnalyzing failures...")
    report = AnalysisReport()
    report.total_failures = len(eval_files)
    
    for eval_file in eval_files:
        analysis = analyze_failure(eval_file)
        report.analyses.append(analysis)
        
        # Count by type
        if analysis.syntax_failed:
            report.by_type["syntax"] += 1
            for error_type, count in analysis.syntax_errors.get("failure_counts", {}).items():
                report.syntax_error_patterns[error_type] += count
        
        if analysis.success_failed:
            report.by_type["success"] += 1
            if analysis.success_reason:
                report.success_failure_patterns.append(analysis.success_reason)
        
        if analysis.faithfulness_failed:
            report.by_type["faithfulness"] += 1
            for issue in analysis.faithfulness_issues:
                for detail in issue.get("issues", []):
                    report.faithfulness_issue_types[detail.get("type", "unknown")] += 1
        
        if analysis.role_confusion_failed:
            report.by_type["role_confusion"] += 1
        
        # Count combinations
        combo_parts = []
        if analysis.syntax_failed:
            combo_parts.append("syntax")
        if analysis.success_failed:
            combo_parts.append("success")
        if analysis.faithfulness_failed:
            combo_parts.append("faithfulness")
        if analysis.role_confusion_failed:
            combo_parts.append("role_confusion")
        combo = "+".join(combo_parts) if combo_parts else "unknown"
        report.by_combination[combo] += 1
        
        if analysis.fixable:
            report.fixable_count += 1
    
    # Attempt fixes
    if args.fix_syntax and not args.dry_run:
        print("\nAttempting to fix syntax errors...")
        for analysis in report.analyses:
            if not analysis.fixable or not analysis.syntax_failed:
                continue
            
            print(f"  Fixing {analysis.conversation_id}...")
            analysis.fix_attempted = True
            report.fix_attempted_count += 1
            
            fixed = fix_syntax_errors(analysis.source_path, analysis.syntax_errors)
            
            if fixed:
                analysis.fix_notes.append("Syntax fixes applied")
                
                # Re-evaluate if requested
                if args.reeval:
                    print(f"    Re-evaluating...")
                    new_eval = rerun_evaluation(analysis.source_path, args.api_key)
                    
                    # Check if syntax is now valid
                    if new_eval.get("SUCCESS") or \
                       (new_eval.get("syntax", {}).get("summary", {}).get("structure", {}).get("valid", False)):
                        analysis.fix_successful = True
                        report.fix_successful_count += 1
                        analysis.fix_notes.append("Re-evaluation passed syntax checks")
                        
                        # Save new eval
                        new_eval_path = analysis.eval_path.with_name("eval_fixed.json")
                        new_eval_path.write_text(json.dumps(new_eval, indent=2, ensure_ascii=False))
                        analysis.fix_notes.append(f"New eval saved to {new_eval_path.name}")
                    else:
                        analysis.fix_notes.append("Re-evaluation still shows syntax errors")
            else:
                analysis.fix_notes.append("No fixes could be applied automatically")
    
    # Generate report
    print("\n" + "=" * 80)
    report_text = generate_report(report, args.output)
    print(report_text)
    
    # Save JSON output
    if args.json_output:
        json_data = {
            "summary": {
                "total_failures": report.total_failures,
                "by_type": report.by_type,
                "by_combination": dict(report.by_combination),
                "syntax_error_patterns": dict(report.syntax_error_patterns),
                "faithfulness_issue_types": dict(report.faithfulness_issue_types),
                "fixable_count": report.fixable_count,
                "fix_attempted_count": report.fix_attempted_count,
                "fix_successful_count": report.fix_successful_count,
            },
            "analyses": [
                {
                    "conversation_id": a.conversation_id,
                    "source_path": str(a.source_path),
                    "syntax_failed": a.syntax_failed,
                    "success_failed": a.success_failed,
                    "faithfulness_failed": a.faithfulness_failed,
                    "role_confusion_failed": a.role_confusion_failed,
                    "fixable": a.fixable,
                    "fix_attempted": a.fix_attempted,
                    "fix_successful": a.fix_successful,
                    "fix_notes": a.fix_notes,
                }
                for a in report.analyses
            ]
        }
        args.json_output.write_text(json.dumps(json_data, indent=2, ensure_ascii=False))
        print(f"\nJSON data saved to: {args.json_output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

