# Failure Analysis & Auto-Fix Tools

This directory contains tools for analyzing and fixing failed conversation evaluations.

## Overview

The evaluation system checks conversations for four types of failures:
1. **Syntax** - Malformed output blocks, missing required structure
2. **Success** - Task not completed (missing required tool calls, wrong actions)
3. **Faithfulness** - Hallucinations, unsupported claims not grounded in tool results
4. **Role Confusion** - User agent acting like an assistant instead of a customer

## Tools

### 1. `analyze_and_fix_failures.py` - Automated Analysis & Fixing

Scans all failed evaluations, categorizes failures, attempts automatic fixes (primarily syntax), and reruns evaluations.

**Usage:**

```bash
# Analyze all failures (dry run)
python scripts/analyze_and_fix_failures.py

# Analyze and attempt to fix syntax errors
python scripts/analyze_and_fix_failures.py --fix-syntax

# Fix syntax and re-evaluate
python scripts/analyze_and_fix_failures.py --fix-syntax --reeval --api-key $OPENAI_API_KEY

# Save reports
python scripts/analyze_and_fix_failures.py --output report.txt --json-output analysis.json

# Custom fail directory
python scripts/analyze_and_fix_failures.py --fail-dir data/outputs/custom_fail/
```

**What it does:**
- Scans `data/outputs/fail/` for all `eval.json` files
- Categorizes failures by type and combination
- Identifies common patterns (syntax errors, faithfulness issues, etc.)
- Attempts to auto-fix syntax errors (malformed blocks)
- Re-evaluates fixed conversations
- Generates summary report with statistics and samples

**Auto-fixable issues:**
- `structure_invalid_block_format` - Unclosed `<think>`, `<plan>` blocks
- Malformed XML-like block syntax
- Extra whitespace between blocks

**Not auto-fixable (require regeneration):**
- Missing required tool calls (success failures)
- Hallucinations (faithfulness failures)
- Role confusion (user agent prompt issues)
- Missing blocks entirely

**Output:**
```
FAILURE ANALYSIS REPORT
================================================================================

Total Failed Conversations: 20

Failures by Type:
  syntax              :    5 ( 25.0%)
  success             :   12 ( 60.0%)
  faithfulness        :    8 ( 40.0%)
  role_confusion      :    3 ( 15.0%)

Top Failure Combinations:
  success+faithfulness                    :    6 ( 30.0%)
  syntax+role_confusion                   :    2 ( 10.0%)
  success                                 :    4 ( 20.0%)

Fix Summary:
  Fixable: 5
  Fix Attempted: 5
  Fix Successful: 3
  Success Rate: 60.0%
```

---

### 2. `diagnose_failures.py` - Detailed Diagnostics & Recommendations

Provides detailed diagnostics for specific failures with actionable recommendations based on the investigation guides in `docs/`.

**Usage:**

```bash
# Diagnose specific conversation by ID
python scripts/diagnose_failures.py --conversation-id os_to_001

# Diagnose specific eval file
python scripts/diagnose_failures.py --eval-file data/outputs/fail/.../eval.json

# Batch diagnose all failures
python scripts/diagnose_failures.py --batch data/outputs/fail/ --output diagnostics.txt

# JSON output
python scripts/diagnose_failures.py --conversation-id os_ro_003 --json
```

**What it does:**
- Analyzes specific failure in detail
- Identifies root causes based on investigation framework
- Provides actionable fix recommendations
- Suggests prevention strategies
- References relevant documentation

**Example Output:**

```
================================================================================
DIAGNOSTIC REPORT: online_shopping.os_to_001
================================================================================

Overall Success: False
Failure Types: syntax, role_confusion
Severity: HIGH

RECOMMENDATIONS:
--------------------------------------------------------------------------------

1. [SYNTAX] Invalid block format in 2 turn(s)
   Severity: HIGH
   Affected turns: [3, 5]
   Root cause: Assistant output has malformed XML-like blocks (<think>, <plan>, <action>)
   Fix: Run: python scripts/analyze_and_fix_failures.py --fix-syntax --reeval
   Prevention: Check system agent prompt to ensure it emphasizes proper block formatting.

2. [ROLE_CONFUSION] User agent confused its role and acted like an assistant
   Severity: MEDIUM
   Affected turns: [4]
   Reason: User offered to help assistant complete a task
   Root cause: User agent phrasing suggests offering help TO the assistant
   Examples:
     BAD: 'Happy to give you whatever you need from me to get that going'
     GOOD: 'Thanks! I'll try that'
   Fix: Update user_agent prompt or persona to avoid assistant-like phrasing
   Prevention: Clarify in user agent prompt: respond naturally as a customer
```

---

## Workflow

### Quick Start: Analyze All Failures

```bash
# 1. Analyze all failures and generate report
python scripts/analyze_and_fix_failures.py --output failure_report.txt

# 2. Attempt fixes and re-evaluate
python scripts/analyze_and_fix_failures.py --fix-syntax --reeval --api-key $OPENAI_API_KEY

# 3. Get detailed diagnostics for high-priority failures
python scripts/diagnose_failures.py --batch data/outputs/fail/ --output detailed_diagnostics.txt
```

### Investigating Specific Failures

```bash
# 1. Find a specific failure in the report
cat failure_report.txt | grep "os_ro_003"

# 2. Get detailed diagnostic
python scripts/diagnose_failures.py --conversation-id os_ro_003

# 3. Review the actual conversation
cat data/outputs/fail/20251124_145817__os_ro_003__persona_031/20251124_145817__os_ro_003__persona_031.json | jq .

# 4. Check the scenario configuration
cat data/domains/online_shopping/return_order/os_ro_003__persona_031.json | jq .
```

### Fixing Configuration Issues

Based on diagnostic recommendations:

1. **Success Failures (Missing Tool Calls)**
   - Check: `docs/failure_investigation_guide.md` (Steps 3-7)
   - Verify: seed data contains entities user agent references
   - Fix: Update seed data OR user agent references to align
   - Example: User says "card ending 4418" but seed has "card ending 2468"

2. **Faithfulness Failures (Hallucinations)**
   - Check: `docs/common_issues_by_domain.md` - faithfulness section
   - Root cause: Assistant claimed actions without executing them
   - Fix: Improve system prompt to prevent reasoning/action mismatch
   - Prevention: Add explicit instruction about grounding in tool responses

3. **Role Confusion**
   - Check: User agent prompt and persona
   - Fix: Remove assistant-like phrasing ("let me know if you need anything")
   - Update: Use natural customer language ("thanks!", "can you help?")

4. **Syntax Failures**
   - Try: Auto-fix with `--fix-syntax`
   - If not fixable: Regenerate with improved system prompt
   - Prevention: Add explicit block formatting requirements to prompt

---

## Understanding Failure Types

### Syntax Failures

**What they are:** Structural issues in assistant output format

**Common errors:**
- `structure_invalid_block_format` - Malformed XML blocks
- `structure_missing_block` - Missing `<think>`, `<plan>`, or `<action>`
- `structure_unexpected_text` - Text outside of blocks
- `turn_structure_invalid_say` - Say action not last or missing

**Investigation:**
```bash
# Check which turns have errors
python scripts/diagnose_failures.py --conversation-id CONVERSATION_ID | grep "Affected turns"

# View the actual output
cat CONVERSATION.json | jq '.messages[] | select(.turn_id == TURN_ID) | .steps[].output_raw'
```

### Success Failures

**What they are:** Task not completed according to success criteria

**Common causes:**
- Missing required tool call
- Configuration mismatch (user references ≠ seed data)
- Assistant hallucinated completion
- Impossible success criteria

**Investigation:**
```bash
# Get detailed diagnostic
python scripts/diagnose_failures.py --conversation-id CONVERSATION_ID

# Compare success criteria with what actually happened
cat CONVERSATION.json | jq '.config.task.success_criteria'
cat CONVERSATION.json | jq '.messages[] | select(.role == "assistant") | .steps[] | select(.action_structured.type == "tool_call") | .action_structured.name'
```

### Faithfulness Failures

**What they are:** Assistant statements not grounded in tool results (hallucinations)

**Types:**
- `slot_value_faithfulness` - Tool parameters incompatible with user intent
- `tool_summary_faithfulness` - Say statements not grounded in tool results

**Investigation:**
```bash
# Check which turns had issues
python scripts/diagnose_failures.py --conversation-id CONVERSATION_ID --json | jq '.[] | .recommendations[] | select(.type == "faithfulness")'

# Compare tool results with assistant say actions
cat CONVERSATION.json | jq '.messages[] | select(.turn_id == TURN_ID) | .steps[]'
```

### Role Confusion

**What it is:** User agent acting like an assistant instead of a customer

**Red flags:**
- "Let me know if you need anything"
- "Can I provide more details to help?"
- "Happy to give you whatever you need"

**Investigation:**
```bash
# Check confused turns
python scripts/diagnose_failures.py --conversation-id CONVERSATION_ID | grep "Affected turns"

# View user messages
cat CONVERSATION.json | jq '.messages[] | select(.role == "user") | {turn_id, output_raw}'
```

---

## Common Patterns & Fixes

### Pattern 1: Structure Invalid Block Format

**Symptom:** `structure_invalid_block_format` in multiple turns

**Fix:**
```bash
python scripts/analyze_and_fix_failures.py --fix-syntax --reeval --api-key $KEY
```

**Prevention:** Update system agent prompt:
```
CRITICAL: Your output MUST follow this exact structure:
<think>
[your reasoning]
</think>
<plan>
[your step-by-step plan]
</plan>
<action type="say">
[your message to user]
</action>

ENSURE all blocks are properly closed with matching end tags.
```

### Pattern 2: Missing Required Tool Call

**Symptom:** Success judge says "did not call `tool_name`"

**Investigation:**
1. Check tool definition: required parameters?
2. Are parameters available in slots, seed data, or user messages?
3. Did user provide all needed information?

**Fix:**
- If data missing: Add to `task.slots.constraints` or `tool_agent.context.seed`
- If user didn't provide: Update `user_agent.injected_behaviors` to provide info
- If config mismatch: Align seed data with user agent references

### Pattern 3: Assistant Hallucinating Tool Results

**Symptom:** Faithfulness errors like "Assistant claims to have looked up orders despite no tool calls"

**Fix:** Requires regeneration with improved prompt:
```
CRITICAL: Only relay information from actual tool responses.
- Do NOT describe tool calls you haven't executed
- Do NOT assume or infer data not in tool results
- If your reasoning mentions tool results, you MUST execute that tool call in the action block
```

### Pattern 4: Configuration Mismatch

**Symptom:** Success failure + user references don't match seed data

**Example:**
- User: "my card ending 4418"
- Seed data: only has card ending 2468

**Fix:**
```bash
# Update scenario configuration
vim data/domains/DOMAIN/USE_CASE/SCENARIO__PERSONA.json

# Option 1: Update seed data to match user reference
# Change card ending from 2468 to 4418 in tool_agent.context.seed

# Option 2: Update user agent to reference what exists
# Change injected_behaviors to mention "card ending 2468"
```

---

## Tips & Best Practices

1. **Start broad, then narrow:**
   - Run `analyze_and_fix_failures.py` first for overview
   - Use `diagnose_failures.py` for specific high-priority issues

2. **Fix syntax first:**
   - Syntax errors can cascade to other failures
   - Auto-fixable with `--fix-syntax`

3. **Configuration mismatches are common:**
   - Always verify user references match seed data
   - Check docs/failure_investigation_guide.md Step 4

4. **Not everything is auto-fixable:**
   - Success/faithfulness/role issues usually require regeneration
   - Use diagnostics to understand WHY, then fix configuration and regenerate

5. **Prevention over fixing:**
   - Update prompts based on diagnostic prevention suggestions
   - Improve configuration validation before generation

---

## References

- **Investigation Guide:** `docs/failure_investigation_guide.md`
- **Common Issues by Domain:** `docs/common_issues_by_domain.md`
- **Schema Guide:** `docs/scenario_schema_guide.md`
- **Evaluation Code:** `src/eval/`

---

## Example Session

```bash
# 1. Analyze all failures
python scripts/analyze_and_fix_failures.py --output report.txt
# Output: "Found 20 failures: 5 syntax, 12 success, 8 faithfulness, 3 role confusion"

# 2. Fix syntax errors automatically
python scripts/analyze_and_fix_failures.py --fix-syntax --reeval --api-key $OPENAI_API_KEY
# Output: "Fixed 3 out of 5 syntax errors"

# 3. Investigate remaining failures
python scripts/diagnose_failures.py --batch data/outputs/fail/ | grep -A 5 "CRITICAL"
# Shows: "Missing required tool call: create_return"

# 4. Deep dive on specific failure
python scripts/diagnose_failures.py --conversation-id os_ro_003
# Shows: Configuration mismatch - user references order date that doesn't exist in seed

# 5. Fix configuration
vim data/domains/online_shopping/return_order/os_ro_003__persona_031.json
# Update seed data to include the order date user mentions

# 6. Regenerate conversation
python src/runner.py --scenario data/domains/online_shopping/return_order/os_ro_003__persona_031.json

# 7. Verify fix
python -m eval.run data/outputs/TIMESTAMP__os_ro_003__persona_031/
# Output: "SUCCESS: true"
```

