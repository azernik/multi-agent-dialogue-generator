#!/usr/bin/env python3
"""
Failure Diagnostic Script

This script provides detailed diagnostics and actionable recommendations for fixing failures.
It analyzes each failure type and suggests specific configuration changes based on the
investigation guides in docs/.

Usage:
    python scripts/diagnose_failures.py --conversation-id os_to_001
    python scripts/diagnose_failures.py --eval-file data/outputs/fail/.../eval.json
    python scripts/diagnose_failures.py --batch data/outputs/fail/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class FailureDiagnostic:
    """Provides detailed diagnostics for a failed conversation."""
    
    def __init__(self, eval_data: Dict[str, Any], conversation_data: Dict[str, Any]):
        self.eval_data = eval_data
        self.conversation_data = conversation_data
        self.conversation_id = eval_data.get("conversation_id", "unknown")
        self.config = conversation_data.get("config", {})
    
    def diagnose(self) -> Dict[str, Any]:
        """Run full diagnostic and return recommendations."""
        diagnostics = {
            "conversation_id": self.conversation_id,
            "overall_success": self.eval_data.get("SUCCESS", False),
            "failure_types": self._identify_failure_types(),
            "recommendations": [],
            "severity": "none",
        }
        
        # Diagnose each failure type
        if self._has_syntax_failure():
            diagnostics["recommendations"].extend(self._diagnose_syntax())
            diagnostics["severity"] = "high"
        
        if self._has_success_failure():
            diagnostics["recommendations"].extend(self._diagnose_success())
            if diagnostics["severity"] != "high":
                diagnostics["severity"] = "critical"
        
        if self._has_faithfulness_failure():
            diagnostics["recommendations"].extend(self._diagnose_faithfulness())
            if diagnostics["severity"] == "none":
                diagnostics["severity"] = "high"
        
        if self._has_role_confusion():
            diagnostics["recommendations"].extend(self._diagnose_role_confusion())
            if diagnostics["severity"] == "none":
                diagnostics["severity"] = "medium"
        
        return diagnostics
    
    def _identify_failure_types(self) -> List[str]:
        """Identify which types of failures occurred."""
        types = []
        if self._has_syntax_failure():
            types.append("syntax")
        if self._has_success_failure():
            types.append("success")
        if self._has_faithfulness_failure():
            types.append("faithfulness")
        if self._has_role_confusion():
            types.append("role_confusion")
        return types
    
    def _has_syntax_failure(self) -> bool:
        syntax = self.eval_data.get("syntax", {})
        return not syntax.get("summary", {}).get("structure", {}).get("valid", True)
    
    def _has_success_failure(self) -> bool:
        success = self.eval_data.get("success", {})
        return not success.get("success", False)
    
    def _has_faithfulness_failure(self) -> bool:
        faithfulness = self.eval_data.get("faithfulness", {})
        return not faithfulness.get("summary", {}).get("valid", True)
    
    def _has_role_confusion(self) -> bool:
        role = self.eval_data.get("role_confusion", {})
        return role.get("has_confusion", False)
    
    def _diagnose_syntax(self) -> List[Dict[str, str]]:
        """Diagnose syntax failures."""
        recommendations = []
        syntax = self.eval_data.get("syntax", {})
        error_turns = syntax.get("error_turns", [])
        failure_counts = syntax.get("summary", {}).get("structure", {}).get("failure_counts", {})
        
        for error_type, count in failure_counts.items():
            if error_type == "structure_invalid_block_format":
                recommendations.append({
                    "type": "syntax",
                    "severity": "high",
                    "issue": f"Invalid block format in {count} turn(s)",
                    "affected_turns": [t["turn_id"] for t in error_turns],
                    "root_cause": "Assistant output has malformed XML-like blocks (<think>, <plan>, <action>)",
                    "fix": "Run: python scripts/analyze_and_fix_failures.py --fix-syntax --reeval",
                    "prevention": "Check system agent prompt to ensure it emphasizes proper block formatting. Consider adding examples of correct format."
                })
            
            elif error_type == "structure_missing_block":
                recommendations.append({
                    "type": "syntax",
                    "severity": "high",
                    "issue": f"Missing required blocks in {count} turn(s)",
                    "affected_turns": [t["turn_id"] for t in error_turns],
                    "root_cause": "Assistant didn't include required <think>, <plan>, or <action> blocks",
                    "fix": "This requires regeneration with improved prompt",
                    "prevention": "Update system agent prompt to make block requirements more explicit. Add validation examples."
                })
            
            elif error_type == "structure_unexpected_text":
                recommendations.append({
                    "type": "syntax",
                    "severity": "medium",
                    "issue": f"Unexpected text outside blocks in {count} turn(s)",
                    "affected_turns": [t["turn_id"] for t in error_turns],
                    "root_cause": "Assistant added text outside of proper block structures",
                    "fix": "May be auto-fixable with analyze_and_fix_failures.py",
                    "prevention": "Clarify in prompt that ALL output must be within blocks"
                })
            
            elif error_type == "turn_structure_invalid_say":
                recommendations.append({
                    "type": "syntax",
                    "severity": "high",
                    "issue": f"Invalid say action placement in {count} turn(s)",
                    "affected_turns": [t["turn_id"] for t in error_turns],
                    "root_cause": "Say action is not the last step, or missing, or multiple say actions exist",
                    "fix": "Requires regeneration",
                    "prevention": "Emphasize in prompt: exactly ONE say action, always as the LAST step"
                })
        
        return recommendations
    
    def _diagnose_success(self) -> List[Dict[str, str]]:
        """Diagnose success failures."""
        recommendations = []
        success = self.eval_data.get("success", {})
        reason = success.get("reason", "")
        
        task = self.config.get("task", {})
        success_criteria = task.get("success_criteria", {})
        required_action = success_criteria.get("action", "")
        
        # Check if required tool call is missing
        if "did not" in reason.lower() and "call" in reason.lower():
            tool_name = self._extract_missing_tool_name(reason, required_action)
            
            recommendations.append({
                "type": "success",
                "severity": "critical",
                "issue": f"Missing required tool call: {tool_name}",
                "root_cause": self._diagnose_missing_tool_call(tool_name),
                "investigation_steps": [
                    "1. Check if tool requires parameters not available in slots or seed data",
                    "2. Check if user agent provided all necessary information in conversation",
                    "3. Verify seed data contains entities referenced by user agent",
                    "4. Check if success criteria requirements are achievable with current configuration"
                ],
                "fix": self._suggest_missing_tool_fix(tool_name),
                "reference": "See docs/failure_investigation_guide.md (Step 3-7)"
            })
        
        # Check for hallucination mentioned in success reason
        elif "hallucin" in reason.lower() or "claim" in reason.lower():
            recommendations.append({
                "type": "success",
                "severity": "critical",
                "issue": "Assistant claimed action completion without executing it",
                "root_cause": "Assistant reasoning block described tool calls that never occurred",
                "fix": "Improve system prompt to prevent reasoning/action mismatch. Regenerate conversation.",
                "prevention": "Add explicit instruction: 'Execute tool calls in action block, not just describe them in reasoning'",
                "reference": "See docs/common_issues_by_domain.md - 'hallucinating tool calls/results'"
            })
        
        # Configuration mismatch
        elif "mismatch" in reason.lower() or "different" in reason.lower():
            recommendations.append({
                "type": "success",
                "severity": "critical",
                "issue": "Configuration mismatch between user agent and seed data",
                "root_cause": "User agent references entities (IDs, names, details) that don't exist in seed data",
                "investigation_steps": [
                    "1. Compare user messages with seed data entities",
                    "2. Check if IDs, names, dates, amounts mentioned by user match seed data",
                    "3. Verify injected_behaviors aren't describing scenario setup instead of user behavior"
                ],
                "fix": "Update seed data to match user agent references, OR update user agent to reference what exists in seed data",
                "reference": "See docs/failure_investigation_guide.md (Step 4)"
            })
        
        else:
            recommendations.append({
                "type": "success",
                "severity": "critical",
                "issue": "Task not completed successfully",
                "reason": reason[:200],
                "fix": "Review conversation transcript and follow investigation workflow",
                "reference": "See docs/failure_investigation_guide.md"
            })
        
        return recommendations
    
    def _diagnose_faithfulness(self) -> List[Dict[str, str]]:
        """Diagnose faithfulness failures."""
        recommendations = []
        faithfulness = self.eval_data.get("faithfulness", {})
        error_turns = faithfulness.get("error_turns", [])
        
        # Group by issue type
        tool_issues = []
        say_issues = []
        
        for error_turn in error_turns:
            action_type = error_turn.get("action_type", "")
            turn_id = error_turn.get("turn_id")
            issues = error_turn.get("issues", [])
            
            for issue in issues:
                issue_type = issue.get("type", "")
                reason = issue.get("reason", "")
                
                if action_type == "tool" or issue_type == "slot_value_faithfulness":
                    tool_issues.append((turn_id, reason))
                else:
                    say_issues.append((turn_id, reason))
        
        if tool_issues:
            recommendations.append({
                "type": "faithfulness",
                "severity": "high",
                "issue": "Tool call parameters not compatible with user intent",
                "affected_turns": [t for t, _ in tool_issues],
                "examples": [f"Turn {t}: {r[:100]}" for t, r in tool_issues[:3]],
                "root_cause": "Assistant used parameter values that don't match user's stated preferences or contradict conversation context",
                "fix": "This indicates agent behavior issues. May need to regenerate with improved prompts or check for configuration mismatches.",
                "prevention": "Ensure tool parameters align with user intent. Check that slots/preferences are properly conveyed to assistant."
            })
        
        if say_issues:
            recommendations.append({
                "type": "faithfulness",
                "severity": "high",
                "issue": "Assistant statements not grounded in tool results",
                "affected_turns": [t for t, _ in say_issues],
                "examples": [f"Turn {t}: {r[:100]}" for t, r in say_issues[:3]],
                "root_cause": "Assistant made claims or provided information not present in tool responses (hallucination)",
                "fix": "Requires regeneration. Update system prompt to emphasize grounding in tool responses only.",
                "prevention": "Add explicit instruction: 'Only relay information directly from tool responses. Do not infer, assume, or add details not in tool output.'",
                "reference": "See docs/common_issues_by_domain.md - faithfulness failures"
            })
        
        return recommendations
    
    def _diagnose_role_confusion(self) -> List[Dict[str, str]]:
        """Diagnose role confusion failures."""
        recommendations = []
        role = self.eval_data.get("role_confusion", {})
        confused_turns = role.get("confused_turns", [])
        reason = role.get("reason", "")
        
        recommendations.append({
            "type": "role_confusion",
            "severity": "medium",
            "issue": "User agent confused its role and acted like an assistant",
            "affected_turns": confused_turns,
            "reason": reason[:200],
            "root_cause": "User agent phrasing suggests offering help TO the assistant or asking questions TO assist the assistant's workflow",
            "examples": [
                "BAD: 'Let me know if you need anything else'",
                "BAD: 'Can I provide more details to help?'",
                "BAD: 'Happy to give you whatever you need from me to get that going'",
                "GOOD: 'Thanks! I'll try that'",
                "GOOD: 'Can you help me with X?'"
            ],
            "fix": "Update user_agent prompt or persona to avoid assistant-like phrasing",
            "prevention": "Clarify in user agent prompt: respond naturally as a customer seeking help, not offering help",
            "reference": "See docs/common_issues_by_domain.md"
        })
        
        return recommendations
    
    def _extract_missing_tool_name(self, reason: str, required_action: str) -> str:
        """Extract tool name from success failure reason."""
        if required_action:
            return required_action
        # Try to extract from reason text
        import re
        match = re.search(r'call (\w+)', reason)
        if match:
            return match.group(1)
        return "unknown"
    
    def _diagnose_missing_tool_call(self, tool_name: str) -> str:
        """Diagnose why a required tool call might be missing."""
        task = self.config.get("task", {})
        slots = task.get("slots", {})
        
        # Check if slots has constraints/preferences structure
        constraints = slots.get("constraints", {})
        preferences = slots.get("preferences", {})
        
        if not constraints and not preferences:
            return "Possible causes: (1) Required tool parameters not in slots, (2) User agent didn't provide needed info, (3) Assistant behavior issue"
        
        return f"Check if {tool_name} requires parameters not available in slots constraints: {list(constraints.keys())}"
    
    def _suggest_missing_tool_fix(self, tool_name: str) -> str:
        """Suggest fix for missing tool call."""
        return f"""Investigate:
1. Check tool definition for {tool_name} - what parameters are required?
2. Are ALL required parameters available from: slots, user messages, or previous tool results?
3. If missing data, add to slots or update seed data
4. If assistant had all needed info, this is an agent behavior issue - regenerate with improved prompt
5. If success criteria require impossible action, update criteria to match seed data constraints"""


def format_diagnostic_report(diagnostic: Dict[str, Any]) -> str:
    """Format diagnostic as human-readable report."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"DIAGNOSTIC REPORT: {diagnostic['conversation_id']}")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Overall Success: {diagnostic['overall_success']}")
    lines.append(f"Failure Types: {', '.join(diagnostic['failure_types'])}")
    lines.append(f"Severity: {diagnostic['severity'].upper()}")
    lines.append("")
    
    if not diagnostic['recommendations']:
        lines.append("No issues found!")
        return "\n".join(lines)
    
    lines.append("RECOMMENDATIONS:")
    lines.append("-" * 80)
    
    for i, rec in enumerate(diagnostic['recommendations'], 1):
        lines.append(f"\n{i}. [{rec['type'].upper()}] {rec['issue']}")
        lines.append(f"   Severity: {rec['severity'].upper()}")
        
        if 'affected_turns' in rec:
            lines.append(f"   Affected turns: {rec['affected_turns']}")
        
        if 'reason' in rec:
            lines.append(f"   Reason: {rec['reason']}")
        
        if 'root_cause' in rec:
            lines.append(f"   Root cause: {rec['root_cause']}")
        
        if 'examples' in rec:
            lines.append("   Examples:")
            for ex in rec['examples']:
                lines.append(f"     - {ex}")
        
        if 'investigation_steps' in rec:
            lines.append("   Investigation steps:")
            for step in rec['investigation_steps']:
                lines.append(f"     {step}")
        
        if 'fix' in rec:
            lines.append(f"   Fix: {rec['fix']}")
        
        if 'prevention' in rec:
            lines.append(f"   Prevention: {rec['prevention']}")
        
        if 'reference' in rec:
            lines.append(f"   Reference: {rec['reference']}")
    
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose specific failure and provide actionable recommendations."
    )
    parser.add_argument(
        "--eval-file",
        type=Path,
        help="Path to eval.json file",
    )
    parser.add_argument(
        "--conversation-id",
        help="Conversation ID to diagnose (searches in data/outputs/fail/)",
    )
    parser.add_argument(
        "--batch",
        type=Path,
        help="Diagnose all failures in directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Save diagnostic report to file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    args = parser.parse_args(argv)
    
    if not (args.eval_file or args.conversation_id or args.batch):
        parser.error("Must provide --eval-file, --conversation-id, or --batch")
    
    diagnostics = []
    
    # Single file
    if args.eval_file:
        eval_data = json.loads(args.eval_file.read_text())
        conv_path = Path(eval_data["source_path"])
        if not conv_path.exists():
            conv_path = args.eval_file.parent / (args.eval_file.parent.name + ".json")
        conv_data = json.loads(conv_path.read_text())
        
        diagnoser = FailureDiagnostic(eval_data, conv_data)
        diagnostic = diagnoser.diagnose()
        diagnostics.append(diagnostic)
    
    # Search by conversation ID
    elif args.conversation_id:
        fail_dir = Path("data/outputs/fail")
        found = False
        for subdir in fail_dir.iterdir():
            if not subdir.is_dir():
                continue
            if args.conversation_id in subdir.name:
                eval_file = subdir / "eval.json"
                if eval_file.exists():
                    eval_data = json.loads(eval_file.read_text())
                    conv_path = subdir / (subdir.name + ".json")
                    conv_data = json.loads(conv_path.read_text())
                    
                    diagnoser = FailureDiagnostic(eval_data, conv_data)
                    diagnostic = diagnoser.diagnose()
                    diagnostics.append(diagnostic)
                    found = True
                    break
        
        if not found:
            print(f"No failure found for conversation ID: {args.conversation_id}")
            return 1
    
    # Batch mode
    elif args.batch:
        for subdir in args.batch.iterdir():
            if not subdir.is_dir():
                continue
            eval_file = subdir / "eval.json"
            if not eval_file.exists():
                continue
            conv_file = subdir / (subdir.name + ".json")
            if not conv_file.exists():
                continue
            
            eval_data = json.loads(eval_file.read_text())
            conv_data = json.loads(conv_file.read_text())
            
            diagnoser = FailureDiagnostic(eval_data, conv_data)
            diagnostic = diagnoser.diagnose()
            diagnostics.append(diagnostic)
    
    # Output
    if args.json:
        output_text = json.dumps(diagnostics, indent=2, ensure_ascii=False)
    else:
        reports = [format_diagnostic_report(d) for d in diagnostics]
        output_text = "\n\n".join(reports)
    
    if args.output:
        args.output.write_text(output_text)
        print(f"Diagnostic saved to: {args.output}")
    else:
        print(output_text)
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

