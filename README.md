# Multi-Agent Dialogue Generator

A system for generating realistic multi-agent conversations between user, system, and tool agents for training and evaluation.

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Create `.env` file and set `OPENAI_API_KEY=your_key_here`

---

## Running Simulations

### `simulate.py` - Run a Single Conversation

The `simulate.py` script runs a single conversation simulation between three agents (user, system, tool) based on a scenario configuration file.

**Basic Usage:**
```bash
python src/simulate.py ca_sm_001__persona_002 --run-eval
```

**With Options:**
```bash
python src/simulate.py ca_sm_001__persona_002 \
  --model gpt-5.1 \
  --max-turns 20 \
  --run-eval \
  --verbose
```

**What it does:**
- Loads a scenario configuration file (persona-specific JSON)
- Runs a conversation between user, system, and tool agents
- Outputs `conversation.json` with the full conversation trace
- Optionally runs evaluation and saves `eval.json`

**Key Options:**
- `--model MODEL` - LLM model to use (default: gpt-5.1)
- `--max-turns N` - Maximum conversation turns (default: 20)
- `--run-eval` - Automatically run evaluation after conversation
- `--eval-model MODEL` - Model for evaluation (default: gpt-5.1)
- `--skip-faithfulness` - Skip faithfulness evaluation
- `--skip-role-confusion` - Skip role confusion evaluation
- `--persona-id ID` - Override persona ID from scenario file
- `--outputs-root DIR` - Custom output directory (default: `data/outputs`)
- `--verbose, -v` - Verbose console output
- `--debug-transcripts` - Write system.md/user.md/tool.md markdown files
- `--export-steps-jsonl` - Export per-turn traces to `turns.jsonl`

**Output Location:**
Conversations are saved to `data/outputs/<scenario_key>__simulate_<persona>_<timestamp>/`:
- `conversation.json` - Full conversation artifact
- `eval.json` - Evaluation results (if `--run-eval` used)
- `simulate.log` - Execution log
- `agent_prompts.json` - Captured agent prompts

---

### `orchestrate.py` - Run Multiple Scenarios

The `orchestrate.py` script runs multiple scenarios sequentially or in parallel. It calls `simulate.py` internally for each scenario.

**Basic Usage:**
```bash
# Run scenarios by ID
python src/orchestrate.py ca_oe_005__persona_001 ca_rm_002__persona_002

# Run all scenarios in a use case directory
python src/orchestrate.py data/domains/online_shopping/return_order

# Run all scenarios in a domain (recursive)
python src/orchestrate.py data/domains/calendar_assistant

# Run all scenarios across all domains
python src/orchestrate.py data/domains
```

**With Options:**
```bash
python src/orchestrate.py data/domains/calendar_assistant \
  --run-eval \
  --model gpt-5.1 \
  --max-turns 20 \
  --parallel 4
```

**What it does:**
- Finds scenario files based on targets (IDs, paths, or directories)
- Runs each scenario using `simulate.py` internally
- Collects results and prints a summary
- Saves orchestration summary JSON

**Key Options:**
- `--run-eval` - Run evaluation after each conversation
- `--model MODEL` - LLM model to use (default: gpt-5.1)
- `--max-turns N` - Maximum conversation turns (default: 20)
- `--eval-model MODEL` - Model for evaluation (default: gpt-5.1)
- `--skip-faithfulness` - Skip faithfulness evaluation
- `--skip-role-confusion` - Skip role confusion evaluation
- `--persona-id ID` - Override persona ID for all scenarios
- `--parallel N` - Run N scenarios in parallel (default: 1, sequential)
- `--dry-run` - Show what would be run without executing
- `--verbose, -v` - Verbose output (passed to simulate.py)
- `--use-case NAME` - When target is a domain, specify use case to run

**How it interacts with simulate.py:**
- `orchestrate.py` is a wrapper that calls `simulate.py` for each scenario
- All `simulate.py` options can be passed through (use `--` to separate)
- Results from each simulation are collected and summarized
- The summary includes success rates, eval results, and timing

---

## Viewing Conversations

### `view.py` - Clean Conversation Viewer

The `view.py` script formats `conversation.json` files for easy reading from different agent perspectives.

**Usage:**
```bash
# View from system perspective (sees everything)
python src/view.py data/outputs/.../conversation.json

# View from user perspective (sees user messages + assistant say outputs only)
python src/view.py data/outputs/.../conversation.json --as user

# View from tool perspective (sees tool calls + responses only)
python src/view.py data/outputs/.../conversation.json --as tool

# Save markdown file
python src/view.py conversation.json --as system --to-file
```

**Options:**
- `--as {system|user|tool}` - Perspective to view from (default: system)
- `--to-file` - Write markdown file to disk
- `--no-color` - Disable ANSI colors

---

## Evaluation

Evaluation scripts check conversation quality across multiple dimensions. They can be run together via `eval.run` or individually.

### Running All Evaluations Together

```bash
# Run all evaluations (syntax, success, faithfulness, role confusion)
PYTHONPATH=src python -m eval.run conversation.json

# Skip specific evaluations
PYTHONPATH=src python -m eval.run conversation.json \
  --skip-faithfulness \
  --skip-role-confusion

# Syntax checks only (no LLM calls)
PYTHONPATH=src python -m eval.run conversation.json --syntax-only
```

**Options:**
- `--model MODEL` - Model for success judge (default: gpt-5.1)
- `--faithfulness-model MODEL` - Model for faithfulness (default: reuse --model)
- `--role-confusion-model MODEL` - Model for role confusion (default: reuse --model)
- `--syntax-only` - Run syntax checks only (no LLM evaluations)
- `--skip-faithfulness` - Skip faithfulness evaluation
- `--skip-role-confusion` - Skip role confusion evaluation
- `--recursive` - Search directories recursively for conversation.json files
- `--jsonl` - Output each result as a single JSON line

### Running Evaluations Separately

Each evaluation can be run independently:

```bash
# Success evaluation only
PYTHONPATH=src python -m eval.success.cli conversation.json --model gpt-5.1

# Faithfulness evaluation only
PYTHONPATH=src python -m eval.faithfulness.cli conversation.json --model gpt-5.1

# Role confusion evaluation only
PYTHONPATH=src python -m eval.role_confusion.cli conversation.json --model gpt-5.1

# Syntax checks only
PYTHONPATH=src python -m eval.syntax.cli conversation.json
```

**Evaluation Types:**
- **Syntax**: Validates conversation structure and tool call syntax
- **Success**: LLM judge determines if the task was accomplished (uses `success_criteria` if present)
- **Faithfulness**: Checks if assistant claims match tool call results
- **Role Confusion**: Detects if user agent acts like system agent

---

## Data Directory Structure

Every conversation gets its own configuration file. The structure is:

```
data/
├── domains/
│   ├── calendar_assistant/
│   │   ├── tools.json                    # Domain tool definitions
│   │   ├── schedule_meeting/
│   │   │   ├── ca_sm_001__persona_002.json  # Scenario config (persona-specific)
│   │   │   ├── ca_sm_002__persona_004.json
│   │   │   └── ...
│   │   └── reschedule_meeting/
│   │       ├── ca_rm_001__persona_004.json
│   │       └── ...
│   └── online_shopping/
│       ├── tools.json
│       └── return_order/
│           ├── os_ro_001__persona_025.json
│           └── ...
├── personas/
│   └── catalog.json                      # Persona definitions
└── outputs/                              # Generated conversations
    └── calendar_assistant.schedule_meeting.ca_sm_001__simulate_persona_002_20250118_143022/
        ├── conversation.json
        └── eval.json
```

**Key Points:**
- Each scenario file is named `<scenario_id>__persona_<id>.json`
- Files are persona-specific because they contain custom data (seed data, slots) tailored to that persona
- Domain tools are shared via `tools.json` referenced in scenario files
- Outputs mirror the scenario hierarchy with scenario keys

---

## Scenario Configuration Files

Each scenario configuration file (`<scenario_id>__persona_<id>.json`) contains:

**Structure:**
```json
{
  "metadata": {
    "domain": "calendar_assistant",
    "use_case": "schedule_meeting",
    "scenario_id": "ca_sm_001"
  },
  "domain_ref": {
    "toolset_path": "../tools.json"
  },
  "task": {
    "objective": "Schedule a meeting with Sarah next week",
    "slots": {
      "constraints": { ... },
      "preferences": { ... }
    },
    "success_criteria": { ... }
  },
  "user_agent": { ... },
  "tool_agent": {
    "context": {
      "seed": { ... }
    }
  },
  "persona": "persona_002"
}
```

**Why persona-specific:**
- Each persona has different background data (seed data in `tool_agent.context.seed`)
- Task slots are tailored to the persona's scenario
- Success criteria reference persona-specific data
- This ensures conversations are realistic and consistent with the persona's context

---

## Seed Data and Slots

**Seed Data** (`tool_agent.context.seed`):
- Provides the "ground truth" data available in the simulated environment
- Examples: existing calendar events, past orders, restaurant availability
- The tool agent uses this to generate realistic tool responses

**Slots** (`task.slots`):
- Define what the user wants to accomplish
- Split into `constraints` (must be satisfied) and `preferences` (should be satisfied)
- Examples: `attendees: ["sarah@example.com"]`, `duration_minutes: 60`

**Relationship:**
- Slots specify what the user is trying to do
- Seed data provides the context/environment the user operates in
- The assistant must use tools to query seed data and satisfy slot requirements
- Success criteria verify the assistant worked with the right seed data (via `target_selector`) and performed the right action

**Example:**
```json
{
  "task": {
    "slots": {
      "constraints": {
        "attendees": ["sarah.chen@uoregon.edu"],
        "duration_minutes": 60
      }
    }
  },
  "tool_agent": {
    "context": {
      "seed": {
        "events": [
          {
            "event_id": "EVT-001",
            "attendees": ["sarah.chen@uoregon.edu"],
            "start_time": "2025-11-10T10:00:00Z"
          }
        ],
        "available_slots": [...]
      }
    }
  }
}
```

The user wants to schedule a 60-minute meeting with Sarah (slots). The seed data shows existing events and available time slots. The assistant must check availability and create a meeting.

---

## Success Criteria in Evaluation

The `success_criteria` field in scenario files provides explicit success conditions for evaluation:

```json
{
  "task": {
    "success_criteria": {
      "target_selector": {
        "attendees": ["sarah.chen@uoregon.edu"]
      },
      "action": "create_meeting",
      "notes": "Success if the assistant schedules a meeting with Sarah via create_meeting for 60 minutes."
    }
  }
}
```

**How it's used:**
- `target_selector`: Identifies which entities in seed data the assistant should work with
- `action`: Specifies the required tool call name
- `notes`: Human-readable description for the LLM judge

**In evaluation:**
- The success judge uses `success_criteria` as the primary definition of success
- It checks that tool calls match the `target_selector` and `action`
- If `success_criteria` is absent, the judge infers success from `task.objective` and `task.slots`
- `constraints` in slots are treated as hard requirements; `preferences` can be relaxed with user agreement

---

## Project Structure

```
├── src/
│   ├── simulate.py          # Run single conversation
│   ├── orchestrate.py        # Run multiple conversations
│   ├── view.py              # View conversation files
│   ├── agents.py            # Agent implementations
│   ├── core.py              # Core LLM client
│   ├── scenario.py          # Scenario loading
│   ├── runner.py            # Conversation execution
│   └── eval/                # Evaluation modules
│       ├── run.py           # Run all evaluations
│       ├── success/         # Success evaluation
│       ├── faithfulness/    # Faithfulness evaluation
│       ├── role_confusion/  # Role confusion detection
│       └── syntax/          # Syntax validation
├── data/
│   ├── domains/             # Scenario configurations
│   ├── personas/           # Persona catalog
│   └── outputs/            # Generated conversations
└── prompts/                # Agent prompt templates
    ├── system_agent/
    ├── user_agent/
    └── tool_agent/
```

---

## How It Works

The simulator orchestrates conversations between three specialized AI agents:

- **System Agent** - The main assistant that responds to users and makes tool calls
- **User Agent** - Simulates realistic user behavior based on scenario objectives  
- **Tool Agent** - Simulates external APIs and tools using seed data

**Process:**
1. Load scenario (tools + user context) and agent prompts
2. User agent generates message → System agent responds (may call tools) → Tool agent processes calls → repeat
3. Maintains separate conversation histories for each agent's perspective
4. Terminates when user signals completion or max turns reached
5. Outputs JSON results with conversation traces
