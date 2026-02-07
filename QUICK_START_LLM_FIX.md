# Quick Start: LLM-Based Failure Fixing

## 🎯 What's New

You now have **TWO ways** to fix failed conversations:

### Option 1: Rule-Based (Fast & Free) ⚡
```bash
python3 scripts/analyze_and_fix_failures.py --fix-syntax
```
- Simple pattern matching
- Only fixes syntax errors
- Free, fast, deterministic

### Option 2: LLM-Based (Smart & Powerful) 🧠
```bash
python3 scripts/llm_fix_failures.py --conversation-id os_to_001 --api-key $KEY
```
- AI understands context
- Fixes syntax, faithfulness, role confusion
- Costs API credits, but much more capable

---

## ⚡ Quick Commands

### Fix ONE conversation with LLM:
```bash
python3 scripts/llm_fix_failures.py \
    --conversation-id os_to_001 \
    --api-key $OPENAI_API_KEY
```

### Fix ALL failures with LLM:
```bash
python3 scripts/llm_fix_failures.py \
    --batch data/outputs/fail/ \
    --api-key $OPENAI_API_KEY
```

### Dry run (see what would be fixed):
```bash
python3 scripts/llm_fix_failures.py \
    --conversation-id os_to_001 \
    --dry-run \
    --api-key $OPENAI_API_KEY
```

### Fix specific error types only:
```bash
# Just syntax
python3 scripts/llm_fix_failures.py \
    --conversation-id os_to_001 \
    --fix-types syntax \
    --api-key $KEY

# Syntax + faithfulness
python3 scripts/llm_fix_failures.py \
    --conversation-id os_to_001 \
    --fix-types syntax faithfulness \
    --api-key $KEY
```

---

## 🤔 Which Should I Use?

### Use LLM-Based When:
- ✅ You have **faithfulness errors** (hallucinations)
- ✅ You have **role confusion** (user acting like assistant)
- ✅ Complex **syntax errors** that rules can't fix
- ✅ You want to preserve conversation flow and meaning
- ✅ You're okay with **API costs** (~$0.01-0.10 per conversation)

### Use Rule-Based When:
- ✅ Simple **syntax errors** only
- ✅ You need **fast** processing
- ✅ You want **free** fixes (no API costs)
- ✅ You're processing **many** conversations at once

### Best Approach: Use BOTH! 💡
```bash
# Step 1: Rule-based for quick syntax fixes (free)
python3 scripts/analyze_and_fix_failures.py --fix-syntax

# Step 2: LLM for remaining complex issues (API cost)
python3 scripts/llm_fix_failures.py \
    --batch data/outputs/fail/ \
    --fix-types faithfulness role_confusion \
    --api-key $KEY
```

---

## 🎨 What LLM Can Fix That Rules Cannot

### 1. Hallucinations (Faithfulness Errors)

**Problem:**
```
Tool returned: {"status": "delivered"}
Assistant said: "Your package was delivered at 2pm to your front door"
                 ↑ Time and location NOT in tool response!
```

**LLM Fix:**
```
"Your package has been delivered"
 ↑ Only states what's in tool response
```

### 2. Role Confusion

**Problem:**
```
User: "Happy to give you whatever you need from me to get that going"
      ↑ Acting like an assistant, not a customer!
```

**LLM Fix:**
```
User: "Sure, I can provide that information"
      ↑ Natural customer response
```

### 3. Complex Syntax

**Problem:**
```
<think>
reasoning
<plan>  ← Multiple missing tags, nested issues
step 1
<action type="say"
message
```

**LLM Fix:**
```
<think>
reasoning
</think>
<plan>
step 1
</plan>
<action type="say">
message
</action>
```

---

## 📊 Real Example

Let's fix `os_to_001` which has syntax errors AND role confusion:

```bash
# 1. See what's wrong
python3 scripts/diagnose_failures.py --conversation-id os_to_001
```

Output:
```
Failure Types: syntax, role_confusion
- Syntax: Invalid block format in turns [3, 5]
- Role Confusion: User acting like assistant in turn [4]
```

```bash
# 2. Fix with LLM (handles both!)
python3 scripts/llm_fix_failures.py \
    --conversation-id os_to_001 \
    --api-key $OPENAI_API_KEY
```

Output:
```
Processing: online_shopping.os_to_001
  Fixing syntax errors with LLM...
    ✓ Fixed 2 syntax errors
  Fixing role confusion with LLM...
    ✓ Fixed 1 role confusion error
  
Successfully fixed: 1
```

**Result:** Both issues fixed intelligently by the LLM! ✅

---

## 💰 Cost Comparison

| Approach | Speed | Cost | Can Fix |
|----------|-------|------|---------|
| **Rule-Based** | ⚡⚡⚡ Fast | 💰 Free | Syntax only |
| **LLM-Based** | 🐌 Slower | 💰💰 ~$0.05/conv | All types |

**Estimated costs for 20 failures:**
- Rule-based: $0 (free)
- LLM-based: ~$1-2 total

---

## 🛡️ Safety Features

### Automatic Backups
```bash
# LLM creates backup before modifying
conversation.json          ← Modified by LLM
conversation.json.backup  ← Original saved here
```

### Dry Run Mode
```bash
# Preview changes without saving
python3 scripts/llm_fix_failures.py --conversation-id os_to_001 --dry-run --api-key $KEY
```

### Selective Fixing
```bash
# Only fix what you trust
python3 scripts/llm_fix_failures.py \
    --conversation-id os_to_001 \
    --fix-types syntax \
    --api-key $KEY
```

---

## 📚 Full Documentation

- **Complete guide:** `scripts/LLM_FIX_GUIDE.md`
- **Technical details:** `scripts/llm_fix_failures.py`
- **Comparison:** See "Rule-Based vs LLM-Based" section in guide

---

## ✅ Recommended Workflow

### For Individual Conversations:
```bash
# 1. Diagnose the issue
python3 scripts/diagnose_failures.py --conversation-id CONV_ID

# 2. Fix with LLM
python3 scripts/llm_fix_failures.py --conversation-id CONV_ID --api-key $KEY

# 3. Verify
python3 -m eval.run data/outputs/.../
```

### For Batch Processing:
```bash
# 1. Get overview
python3 scripts/analyze_and_fix_failures.py --output report.txt

# 2. Quick rule-based fixes (free)
python3 scripts/analyze_and_fix_failures.py --fix-syntax

# 3. LLM fixes for remaining issues (costs API credits)
python3 scripts/llm_fix_failures.py \
    --batch data/outputs/fail/ \
    --fix-types faithfulness role_confusion \
    --api-key $KEY
```

---

## 🚀 Get Started Now

**Simplest command to try:**
```bash
python3 scripts/llm_fix_failures.py \
    --conversation-id os_to_001 \
    --dry-run \
    --api-key $OPENAI_API_KEY
```

This will:
- ✅ Show you what would be fixed
- ✅ Not save any changes (dry run)
- ✅ Let you see the LLM's capabilities
- ✅ Cost almost nothing (~$0.01)

Then remove `--dry-run` to actually apply the fixes!

---

## 💡 Pro Tips

1. **Start with dry run** to preview changes
2. **Fix syntax first** (cheapest with rules, then LLM if needed)
3. **Use LLM for faithfulness** (rules can't handle this)
4. **Review success suggestions** before applying (too risky to auto-apply)
5. **Batch carefully** (costs add up, but ~$2 for 20 conversations is reasonable)

---

## Summary

You now have **intelligent, LLM-powered fixing** that can:
- 🧠 Understand context and intent
- 🔧 Fix syntax, faithfulness, and role confusion
- 💬 Preserve conversational flow
- 🎯 Handle complex issues rules cannot

**Start here:**
```bash
python3 scripts/llm_fix_failures.py --conversation-id YOUR_ID --dry-run --api-key $KEY
```

**Questions?** See `scripts/LLM_FIX_GUIDE.md` for complete documentation.

