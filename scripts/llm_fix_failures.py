#!/usr/bin/env python3
"""
LLM-Based Failure Fixing Script

Instead of rule-based auto-fix, this script uses an LLM to intelligently
fix issues in failed conversations based on evaluation feedback.

The LLM can fix:
- Syntax errors (malformed blocks)
- Faithfulness issues (hallucinations, unsupported claims)
- Role confusion (assistant-like user phrasing)
- Potentially improve success rate by ensuring required tool calls

Usage:
    python scripts/llm_fix_failures.py --conversation-id os_to_001
    python scripts/llm_fix_failures.py --eval-file path/to/eval.json --model gpt-5.1
    python scripts/llm_fix_failures.py --batch data/outputs/fail/
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core import LLMClient
from eval.syntax import evaluate_conversation, load_conversation_artifact
from eval.success import evaluate_success
from eval.faithfulness import evaluate_faithfulness
from eval.role_confusion import evaluate_role_confusion


FIX_SYNTAX_PROMPT = """You are an expert at fixing conversation formatting issues.

PROBLEM:
The assistant's output has syntax/structure errors that violate the required format.

REQUIRED FORMAT:
Every assistant turn must follow this exact structure:
<think>
[reasoning here - can be empty but block must exist]
</think>
<plan>
[step-by-step plan here]
</plan>
<action type="say">
[message to user]
</action>

OR for tool calls:
<think>
[reasoning]
</think>
<plan>
[plan]
</plan>
<action type="tool" name="tool_name">
{{"param": "value"}}
</action>

CRITICAL RULES:
1. ALL blocks must be properly opened and closed
2. Exactly ONE action block per step, always as the last element
3. No text outside of blocks
4. For multi-step turns: think/plan in first step, subsequent steps have think/plan/action

ERRORS FOUND:
{errors}

ORIGINAL OUTPUT (with errors):
{original_output}

INSTRUCTIONS:
Fix the output to match the required format exactly. Preserve the original intent and content,
just fix the structure. Output ONLY the fixed version, no explanations.

FIXED OUTPUT:"""

FIX_FAITHFULNESS_PROMPT = """You are an expert at fixing hallucinations in AI assistant conversations.

PROBLEM:
The assistant made claims or provided information that is NOT grounded in the actual tool responses
or conversation context. This is a hallucination/faithfulness error.

FAITHFULNESS ISSUES:
{issues}

CONVERSATION CONTEXT:
{context}

TURN TO FIX (turn {turn_id}, step {step_index}):
{problematic_turn}

TOOL RESPONSES AVAILABLE:
{tool_responses}

INSTRUCTIONS:
Rewrite the assistant's output for this turn to:
1. Remove any claims not supported by tool responses
2. Only state facts directly from tool outputs
3. Do NOT infer, assume, or add details not in tool responses
4. Maintain helpful tone while being strictly factual
5. Keep the same format structure (<think>, <plan>, <action>)

Output ONLY the rewritten turn, no explanations.

REWRITTEN TURN:"""

FIX_ROLE_CONFUSION_PROMPT = """You are an expert at fixing role confusion in conversation simulations.

PROBLEM:
The user agent is acting like an assistant instead of a customer. They're using phrasing that
suggests they're helping the assistant or asking questions TO help the assistant.

ROLE CONFUSION ISSUES:
{issues}

USER MESSAGES WITH PROBLEMS:
{problematic_messages}

BAD EXAMPLES (assistant-like phrasing):
- "Let me know if you need anything else"
- "Happy to give you whatever you need from me"
- "Can I provide more details to help you?"
- "Just let me know if there's anything else"

GOOD EXAMPLES (customer-like phrasing):
- "Thanks for your help!"
- "Can you help me with this?"
- "I appreciate it"
- "That would be great"

INSTRUCTIONS:
Rewrite the problematic user messages to sound like a natural customer response, not an assistant.
Maintain the same information content, just change the phrasing.

Output as JSON array of fixed messages:
[
  {{"turn_id": 1, "fixed_output": "..."}},
  {{"turn_id": 2, "fixed_output": "..."}}
]

FIXED MESSAGES:"""

IMPROVE_SUCCESS_PROMPT = """You are an expert at ensuring AI assistants complete their tasks successfully.

PROBLEM:
The assistant did not successfully complete the required task according to success criteria.

SUCCESS CRITERIA:
{success_criteria}

FAILURE REASON:
{failure_reason}

CONVERSATION:
{conversation}

AVAILABLE TOOLS:
{tools}

SEED DATA:
{seed_data}

INSTRUCTIONS:
Identify which assistant turn(s) need to be modified to ensure task success. Specifically:
1. If a required tool call is missing, add it
2. If wrong tool was called, correct it
3. If assistant hallucinated completion, add the actual tool call
4. Maintain conversational flow and natural progression

Output as JSON:
{{
  "turns_to_modify": [
    {{
      "turn_id": 3,
      "step_index": 2,
      "reason": "Missing required tool call",
      "original": "...",
      "fixed": "..."
    }}
  ],
  "explanation": "Brief explanation of changes"
}}

ANALYSIS:"""


def load_conversation_context(conversation_path: Path, eval_data: Dict[str, Any]) -> Dict[str, Any]:
    """Load full conversation context for LLM fixing."""
    conv_data = json.loads(conversation_path.read_text())
    
    # Extract messages
    messages = conv_data.get("messages", [])
    
    # Format conversation for LLM
    formatted_messages = []
    for msg in messages:
        if msg.get("role") == "user":
            formatted_messages.append({
                "turn_id": msg.get("turn_id"),
                "role": "user",
                "content": msg.get("output_raw", "")
            })
        elif msg.get("role") == "assistant":
            steps = msg.get("steps", [])
            for step in steps:
                formatted_messages.append({
                    "turn_id": msg.get("turn_id"),
                    "step_index": step.get("step_index"),
                    "role": "assistant",
                    "content": step.get("output_raw", ""),
                    "action": step.get("action_structured")
                })
    
    # Get tool responses
    tool_responses = []
    for msg in messages:
        if msg.get("role") == "assistant":
            for step in msg.get("steps", []):
                obs = step.get("observation")
                if obs:
                    tool_responses.append({
                        "turn_id": msg.get("turn_id"),
                        "step_index": step.get("step_index"),
                        "tool": step.get("action_structured", {}).get("name"),
                        "result": obs.get("parsed", obs.get("raw"))
                    })
    
    return {
        "config": conv_data.get("config", {}),
        "messages": formatted_messages,
        "tool_responses": tool_responses,
        "eval_data": eval_data
    }


def fix_syntax_with_llm(
    conversation_path: Path,
    eval_data: Dict[str, Any],
    model: str = "gpt-5.1",
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """Use LLM to fix syntax errors in conversation."""
    conv_data = json.loads(conversation_path.read_text())
    messages = conv_data.get("messages", [])
    
    syntax_errors = eval_data.get("syntax", {})
    error_turns = {et["turn_id"]: et for et in syntax_errors.get("error_turns", [])}
    
    if not error_turns:
        return {"fixed": False, "reason": "No syntax errors to fix"}
    
    client = LLMClient(model=model, api_key=api_key)
    fixes_applied = []
    
    for message in messages:
        if message.get("role") != "assistant":
            continue
        
        turn_id = message.get("turn_id")
        if turn_id not in error_turns:
            continue
        
        error_info = error_turns[turn_id]
        steps = message.get("steps", [])
        error_steps = {s["index"]: s for s in error_info.get("steps", [])}
        
        for step in steps:
            step_index = step.get("step_index")
            if step_index not in error_steps:
                continue
            
            original_output = step.get("output_raw", "")
            error_details = error_steps[step_index]
            
            # Build error description
            errors_desc = []
            for err_type in error_details.get("structure_errors", []):
                errors_desc.append(f"- {err_type}")
            errors_text = "\n".join(errors_desc)
            
            # Ask LLM to fix
            prompt = FIX_SYNTAX_PROMPT.format(
                errors=errors_text,
                original_output=original_output
            )
            
            fixed_output = client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are an expert at fixing conversation format issues. Output only the fixed version, no explanations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            ).strip()
            
            # Remove markdown code fences if present
            if fixed_output.startswith("```"):
                lines = fixed_output.split("\n")
                fixed_output = "\n".join(lines[1:-1]) if len(lines) > 2 else fixed_output
            
            # Apply fix
            step["output_raw"] = fixed_output
            fixes_applied.append({
                "turn_id": turn_id,
                "step_index": step_index,
                "original_length": len(original_output),
                "fixed_length": len(fixed_output)
            })
    
    return {
        "fixed": True,
        "fixes_applied": fixes_applied,
        "modified_conversation": conv_data
    }


def fix_faithfulness_with_llm(
    conversation_path: Path,
    eval_data: Dict[str, Any],
    model: str = "gpt-5.1",
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """Use LLM to fix faithfulness errors (hallucinations)."""
    context = load_conversation_context(conversation_path, eval_data)
    conv_data = json.loads(conversation_path.read_text())
    messages = conv_data.get("messages", [])
    
    faithfulness = eval_data.get("faithfulness", {})
    error_turns = faithfulness.get("error_turns", [])
    
    if not error_turns:
        return {"fixed": False, "reason": "No faithfulness errors to fix"}
    
    client = LLMClient(model=model, api_key=api_key)
    fixes_applied = []
    
    for error in error_turns:
        turn_id = error.get("turn_id")
        step_index = error.get("step_index")
        issues = error.get("issues", [])
        
        # Find the problematic turn
        problematic_turn = None
        for msg in context["messages"]:
            if msg.get("turn_id") == turn_id and msg.get("step_index") == step_index:
                problematic_turn = msg
                break
        
        if not problematic_turn:
            continue
        
        # Get relevant tool responses up to this point
        relevant_tools = [
            tr for tr in context["tool_responses"]
            if tr["turn_id"] <= turn_id
        ]
        
        # Build context
        issues_desc = "\n".join([
            f"- {issue.get('type')}: {issue.get('reason')}"
            for issue in issues
        ])
        
        prompt = FIX_FAITHFULNESS_PROMPT.format(
            issues=issues_desc,
            context=json.dumps(context["messages"][:10], indent=2),
            turn_id=turn_id,
            step_index=step_index,
            problematic_turn=json.dumps(problematic_turn, indent=2),
            tool_responses=json.dumps(relevant_tools, indent=2)
        )
        
        fixed_output = client.chat_completion(
            messages=[
                {"role": "system", "content": "You are an expert at fixing hallucinations in AI conversations. Output only the fixed turn content."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        ).strip()
        
        # Remove markdown if present
        if fixed_output.startswith("```"):
            lines = fixed_output.split("\n")
            fixed_output = "\n".join(lines[1:-1]) if len(lines) > 2 else fixed_output
        
        # Apply fix to conversation
        for message in messages:
            if message.get("role") == "assistant" and message.get("turn_id") == turn_id:
                steps = message.get("steps", [])
                for step in steps:
                    if step.get("step_index") == step_index:
                        step["output_raw"] = fixed_output
                        fixes_applied.append({
                            "turn_id": turn_id,
                            "step_index": step_index,
                            "issue_types": [i.get("type") for i in issues]
                        })
                        break
    
    return {
        "fixed": True,
        "fixes_applied": fixes_applied,
        "modified_conversation": conv_data
    }


def fix_role_confusion_with_llm(
    conversation_path: Path,
    eval_data: Dict[str, Any],
    model: str = "gpt-5.1",
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """Use LLM to fix role confusion in user messages."""
    conv_data = json.loads(conversation_path.read_text())
    messages = conv_data.get("messages", [])
    
    role_confusion = eval_data.get("role_confusion", {})
    if not role_confusion.get("has_confusion"):
        return {"fixed": False, "reason": "No role confusion to fix"}
    
    confused_turns = role_confusion.get("confused_turns", [])
    if not confused_turns:
        return {"fixed": False, "reason": "No confused turns identified"}
    
    # Get problematic user messages
    problematic_messages = []
    for msg in messages:
        if msg.get("role") == "user" and msg.get("turn_id") in confused_turns:
            problematic_messages.append({
                "turn_id": msg.get("turn_id"),
                "content": msg.get("output_raw", "")
            })
    
    if not problematic_messages:
        return {"fixed": False, "reason": "No messages found for confused turns"}
    
    client = LLMClient(model=model, api_key=api_key)
    
    prompt = FIX_ROLE_CONFUSION_PROMPT.format(
        issues=role_confusion.get("reason", ""),
        problematic_messages=json.dumps(problematic_messages, indent=2)
    )
    
    response = client.chat_completion(
        messages=[
            {"role": "system", "content": "You are an expert at fixing role confusion in conversations. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    ).strip()
    
    # Parse JSON response
    if response.startswith("```json"):
        response = response.split("```json")[1].split("```")[0].strip()
    elif response.startswith("```"):
        response = response.split("```")[1].split("```")[0].strip()
    
    try:
        fixes = json.loads(response)
    except json.JSONDecodeError:
        return {"fixed": False, "reason": "Failed to parse LLM response", "response": response}
    
    # Apply fixes
    fixes_applied = []
    for fix in fixes:
        turn_id = fix.get("turn_id")
        fixed_output = fix.get("fixed_output")
        
        for message in messages:
            if message.get("role") == "user" and message.get("turn_id") == turn_id:
                message["output_raw"] = fixed_output
                fixes_applied.append({"turn_id": turn_id})
                break
    
    return {
        "fixed": True,
        "fixes_applied": fixes_applied,
        "modified_conversation": conv_data
    }


def improve_success_with_llm(
    conversation_path: Path,
    eval_data: Dict[str, Any],
    model: str = "gpt-5.1",
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """Use LLM to suggest improvements for success criteria."""
    context = load_conversation_context(conversation_path, eval_data)
    
    success = eval_data.get("success", {})
    if success.get("success"):
        return {"fixed": False, "reason": "Already successful"}
    
    client = LLMClient(model=model, api_key=api_key)
    
    config = context["config"]
    task = config.get("task", {})
    
    prompt = IMPROVE_SUCCESS_PROMPT.format(
        success_criteria=json.dumps(task.get("success_criteria", {}), indent=2),
        failure_reason=success.get("reason", ""),
        conversation=json.dumps(context["messages"], indent=2),
        tools=json.dumps(config.get("tools", {}), indent=2)[:1000],
        seed_data=json.dumps(config.get("tool_agent_config", {}).get("context", {}).get("seed", {}), indent=2)[:1000]
    )
    
    response = client.chat_completion(
        messages=[
            {"role": "system", "content": "You are an expert at analyzing conversation success. Output valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    ).strip()
    
    # Parse response
    if response.startswith("```json"):
        response = response.split("```json")[1].split("```")[0].strip()
    elif response.startswith("```"):
        response = response.split("```")[1].split("```")[0].strip()
    
    try:
        analysis = json.loads(response)
    except json.JSONDecodeError:
        return {"fixed": False, "reason": "Failed to parse LLM analysis", "response": response}
    
    return {
        "fixed": False,  # Don't auto-apply success fixes, too risky
        "analysis": analysis,
        "reason": "Success improvements suggested but not applied (requires manual review)"
    }


def apply_llm_fixes(
    conversation_path: Path,
    eval_data: Dict[str, Any],
    fix_types: List[str],
    model: str = "gpt-5.1",
    api_key: Optional[str] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """Apply LLM-based fixes to a failed conversation."""
    results = {
        "conversation_id": eval_data.get("conversation_id"),
        "original_path": str(conversation_path),
        "fixes_attempted": [],
        "fixes_successful": [],
        "new_conversation": None
    }
    
    # Start with original conversation
    current_conv_data = json.loads(conversation_path.read_text())
    
    # Apply fixes in order
    if "syntax" in fix_types:
        print(f"  Fixing syntax errors with LLM...")
        result = fix_syntax_with_llm(conversation_path, eval_data, model, api_key)
        results["fixes_attempted"].append("syntax")
        if result.get("fixed"):
            current_conv_data = result["modified_conversation"]
            results["fixes_successful"].append("syntax")
            print(f"    ✓ Fixed {len(result.get('fixes_applied', []))} syntax errors")
    
    if "faithfulness" in fix_types:
        print(f"  Fixing faithfulness errors with LLM...")
        # Update conversation path temporarily for faithfulness fix
        temp_path = conversation_path.with_suffix(".tmp.json")
        temp_path.write_text(json.dumps(current_conv_data, indent=2, ensure_ascii=False))
        
        result = fix_faithfulness_with_llm(temp_path, eval_data, model, api_key)
        results["fixes_attempted"].append("faithfulness")
        if result.get("fixed"):
            current_conv_data = result["modified_conversation"]
            results["fixes_successful"].append("faithfulness")
            print(f"    ✓ Fixed {len(result.get('fixes_applied', []))} faithfulness errors")
        
        temp_path.unlink()
    
    if "role_confusion" in fix_types:
        print(f"  Fixing role confusion with LLM...")
        temp_path = conversation_path.with_suffix(".tmp.json")
        temp_path.write_text(json.dumps(current_conv_data, indent=2, ensure_ascii=False))
        
        result = fix_role_confusion_with_llm(temp_path, eval_data, model, api_key)
        results["fixes_attempted"].append("role_confusion")
        if result.get("fixed"):
            current_conv_data = result["modified_conversation"]
            results["fixes_successful"].append("role_confusion")
            print(f"    ✓ Fixed {len(result.get('fixes_applied', []))} role confusion errors")
        
        temp_path.unlink()
    
    if "success" in fix_types:
        print(f"  Analyzing success improvements with LLM...")
        temp_path = conversation_path.with_suffix(".tmp.json")
        temp_path.write_text(json.dumps(current_conv_data, indent=2, ensure_ascii=False))
        
        result = improve_success_with_llm(temp_path, eval_data, model, api_key)
        results["fixes_attempted"].append("success")
        if result.get("analysis"):
            results["success_analysis"] = result["analysis"]
            print(f"    ℹ Success improvement suggestions generated (review required)")
        
        temp_path.unlink()
    
    results["new_conversation"] = current_conv_data
    
    # Save if not dry run
    if not dry_run and results["fixes_successful"]:
        # Backup original
        backup_path = conversation_path.with_suffix(".json.backup")
        shutil.copy2(conversation_path, backup_path)
        
        # Write fixed version
        conversation_path.write_text(json.dumps(current_conv_data, indent=2, ensure_ascii=False))
        results["backup_path"] = str(backup_path)
        results["saved"] = True
    else:
        results["saved"] = False
    
    return results


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Use LLM to intelligently fix failed conversations."
    )
    parser.add_argument(
        "--conversation-id",
        help="Conversation ID to fix (searches in data/outputs/fail/)",
    )
    parser.add_argument(
        "--eval-file",
        type=Path,
        help="Path to eval.json file",
    )
    parser.add_argument(
        "--batch",
        type=Path,
        help="Fix all failures in directory",
    )
    parser.add_argument(
        "--fix-types",
        nargs="+",
        default=["syntax", "faithfulness", "role_confusion"],
        choices=["syntax", "faithfulness", "role_confusion", "success"],
        help="Types of failures to fix (default: syntax, faithfulness, role_confusion)",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.1",
        help="OpenAI model to use for fixing (default: gpt-5.1)",
    )
    parser.add_argument(
        "--api-key",
        help="OpenAI API key",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't save fixes, just show what would be fixed",
    )
    parser.add_argument(
        "--reeval",
        action="store_true",
        help="Re-evaluate after fixing",
    )
    args = parser.parse_args(argv)
    
    if not (args.conversation_id or args.eval_file or args.batch):
        parser.error("Must provide --conversation-id, --eval-file, or --batch")
    
    # Collect conversations to fix
    to_fix = []
    
    if args.eval_file:
        to_fix.append(args.eval_file)
    elif args.conversation_id:
        fail_dir = Path("data/outputs/fail")
        for subdir in fail_dir.iterdir():
            if args.conversation_id in subdir.name:
                eval_file = subdir / "eval.json"
                if eval_file.exists():
                    to_fix.append(eval_file)
                    break
    elif args.batch:
        for subdir in args.batch.iterdir():
            if subdir.is_dir():
                eval_file = subdir / "eval.json"
                if eval_file.exists():
                    to_fix.append(eval_file)
    
    if not to_fix:
        print("No conversations found to fix")
        return 1
    
    print(f"Found {len(to_fix)} conversation(s) to fix")
    print(f"Fix types: {', '.join(args.fix_types)}")
    print(f"Model: {args.model}")
    print(f"Dry run: {args.dry_run}")
    print()
    
    results = []
    
    for eval_path in to_fix:
        eval_data = json.loads(eval_path.read_text())
        conv_path = Path(eval_data["source_path"])
        if not conv_path.exists():
            conv_path = eval_path.parent / (eval_path.parent.name + ".json")
        
        print(f"Processing: {eval_data.get('conversation_id')}")
        
        result = apply_llm_fixes(
            conv_path,
            eval_data,
            args.fix_types,
            args.model,
            args.api_key,
            args.dry_run
        )
        results.append(result)
        
        print(f"  Attempted: {', '.join(result['fixes_attempted'])}")
        print(f"  Successful: {', '.join(result['fixes_successful']) if result['fixes_successful'] else 'None'}")
        
        if args.reeval and result["fixes_successful"] and not args.dry_run:
            print(f"  Re-evaluating...")
            from eval.run import main as eval_main
            # Save to temp and evaluate
            # (simplified - full implementation would call eval properly)
            print(f"    (Re-evaluation skipped in this version - use eval.run manually)")
        
        print()
    
    # Summary
    print("=" * 80)
    print(f"SUMMARY")
    print("=" * 80)
    print(f"Total conversations processed: {len(results)}")
    print(f"Successfully fixed: {sum(1 for r in results if r['fixes_successful'])}")
    
    successful_by_type = {}
    for fix_type in ["syntax", "faithfulness", "role_confusion", "success"]:
        count = sum(1 for r in results if fix_type in r['fixes_successful'])
        if count > 0:
            successful_by_type[fix_type] = count
    
    if successful_by_type:
        print("\nFixes by type:")
        for fix_type, count in successful_by_type.items():
            print(f"  {fix_type}: {count}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

