**Project Context & Original Objective**
- Preparing to scale multi-agent conversation simulator (`src/`, scenarios under `data/domains/`, personas in `data/personas/`).
- Need automated QA before generating large dataset of conversations.
- Simulator entry point: `src/simulate.py` (uses `ExampleScenario`, system/user/tool agents); outputs JSON artifacts & transcripts; scenarios live in `data/domains/<domain>/<use_case>/<scenario_id>/`.

---

### 1. Syntax Checker Implementation

**Expectations & Coverage**
- Enforce `<think>/<plan>/<action>` ordering, exactly one `<action>`, valid tool JSON and tool names, per-turn rules (one "say", say last, leniency on plan after first step removed).
- Failure categories: structure vs. tool.

**Key Files/Commands**
- Package: `src/eval/syntax/{models.py, parser.py, checks.py, checker.py, cli.py}`.
- CLI: `PYTHONPATH=src python -m eval.syntax.cli conversation.json [--jsonl]`.
- Outputs now list only failing turns with canonical error codes (`structure_invalid_block_format`, `structure_unexpected_text`, etc.).

### 2. LLM Success Judge

**Purpose**
- LLM judge decides if conversation fulfilled scenario task or handled impossible case gracefully.

**Implementation**
- Files: `src/eval/success/{models.py, reader.py, judge.py, cli.py}` (uses `LLMClient`).
- Prompt includes task description, slots, impossible flag/fallback, transcript with tool calls/results.
- CLI: `PYTHONPATH=src python -m eval.success.cli conversation.json --model gpt-4.1-mini --api-key ...`.
- Combined runner `src/eval/run.py`: runs syntax + (unless `--syntax-only`) success judge; writes JSON/JSONL summary.

**Schema**
- Scenarios now keep `task.description`, `task.slots`, optional `impossible` + `fallback_behavior`.
- `conversation.json` config now includes merged task persona overrides so judge sees correct slots.

### 3. Persona Integration

**Persona curation**
- Filtered PersonaHub sample to 57 broad personas (`data/personas/personahub_filtered.jsonl`).
- Catalog: `data/personas/catalog.json` with fields `id`, `name`, `age`, `hometown`, `occupation`, `bio`, `sample_messages` (3 casual snippets), `use_cases` (empty), `email`, `phone`.
- First 5 personas (Elena, Maya, Nikola, Sofía, Jordan) fully enriched (chatty sample messages, demographics).

**Scenario schema**
- `personas` block per scenario:
  ```json
  "personas": {
    "catalog": "data/personas/catalog.json",
    "entries": [
      {"id": "persona_002"},
      {"id": "persona_004"},
      {"id": "persona_005", "slot_overrides": {...}}
    ]
  }
  ```
- Slot overrides adjust persona-specific target slots while scenario retains base defaults.
- Removed legacy `user_persona` and `initial_message` fields.

**Simulator/Runner changes**
- `src/simulate.py`
  - `--persona-id`; loads persona catalog, merges overrides, writes persona-aware task metadata to output & manifest.
  - Output directory/ID includes persona slug (`simulate_persona_005_<timestamp>`).
- `src/runner.py`
  - Accepts persona + merged task context; injects persona profile (name, age, bio, sample messages, contact) into user-agent prompt.
  - System greeting defaults to "Hi there! How can I help you today?" and initiates conversation, replacing scenario initial messages.
  - Result metadata contains `persona_id`.
- `prompts/user_agent/v1.txt`: instructs simulated user to adopt persona profile, mirror tone, use sample messages.
- `src/agents.py`: user agent builds prompt with persona profile; no initial message shortcut.

**Catalog support**
- Added `use_cases` array to each persona for future mapping (currently empty).

### 4. Cleanup & Behavior Tweaks

- Removed `initial_message` and `user_persona` from all scenario files.
- Removed outdated `eval.success_criteria` blocks (LLM judge now authoritative).
- Slot overrides now propagate everywhere (context, outputs, success eval).

### 5. Current Usage Notes

- Run a scenario with persona:
  ```bash
  PYTHONPATH=src python src/simulate.py \
    data/domains/restaurant_booking/dine_in/rb_001 \
    --persona-id persona_005 \
    --model gpt-4.1-mini --max-turns 4 --api-key $OPENAI_API_KEY
  ```
- Use combined evaluator:
  ```bash
  PYTHONPATH=src python -m eval.run <conversation.json> --model gpt-4.1-mini [--syntax-only]
  ```

### 6. Outstanding Tasks

1. **Persona enrichment** – Remaining ~52 catalog entries need name/bio/sample_messages/use_cases.
2. **Scenario persona rollout** – Add personas + slot overrides to other domains/use cases; ensure greetings removed everywhere.
3. **Faithfulness checker** – Design LLM prompt/check metrics for hallucinations and tool-argument faithfulness.
4. **Optional enhancements** – Loop over personas per scenario, templated greetings, more expressive persona metadata in outputs.
5. **Cleanup** – Remove unused helper scripts in `data/personas/` if obsolete.

