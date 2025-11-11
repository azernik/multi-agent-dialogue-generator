# Project Snapshot

## Purpose & Architecture
- Generates multi-agent (system/user/tool) conversations from scenario definitions; used to produce synthetic data.
- Simulator entry point: `src/simulate.py` — loads a scenario, initializes agents (`SystemAgent`, `UserAgent`, `ToolAgent`), loops through turns, and writes transcripts/JSON artifacts.
- Scenarios: `data/domains/<domain>/<use_case>/<scenario_id>/scenario.json` (task description/slots, personas, injected behaviors).
- Personas: `data/personas/catalog.json` — enriched PersonaHub bios with demographics, contact info, sample messages, and target use cases.

## Core Modules
- `src/simulate.py`
  - Parses CLI args (model, max turns, persona ID, etc.).
  - `_prepare_persona_context` loads persona from catalog, merges slot overrides into task.
  - `setup_logging` includes persona slug in run directory (`<scenario_key>__simulate_<persona>_<timestamp>`).
  - Runs `ConversationRunner`, writes `conversation.json`, transcripts, manifest line (`data/outputs/index.jsonl`).
- `src/runner.py`
  - Constructor accepts persona + task override, prepends default system greeting (`"Hi there! How can I help you today?"`).
  - `build_user_context` injects persona profile (name, age, hometown, occupation, bio, sample messages, contact info) and merged slots into the user-agent prompt.
  - `process_system_turn` handles ReAct-style micro-steps: detect tool calls, invoke `ToolAgent`, capture observations, continue until the “say” action.
  - Records structured steps in `turn_traces` and persona ID in result metadata.
- `src/agents.py`
  - `UserAgent.build_prompt` constructs OpenAI-style chat prompt combining base instructions, persona profile, task objective/slots, and injected behaviors; reinforces system prompt periodically.
  - `SystemAgent` and `ToolAgent` embed tool definitions and log inputs/outputs when debug mode is enabled.
- `src/scenario.py`
  - Loads `scenario.json`, pulling `task`, `personas` (catalog reference + entries), `user_agent`, and `tool_agent` blocks; resolves domain-level tools.
- `src/core.py`
  - `LLMClient` hides OpenAI SDK differences (new `openai.OpenAI` vs legacy `openai.ChatCompletion`).
- `prompts/user_agent/v1.txt`
  - Governs user simulation: adopt persona profile, mimic informal tone, rely on sample messages, complete with `[DONE_SUCCESS]`/`[DONE_FAILURE]`.

## Evaluation Suite (`src/eval/`)
- `syntax/`
  - `checker.py` orchestrates structural/tool validations; CLI `python -m eval.syntax.cli conversation.json`.
  - Error codes: `structure_invalid_block_format`, `structure_unexpected_text`, `tool_illegal_body_json`, etc.; output lists only failing turns.
- `success/`
  - `evaluate_success` uses `LLMClient` (OpenAI Responses API semantics) to judge success based on task description/slots, impossible flag, and transcript.
  - CLI: `python -m eval.success.cli conversation.json --model ...`.
- `run.py`
  - Combined CLI: `python -m eval.run conversation.json [--syntax-only --model ...]`; returns syntax summary + success verdict (cached LLM response).

## Data & Outputs
- **Scenarios**: include `task` (description, slots, optional `impossible` + `fallback_behavior`), `user_agent` behaviors, `tool_agent` behaviors, and `personas.entries` with optional slot overrides.
- **Personas**: fields `id`, `name`, `age`, `hometown`, `occupation`, `bio`, `sample_messages`, `email`, `phone`, `use_cases` (empty; to be populated). First five personas fully enriched.
- **Run artifacts** (`data/outputs/<scenario_key>__simulate_<persona>_<timestamp>/`):
  - `simulate.out` (JSON summary), `simulate.log`, `agent_flow.log` (if debug), transcripts, `conversation.json` (config contains persona + merged task), optional `turns.jsonl`.
  - Manifest `data/outputs/index.jsonl` logs run metadata (`scenario_key`, `run_id`, `success`, `persona_id`, paths).

## Current Behavior
- All scenarios now launch with the system greeting; user agents rely on persona sample messages to open the conversation.
- Persona slot overrides fully replace base slots when provided; success judge reads merged slots from `conversation.json`.
- `eval.success_criteria` removed from scenarios (obsolete); `user_persona` and `initial_message` fields cleared.

## Usage Examples
```bash
# Run simulator with persona
PYTHONPATH=src python src/simulate.py \
  data/domains/restaurant_booking/dine_in/rb_001 \
  --persona-id persona_005 --model gpt-4.1-mini --max-turns 4 --api-key $OPENAI_API_KEY

# Syntax check only
PYTHONPATH=src python -m eval.syntax.cli path/to/conversation.json --jsonl

# Success judge
PYTHONPATH=src python -m eval.success.cli path/to/conversation.json --model gpt-4.1-mini --api-key …

# Combined eval
PYTHONPATH=src python -m eval.run path/to/conversation.json --model gpt-4.1-mini
```

## Outstanding Work
- Persona catalog: remaining ~52 entries need names/demographics/sample messages and `use_cases` mapping.
- Scenario persona rollout across other domains (calendar, shopping, banking, travel); ensure greetings removed everywhere.
- Faithfulness checker (LLM judge for factual consistency) still to be designed/implemented.
- Optional: run loop iterating all personas, templated user-agent greetings, richer persona metadata in outputs.
- Cleanup: remove unused persona helper scripts if no longer needed.

