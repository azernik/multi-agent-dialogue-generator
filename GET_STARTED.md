# Get Started with Failure Analysis Tools

## 🎯 TL;DR - Run These Commands

```bash
cd /Users/muditarora/multi-agent-dialogue-generator

# 1. See what's failing and why
python3 scripts/analyze_and_fix_failures.py --output report.txt
cat report.txt

# 2. Auto-fix what can be fixed (syntax errors)
python3 scripts/analyze_and_fix_failures.py --fix-syntax --reeval --api-key $OPENAI_API_KEY

# 3. Get detailed help for remaining issues
python3 scripts/diagnose_failures.py --batch data/outputs/fail/ --output help.txt
cat help.txt
```

That's it! These three commands will:
- ✅ Analyze all 20 failures in your `data/outputs/fail/` directory
- ✅ Automatically fix syntax errors and re-evaluate
- ✅ Provide specific fix instructions for everything else

---

## 📖 What You Now Have

### Two Powerful Tools

**1. `analyze_and_fix_failures.py`**
- Analyzes ALL failures at once
- Automatically fixes syntax errors (malformed blocks)
- Re-runs evaluation to verify fixes work
- Shows statistics and patterns

**2. `diagnose_failures.py`**
- Deep-dives into specific failures
- Tells you EXACTLY what to fix and how
- Provides step-by-step investigation guidance
- References your documentation

### Complete Documentation

- **`FAILURE_ANALYSIS_TOOLS.md`** - Quick start guide
- **`scripts/README_FAILURE_ANALYSIS.md`** - Complete reference
- **`scripts/IMPLEMENTATION_SUMMARY.md`** - Technical details

---

## 🔥 Real Example

Let's fix the `os_to_001` conversation that's currently failing:

```bash
# 1. What's wrong?
python3 scripts/diagnose_failures.py --conversation-id os_to_001
```

**Output tells you:**
```
Problem 1: SYNTAX - Invalid block format in turns 3 and 5
  Fix: Run the auto-fix command below ⬇️

Problem 2: ROLE_CONFUSION - User acting like assistant in turn 4
  Fix: Edit the persona to avoid "happy to give you whatever you need"
```

```bash
# 2. Auto-fix the syntax
python3 scripts/analyze_and_fix_failures.py --fix-syntax --reeval
```

**Result:**
- ✅ Syntax fixed automatically
- ✅ Conversation re-evaluated
- ✅ New results saved to `eval_fixed.json`
- ⚠️ Role confusion still needs manual fix

```bash
# 3. Manual fix for role confusion
vim data/domains/online_shopping/track_order/os_to_001__persona_005.json
# Remove assistant-like phrasing from user_agent config

# 4. Regenerate conversation
python3 src/runner.py --scenario data/domains/online_shopping/track_order/os_to_001__persona_005.json

# 5. Verify it works
python3 -m eval.run data/outputs/NEW_OUTPUT/
```

Done! Conversation now passes all criteria. ✅

---

## 💡 What Gets Auto-Fixed

### ✅ Auto-Fixable (No human intervention needed)

**Syntax Errors:**
- Unclosed `<think>` blocks → Automatically adds `</think>`
- Unclosed `<plan>` blocks → Automatically adds `</plan>`
- Extra whitespace → Cleaned up
- Malformed block structure → Corrected

**Example:**
```xml
<!-- BEFORE (broken) -->
<think>
reasoning here
<plan>  ⬅️ Missing </think> !

<!-- AFTER (fixed) -->
<think>
reasoning here
</think>  ⬅️ Auto-added!
<plan>
```

### ❌ Needs Manual Fix (Tool tells you exactly how)

**Success Failures:**
- Missing tool calls → "Add X to slots" or "Update seed data"
- Config mismatches → "User mentions Y but seed has Z"

**Faithfulness Failures:**
- Hallucinations → "Update system prompt to prevent..."

**Role Confusion:**
- Wrong phrasing → "Change 'let me know' to 'thanks'"

---

## 📊 What You'll See

### Analysis Report

```
FAILURE ANALYSIS REPORT
================================================================================

Total Failed Conversations: 20

Failures by Type:
  syntax              :    5 ( 25.0%)  ⬅️ Can auto-fix these!
  success             :   12 ( 60.0%)  ⬅️ Config issues
  faithfulness        :    8 ( 40.0%)  ⬅️ Hallucinations
  role_confusion      :    3 ( 15.0%)  ⬅️ Prompt issues

Top Failure Combinations:
  success+faithfulness                    :    6 ( 30.0%)
  syntax+role_confusion                   :    2 ( 10.0%)

Fix Summary:
  Fixable: 5              ⬅️ 5 have syntax errors
  Fix Attempted: 5        ⬅️ Tried to fix all 5
  Fix Successful: 3       ⬅️ 3 now pass!
  Success Rate: 60.0%

SAMPLE FAILURES FOR INVESTIGATION
[Shows examples of each type with specific details]
```

### Diagnostic Report

```
DIAGNOSTIC REPORT: online_shopping.os_to_001
================================================================================

Severity: HIGH
Failure Types: syntax, role_confusion

RECOMMENDATIONS:

1. [SYNTAX] Invalid block format in 2 turn(s)
   Affected turns: [3, 5]
   Root cause: Assistant output has malformed XML-like blocks
   
   Fix: Run this command:
   python3 scripts/analyze_and_fix_failures.py --fix-syntax --reeval
   
   Prevention: Update system agent prompt to emphasize proper block formatting

2. [ROLE_CONFUSION] User agent confused its role
   Affected turns: [4]
   Reason: In turn 4 the user offers to help the assistant
   Root cause: User phrasing like "happy to give you whatever you need"
   
   Examples:
     BAD: "Let me know if you need anything"
     GOOD: "Thanks! I'll try that"
   
   Fix: Update user_agent.injected_behaviors in scenario config
   
   Prevention: Clarify in user prompt to respond as customer, not helper
   
   Reference: docs/common_issues_by_domain.md
```

---

## 🚀 Next Steps

### Immediate Actions (5 minutes)

```bash
# Get the overview
python3 scripts/analyze_and_fix_failures.py --output report.txt
cat report.txt

# Fix what's auto-fixable
python3 scripts/analyze_and_fix_failures.py --fix-syntax --reeval --api-key $KEY
```

### Deep Dive (30 minutes)

```bash
# Get detailed diagnostics for all failures
python3 scripts/diagnose_failures.py --batch data/outputs/fail/ --output detailed.txt

# Read through recommendations
cat detailed.txt | less

# Apply manual fixes to scenario configs based on recommendations
```

### Long-term (Ongoing)

1. **Before generating new conversations:**
   - Review past diagnostics
   - Apply prevention strategies
   - Validate configurations

2. **After generating conversations:**
   - Run evaluation
   - If failed, run diagnostic
   - Apply fixes (auto + manual)
   - Regenerate and verify

---

## 🆘 Need Help?

### "Which command should I run?"

Start here: `python3 scripts/analyze_and_fix_failures.py --output report.txt`

### "How do I fix a specific failure?"

Run: `python3 scripts/diagnose_failures.py --conversation-id YOUR_ID`

It will tell you EXACTLY what to do.

### "Can this fix everything automatically?"

- ✅ Syntax errors: YES (auto-fixed with `--fix-syntax`)
- ❌ Other errors: NO (but tool tells you how to fix manually)

### "I want to understand how it works"

Read: `scripts/README_FAILURE_ANALYSIS.md` (comprehensive guide)

---

## 📁 Where Are Things?

```
Your Project/
├── data/outputs/fail/           ⬅️ Failed conversations here
│   └── */eval.json              ⬅️ Shows what failed
│
├── scripts/
│   ├── analyze_and_fix_failures.py  ⬅️ Main tool
│   ├── diagnose_failures.py         ⬅️ Diagnostic tool
│   └── README_FAILURE_ANALYSIS.md   ⬅️ Full documentation
│
├── docs/                        ⬅️ Your investigation guides
│   ├── failure_investigation_guide.md
│   ├── common_issues_by_domain.md
│   └── scenario_schema_guide.md
│
└── GET_STARTED.md              ⬅️ You are here!
```

---

## ✅ Checklist

- [ ] Run `analyze_and_fix_failures.py --output report.txt`
- [ ] Review the statistics to understand what's failing
- [ ] Run `analyze_and_fix_failures.py --fix-syntax --reeval` to auto-fix
- [ ] Run `diagnose_failures.py --batch ...` for remaining issues
- [ ] Apply manual fixes based on diagnostic recommendations
- [ ] Update scenario configurations
- [ ] Regenerate conversations
- [ ] Verify with `python3 -m eval.run`

---

**You're all set!** The tools are ready to use right now. Start with the first command and follow the guidance in the reports. 🎉

