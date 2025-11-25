# Failure Investigation Guide

## Agent Context Access

**SystemAgent** receives:
- `tools` dict (from scenario or `tools.json`)
- Conversation history (`system_history`)

**UserAgent** receives:
- `user_agent` config (objective, slots, persona, injected_behaviors)
- Conversation history (`user_history`)
- Persona details (writing style, sample messages, bio, contact info)

**ToolAgent** receives:
- `tools` dict
- `tool_agent` config (injected_behaviors)
- `scenario_context` containing:
  - `task_slots` (from `task.slots`)
  - `seed_data` (from `tool_agent.context.seed`)
- Tool conversation history

**Success Judge** (evaluation only) receives:
- Task objective
- Target slots (constraints/preferences)
- Success criteria (if present)
- Conversation transcript with tool calls/results

---

## Step-by-Step Investigation Workflow

### Step 1: Identify the failure type and what was supposed to happen
- What failure occurred? (success, faithfulness, syntax, role confusion)
- What action was required? (from success criteria or inferred from objective)
- What tool call should have been made? (if applicable)

### Step 2: Trace what the assistant actually did
- Review the conversation transcript
- Which tool calls were made? (if any)
- What did the assistant claim vs. what actually happened?
- Where did the assistant get stuck or make mistakes?

### Step 3: Check if the assistant had all required information
- What information did the assistant need? (from tool definition: required vs optional parameters)
- What information did the assistant receive?
  - From user messages (what the user said)
  - From tool observations (what tools returned)
  - From system context (what's in the prompt)
- Was anything missing? (required parameters not available)

### Step 4: Verify user agent references match seed data
- What entities did the user agent reference? (meetings, orders, cards, transactions, etc.)
- What specific details did the user provide? (IDs, names, dates, amounts, emails, etc.)
- What exists in seed data? (check `tool_agent.context.seed`)
- Do they match? (same IDs, same details, same entities)
- If not, this is a configuration mismatch — user agent is describing things that don't exist
- Check injected behaviors: Do they describe user behavior patterns, or scenario setup? If they describe seed data state rather than user actions, they're misconfigured and can cause role confusion

### Step 5: Check tool definitions and seed data alignment
- What does the tool definition require? (required parameters, return types)
- What does seed data provide? (structure, fields, values)
- Can the tool be called with available data? (all required params available)
- Can the tool return what's needed? (seed data has matching structure)

### Step 6: Verify success criteria are achievable
- What does success criteria require? (specific action, specific target)
- Is that action possible given seed data? (e.g., can't cancel if already shipped)
- Does success criteria match seed data constraints? (e.g., requires full cancellation but only partial is possible)

### Step 7: Check slots vs seed data alignment
- What do slots specify? (constraints, preferences)
- What does seed data allow? (available states, possible actions)
- Are slots achievable? (can constraints be satisfied with seed data)

### Step 8: Determine root cause
- Configuration mismatch? (user agent references ≠ seed data, slots ≠ seed data, success criteria ≠ seed data, injected behaviors describing scenario setup instead of user behavior)
- Missing data? (required tool params not available from any source)
- Agent behavior? (assistant had everything but made a mistake)
- Prompt/instruction issue? (assistant misunderstood what to do, or prompt doesn't explicitly state requirements that syntax checker enforces)

### Step 9: Identify the fix
- If configuration mismatch: align the mismatched elements (update seed data, update slots, update user agent references, or update success criteria)
- If missing data: add data to slots or seed data, or make tool params optional
- If agent behavior: improve prompts/instructions (but only if it's truly agent error, not config issue)
- If success criteria: make criteria achievable or adjust seed data to match

---

## Key Principles

- Always check the four-element balance: tools, seed data, slots, success criteria
- Trace information flow: user agent → assistant → tool agent → tool responses → assistant
- Verify each claim: if user says "my card ending in 4418", check if that card exists in seed data
- Check tool requirements: if tool needs `event_id` (required), verify it's available
- Consider cascading failures: missing data → assistant gets stuck → hallucination → multiple failure types

---

## Red Flags to Watch For

- User agent mentions specific entities (IDs, names, details) that don't appear in seed data
- Assistant searches multiple times but can't find matching entities
- Assistant claims to have done something but no tool call appears
- Success criteria requires actions that seed data makes impossible
- Tool requires parameters that aren't in slots or seed data
- Syntax failures (empty say actions, invalid block format) — often indicate configuration/prompt issues, not just agent errors

---

## Key Files and Locations

**Scenario Configuration:**
- `data/domains/{domain}/{use_case}/{scenario_id}__{persona_id}.json` - Scenario config files

**Tool Definitions:**
- `data/domains/{domain}/tools.json` - Domain-level tool schemas

**Conversation Outputs:**
- `data/outputs/{timestamp}__{scenario_id}__{persona_id}/{timestamp}__{scenario_id}__{persona_id}.json` - Conversation transcripts

**Evaluation Results:**
- `data/outputs/{timestamp}__{scenario_id}__{persona_id}/eval.json` - Evaluation results

**Documentation:**
- `docs/failure_modes_guide.md` - Detailed failure patterns and examples
- `docs/common_issues_by_domain.md` - Domain-specific failure patterns
- `docs/scenario_schema_guide.md` - Scenario configuration schema

**Agent Prompts:**
- `prompts/system_agent/v*.txt` - System agent prompts
- `prompts/user_agent/v*.txt` - User agent prompts
- `prompts/tool_agent/v*.txt` - Tool agent prompts

**Source Code:**
- `src/agents.py` - Agent implementations and context building
- `src/runner.py` - Conversation orchestration
- `src/eval/` - Evaluation judges (success, faithfulness, syntax, role confusion)

