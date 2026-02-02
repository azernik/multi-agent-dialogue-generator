# LLM-Based Failure Fixing Guide

## Overview

Instead of using rule-based string manipulation to fix failures, **`llm_fix_failures.py`** uses an LLM (like GPT-4.5/5.1) to intelligently understand and fix issues in failed conversations.

## Why LLM-Based Fixing?

### Rule-Based (Old Approach) ❌
```python
# Simple regex/string manipulation
if "<think>" in text and "</think>" not in text:
    text = text.replace("<plan>", "</think>\n<plan>")
```

**Limitations:**
- Only fixes simple syntax errors
- Can't understand context
- May break content
- Limited to pattern matching

### LLM-Based (New Approach) ✅
```python
# LLM understands the problem and fixes intelligently
prompt = f"""
The assistant's output has these errors: {errors}
Original output: {original}
Fix it while preserving intent.
"""
fixed = llm.complete(prompt)
```

**Advantages:**
- ✅ Understands context and intent
- ✅ Can fix complex issues (hallucinations, role confusion)
- ✅ Maintains conversation flow
- ✅ Preserves meaning while fixing structure
- ✅ Can handle multiple error types simultaneously

---

## What Can LLM Fix?

### 1. Syntax Errors (Structure) ✅

**Problem:** Malformed XML blocks, missing closing tags

**LLM Approach:**
- Understands required format (`<think>`, `<plan>`, `<action>`)
- Fixes structure while preserving content
- Ensures proper nesting and closure

**Example:**
```
Input (broken):
<think>
reasoning here
<plan>  ← Missing </think>!
steps here
</plan>
<action type="say">
message
</action>

LLM fixes to:
<think>
reasoning here
</think>
<plan>
steps here
</plan>
<action type="say">
message
</action>
```

---

### 2. Faithfulness Errors (Hallucinations) ✅✅

**Problem:** Assistant makes claims not supported by tool responses

**LLM Approach:**
- Reviews tool responses available
- Identifies unsupported claims
- Rewrites to only use grounded information
- Maintains helpful tone

**Example:**
```
Tool response: {"status": "delivered", "tracking": "123"}

Bad (hallucination):
"Your package was delivered at 2pm yesterday to your front door."
                        ↑ Time and location not in tool response!

LLM fixes to:
"Your package has been delivered. Tracking number: 123"
                        ↑ Only states what's in tool response
```

---

### 3. Role Confusion ✅✅

**Problem:** User agent sounds like an assistant

**LLM Approach:**
- Recognizes assistant-like phrasing
- Rewrites in customer voice
- Preserves information content

**Example:**
```
Bad (user acting like assistant):
"Happy to give you whatever you need from me to get that going"

LLM fixes to:
"Sure, I can provide that information"
```

---

### 4. Success Improvements 🔍

**Problem:** Required tool call missing or wrong tool used

**LLM Approach:**
- Analyzes success criteria
- Identifies what's missing
- **Suggests** improvements (doesn't auto-apply for safety)
- Provides reasoning

**Example:**
```
Success requires: create_return tool call
Current: Only called get_order_details

LLM suggests:
{
  "turn_to_modify": 5,
  "missing_action": "create_return",
  "reason": "User confirmed return, should execute create_return",
  "suggested_fix": "Add tool call after user confirms"
}
```

---

## Usage

### Quick Start

```bash
# Fix specific conversation with LLM
python3 scripts/llm_fix_failures.py --conversation-id os_to_001 --api-key $OPENAI_API_KEY

# Fix syntax and faithfulness only
python3 scripts/llm_fix_failures.py \
    --conversation-id os_to_001 \
    --fix-types syntax faithfulness \
    --api-key $KEY

# Batch fix all failures
python3 scripts/llm_fix_failures.py \
    --batch data/outputs/fail/ \
    --api-key $KEY

# Dry run (see what would be fixed without saving)
python3 scripts/llm_fix_failures.py \
    --conversation-id os_to_001 \
    --dry-run \
    --api-key $KEY
```

### Fix Types

You can choose which types to fix with `--fix-types`:

```bash
# Fix only syntax
--fix-types syntax

# Fix syntax and faithfulness
--fix-types syntax faithfulness

# Fix everything (default)
--fix-types syntax faithfulness role_confusion

# Include success analysis (suggestions only, not auto-applied)
--fix-types syntax faithfulness role_confusion success
```

---

## How It Works

### 1. Syntax Fixing

```python
# LLM receives:
PROBLEM: structure_invalid_block_format in turn 3

REQUIRED FORMAT:
<think>...</think>
<plan>...</plan>
<action type="say">...</action>

ORIGINAL OUTPUT (with errors):
[broken output here]

# LLM responds with:
[fixed output with proper structure]
```

### 2. Faithfulness Fixing

```python
# LLM receives:
PROBLEM: Assistant claimed to have looked up orders but no tool call occurred

CONVERSATION CONTEXT:
[previous messages]

TOOL RESPONSES AVAILABLE:
[list of actual tool calls and results]

TURN TO FIX:
[the problematic turn]

# LLM responds with:
[rewritten turn that only uses grounded information]
```

### 3. Role Confusion Fixing

```python
# LLM receives:
PROBLEM: User acting like assistant in turns [4, 6]

BAD EXAMPLES:
- "Let me know if you need anything"
- "Happy to help you with that"

GOOD EXAMPLES:
- "Thanks for your help!"
- "Can you help me?"

USER MESSAGES TO FIX:
[problematic messages]

# LLM responds with:
[{"turn_id": 4, "fixed_output": "..."}]
```

---

## Example Session

```bash
$ python3 scripts/llm_fix_failures.py --conversation-id os_to_001 --api-key $KEY

Found 1 conversation(s) to fix
Fix types: syntax, faithfulness, role_confusion
Model: gpt-5.1
Dry run: False

Processing: online_shopping.os_to_001
  Fixing syntax errors with LLM...
    ✓ Fixed 2 syntax errors
  Fixing faithfulness errors with LLM...
    ✓ Fixed 0 faithfulness errors (none found)
  Fixing role confusion with LLM...
    ✓ Fixed 1 role confusion error
  Attempted: syntax, faithfulness, role_confusion
  Successful: syntax, role_confusion

================================================================================
SUMMARY
================================================================================
Total conversations processed: 1
Successfully fixed: 1

Fixes by type:
  syntax: 1
  role_confusion: 1
```

---

## Comparison: Rule-Based vs LLM-Based

| Feature | Rule-Based | LLM-Based |
|---------|------------|-----------|
| **Syntax errors** | ✅ Simple cases | ✅✅ All cases |
| **Faithfulness** | ❌ Cannot fix | ✅✅ Rewrites grounded content |
| **Role confusion** | ❌ Cannot fix | ✅✅ Rephrases naturally |
| **Success improvements** | ❌ Cannot analyze | ✅ Provides suggestions |
| **Context awareness** | ❌ No understanding | ✅✅ Full understanding |
| **Preserves meaning** | ⚠️ May break content | ✅✅ Maintains intent |
| **Speed** | ⚡ Very fast | 🐌 Slower (API calls) |
| **Cost** | 💰 Free | 💰💰 API costs |
| **Reliability** | ✅ Deterministic | ⚠️ Model-dependent |

---

## Best Practices

### 1. Start with Dry Run

```bash
# See what would be fixed before applying
python3 scripts/llm_fix_failures.py --conversation-id os_to_001 --dry-run --api-key $KEY
```

### 2. Fix Types Incrementally

```bash
# First, just fix syntax
python3 scripts/llm_fix_failures.py --conversation-id os_to_001 --fix-types syntax --api-key $KEY

# Then add faithfulness if needed
python3 scripts/llm_fix_failures.py --conversation-id os_to_001 --fix-types syntax faithfulness --api-key $KEY
```

### 3. Review Success Suggestions

```bash
# Get success improvement suggestions (not auto-applied)
python3 scripts/llm_fix_failures.py \
    --conversation-id os_to_001 \
    --fix-types success \
    --api-key $KEY

# Review the analysis, then manually decide whether to apply
```

### 4. Batch Process Carefully

```bash
# Batch fix is powerful but uses API credits
# Start with dry run
python3 scripts/llm_fix_failures.py --batch data/outputs/fail/ --dry-run --api-key $KEY

# Then apply
python3 scripts/llm_fix_failures.py --batch data/outputs/fail/ --api-key $KEY
```

---

## Safety Features

### Backups
- ✅ Original file saved as `.backup` before modification
- ✅ Can restore if LLM fix makes it worse

### Dry Run Mode
- ✅ Preview changes without saving
- ✅ Test on single conversation first

### Selective Fixing
- ✅ Choose which error types to fix
- ✅ Skip risky fixes (e.g., success improvements)

### Manual Review
- ✅ Success improvements are only suggestions
- ✅ You decide whether to apply them

---

## When to Use Which Tool?

### Use `analyze_and_fix_failures.py` (Rule-Based) When:
- ✅ You want quick, free fixes for simple syntax errors
- ✅ You're processing many conversations at once
- ✅ You want deterministic, predictable fixes

### Use `llm_fix_failures.py` (LLM-Based) When:
- ✅ You have faithfulness errors (hallucinations)
- ✅ You have role confusion issues
- ✅ Syntax errors are complex
- ✅ You want context-aware fixing
- ✅ You need to preserve conversational flow
- ✅ You're okay with API costs

### Use Both:
```bash
# 1. Quick rule-based syntax fixes (free)
python3 scripts/analyze_and_fix_failures.py --fix-syntax

# 2. LLM-based fixes for remaining issues (costs API credits)
python3 scripts/llm_fix_failures.py \
    --batch data/outputs/fail/ \
    --fix-types faithfulness role_confusion \
    --api-key $KEY
```

---

## Cost Estimation

Using GPT-4.5/5.1:
- **Small conversation** (5 turns): ~$0.01-0.05 per fix
- **Medium conversation** (10 turns): ~$0.05-0.10 per fix
- **Large conversation** (20+ turns): ~$0.10-0.20 per fix

**Batch processing 20 failures:** ~$1-3 total

💡 **Tip:** Use `--fix-types syntax` only to minimize costs, then manually handle other types.

---

## Troubleshooting

### "LLM returned invalid format"
- Try different model: `--model gpt-4.5`
- Check API key is valid
- Review prompt templates in the script

### "Fix made conversation worse"
- Restore from backup: `mv conversation.json.backup conversation.json`
- Try with different fix types
- Use dry run first: `--dry-run`

### "Too slow for batch processing"
- Use rule-based tool first for syntax
- Process subset: `--fix-types syntax` only
- Consider parallelization (future enhancement)

---

## Future Enhancements

Potential improvements:
- [ ] Parallel processing for batch fixes
- [ ] Custom prompts per domain
- [ ] Fine-tuned model for this specific task
- [ ] Confidence scores for fixes
- [ ] A/B testing: compare rule-based vs LLM fixes
- [ ] Caching common fix patterns

---

## Summary

**LLM-based fixing** is a powerful complement to rule-based approaches:

✅ **Use LLM when:** You need intelligent, context-aware fixes for complex issues
⚡ **Use rules when:** You need fast, free fixes for simple syntax errors
🎯 **Best approach:** Combine both tools for optimal results

Start here:
```bash
python3 scripts/llm_fix_failures.py --conversation-id YOUR_ID --dry-run --api-key $KEY
```

