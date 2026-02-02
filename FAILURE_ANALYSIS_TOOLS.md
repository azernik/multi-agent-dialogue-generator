# Failure Analysis & Auto-Fix Tools - Quick Start

## What I've Created

I've built a comprehensive failure analysis and auto-fix system based on your evaluation framework and investigation guides. This system can:

1. **Analyze** all failed evaluations and categorize them by failure type
2. **Auto-fix** certain types of failures (primarily syntax errors)
3. **Diagnose** specific failures with actionable recommendations
4. **Re-evaluate** fixed conversations to verify success

## Files Created

### Core Tools

1. **`scripts/analyze_and_fix_failures.py`** (600+ lines)
   - Scans all failures in `data/outputs/fail/`
   - Categorizes by type: syntax, success, faithfulness, role_confusion
   - Identifies patterns and common issues
   - **Auto-fixes syntax errors** (malformed blocks)
   - Re-runs evaluations after fixes
   - Generates comprehensive analysis report

2. **`scripts/diagnose_failures.py`** (450+ lines)
   - Deep diagnostic analysis for specific failures
   - Root cause identification
   - Actionable fix recommendations
   - Prevention strategies
   - References to your investigation guides

3. **`scripts/README_FAILURE_ANALYSIS.md`**
   - Complete documentation
   - Usage examples for all scenarios
   - Investigation workflows
   - Common patterns and fixes
   - Example session walkthrough

4. **`scripts/test_diagnostic.sh`**
   - Quick test script to verify everything works

## Quick Start

### 1. Analyze All Failures

```bash
cd /Users/muditarora/multi-agent-dialogue-generator

# Get overview of all failures
python3 scripts/analyze_and_fix_failures.py --output reports/failure_analysis.txt

# Save detailed data
python3 scripts/analyze_and_fix_failures.py --json-output reports/analysis_data.json
```

**Output includes:**
- Total failures by type
- Most common failure combinations
- Syntax error patterns
- Faithfulness issue types
- Sample failures for investigation

### 2. Attempt Automatic Fixes

```bash
# Fix syntax errors (no re-evaluation yet)
python3 scripts/analyze_and_fix_failures.py --fix-syntax

# Fix syntax AND re-evaluate (requires OpenAI API key)
python3 scripts/analyze_and_fix_failures.py \
    --fix-syntax \
    --reeval \
    --api-key $OPENAI_API_KEY
```

**What gets fixed automatically:**
- ✅ `structure_invalid_block_format` - Unclosed `<think>`, `<plan>` blocks
- ✅ Malformed XML-like block syntax
- ✅ Extra whitespace between blocks

**What requires manual intervention:**
- ❌ Missing required tool calls (configuration issues)
- ❌ Hallucinations (prompt improvements needed)
- ❌ Role confusion (user agent prompt fixes)
- ❌ Configuration mismatches (seed data vs user references)

### 3. Diagnose Specific Failures

```bash
# Diagnose by conversation ID
python3 scripts/diagnose_failures.py --conversation-id os_to_001

# Diagnose by eval file path
python3 scripts/diagnose_failures.py \
    --eval-file data/outputs/fail/20251124_143228__os_to_001__persona_005/eval.json

# Batch diagnose all failures
python3 scripts/diagnose_failures.py \
    --batch data/outputs/fail/ \
    --output reports/detailed_diagnostics.txt
```

**Example diagnostic output:**

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
   Root cause: Assistant output has malformed XML-like blocks
   Fix: Run: python scripts/analyze_and_fix_failures.py --fix-syntax --reeval
   Prevention: Check system agent prompt for proper block formatting emphasis

2. [ROLE_CONFUSION] User agent confused its role
   Severity: MEDIUM
   Affected turns: [4]
   Reason: User offered to help assistant complete a task
   Root cause: User phrasing suggests offering help TO the assistant
   Fix: Update user_agent prompt to avoid assistant-like phrasing
   Prevention: Clarify user should respond as customer, not helper
```

## What Each Failure Type Means

### Syntax Failures (Auto-fixable ✅)

**What:** Structural issues in assistant output (malformed XML blocks)

**Common errors:**
- `structure_invalid_block_format` - Missing closing tags
- `structure_missing_block` - Missing `<think>`, `<plan>`, or `<action>`
- `structure_unexpected_text` - Text outside proper blocks

**Fix:** Auto-fixable with `--fix-syntax` flag

### Success Failures (Manual fix required ❌)

**What:** Task not completed per success criteria

**Common causes:**
- Missing required tool call
- Configuration mismatch (user mentions entities that don't exist in seed data)
- Assistant hallucinated completion without executing tools

**Fix:** Requires configuration changes or regeneration
- Update seed data to match user references
- Add missing data to slots
- Improve system prompt to prevent hallucinations

### Faithfulness Failures (Manual fix required ❌)

**What:** Assistant made unsupported claims (hallucinations)

**Types:**
- Tool parameters incompatible with user intent
- Say statements not grounded in actual tool results
- Fabricated data not from tool responses

**Fix:** Requires regeneration with improved prompts
- Add explicit grounding instructions
- Emphasize using only actual tool response data

### Role Confusion (Manual fix required ❌)

**What:** User agent acted like assistant instead of customer

**Examples:**
- "Let me know if you need anything" ❌
- "Happy to give you whatever you need from me" ❌
- "Can you help me?" ✅
- "Thanks!" ✅

**Fix:** Update user agent prompt/persona
- Remove assistant-like phrasing
- Use natural customer language

## Real Example: Fixing the os_to_001 Failure

```bash
# 1. Diagnose the issue
python3 scripts/diagnose_failures.py --conversation-id os_to_001

# Output shows:
# - Syntax errors in turns 3 and 5 (auto-fixable)
# - Role confusion in turn 4 (needs prompt update)

# 2. Auto-fix syntax
python3 scripts/analyze_and_fix_failures.py --fix-syntax --reeval

# Creates:
# - data/outputs/fail/.../conversation.json.backup (original)
# - data/outputs/fail/.../conversation.json (fixed version)
# - data/outputs/fail/.../eval_fixed.json (new evaluation)

# 3. Manual fix for role confusion
# Edit the user agent configuration to remove assistant-like phrasing
vim data/domains/online_shopping/track_order/os_to_001__persona_005.json

# Update user_agent.injected_behaviors or persona to avoid phrases like:
# "happy to give you whatever you need from me"

# 4. Regenerate conversation with fixed configuration
python3 src/runner.py \
    --scenario data/domains/online_shopping/track_order/os_to_001__persona_005.json

# 5. Verify success
python3 -m eval.run data/outputs/TIMESTAMP__os_to_001__persona_005/
```

## Understanding the Output

### Analysis Report (from analyze_and_fix_failures.py)

```
Total Failed Conversations: 20

Failures by Type:
  syntax              :    5 ( 25.0%)
  success             :   12 ( 60.0%)
  faithfulness        :    8 ( 40.0%)
  role_confusion      :    3 ( 15.0%)

Top Failure Combinations:
  success+faithfulness                    :    6 ( 30.0%)
  syntax+role_confusion                   :    2 ( 10.0%)

Fix Summary:
  Fixable: 5
  Fix Attempted: 5
  Fix Successful: 3
  Success Rate: 60.0%
```

**Interpretation:**
- 60% of failures are success-related (task not completed)
- 40% have faithfulness issues (hallucinations)
- Most common combo: success + faithfulness (agent hallucinated completing task)
- 5 conversations had auto-fixable syntax errors
- 3 out of 5 syntax fixes were successful after re-evaluation

### Diagnostic Report (from diagnose_failures.py)

Each recommendation includes:
- **Type**: Which failure category
- **Severity**: HIGH, MEDIUM, or LOW
- **Affected turns**: Which conversation turns had issues
- **Root cause**: Why it happened
- **Fix**: Specific action to take
- **Prevention**: How to avoid in future
- **Reference**: Link to relevant documentation

## Integration with Your Workflow

### Before Generation
1. Review past diagnostics to improve configurations
2. Apply prevention strategies from recommendations
3. Validate seed data matches user agent references

### After Generation
1. Run evaluation: `python3 -m eval.run data/outputs/NEW_OUTPUT/`
2. If failed, run analysis: `python3 scripts/diagnose_failures.py --eval-file PATH`
3. Apply auto-fixes if available: `--fix-syntax --reeval`
4. For manual fixes, follow diagnostic recommendations
5. Update configuration and regenerate

## Advanced Usage

### Custom Fail Directory

```bash
python3 scripts/analyze_and_fix_failures.py --fail-dir data/outputs/custom_fail/
```

### JSON Output for Processing

```bash
# Get JSON data for further analysis
python3 scripts/analyze_and_fix_failures.py --json-output analysis.json

# Get diagnostic JSON
python3 scripts/diagnose_failures.py --batch data/outputs/fail/ --json > diagnostics.json

# Process with jq
cat analysis.json | jq '.summary.by_type'
cat diagnostics.json | jq '.[] | select(.severity == "critical")'
```

### Filtering by Failure Type

```bash
# Find all syntax failures
python3 scripts/diagnose_failures.py --batch data/outputs/fail/ --json | \
    jq '.[] | select(.failure_types | contains(["syntax"]))'

# Find all critical success failures
python3 scripts/diagnose_failures.py --batch data/outputs/fail/ --json | \
    jq '.[] | select(.severity == "critical") | select(.failure_types | contains(["success"]))'
```

## Key Insights from Your Investigation Guides

The tools implement recommendations from your docs:

1. **Configuration Balance** (from failure_investigation_guide.md)
   - Checks alignment: user agent ↔ seed data ↔ slots ↔ success criteria
   - Identifies mismatches and suggests fixes

2. **Domain-Specific Patterns** (from common_issues_by_domain.md)
   - Recognizes patterns like "user references missing entities"
   - Suggests domain-specific fixes

3. **Schema Validation** (from scenario_schema_guide.md)
   - Validates constraints vs preferences
   - Checks success criteria structure
   - Verifies target_selector matches seed data

## Troubleshooting

### "No failures found!"
- Check `--fail-dir` path is correct
- Verify subdirectories contain `eval.json` files

### "Conversation file not found"
- Tool looks for `{subdir_name}.json` in same directory as `eval.json`
- Check file naming matches convention

### Re-evaluation errors
- Requires OpenAI API key: `--api-key $OPENAI_API_KEY`
- Network access needed (may need to run outside sandbox)

### Import errors
- Run from project root: `cd /Users/muditarora/multi-agent-dialogue-generator`
- Ensure `src/` is in Python path (scripts handle this automatically)

## Next Steps

1. **Run initial analysis:**
   ```bash
   python3 scripts/analyze_and_fix_failures.py --output initial_report.txt
   ```

2. **Review the report** to understand failure distribution

3. **Fix what's auto-fixable:**
   ```bash
   python3 scripts/analyze_and_fix_failures.py --fix-syntax --reeval
   ```

4. **Deep dive on remaining issues:**
   ```bash
   python3 scripts/diagnose_failures.py --batch data/outputs/fail/ --output detailed.txt
   ```

5. **Apply manual fixes** based on recommendations

6. **Update configurations** to prevent future failures

7. **Regenerate conversations** with improved configs

## Support

- **Full documentation:** `scripts/README_FAILURE_ANALYSIS.md`
- **Investigation guide:** `docs/failure_investigation_guide.md`
- **Common issues:** `docs/common_issues_by_domain.md`
- **Schema guide:** `docs/scenario_schema_guide.md`

---

**Questions or issues?** The diagnostic tools provide actionable recommendations with specific commands to run. Start with `diagnose_failures.py` for any specific failure you want to understand better.

