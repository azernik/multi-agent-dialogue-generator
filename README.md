# Multi-Agent Dialogue Generator

## Setup

1. `pip install -r requirements.txt`
2. Create `.env` file and set `OPENAI_API_KEY=your_key_here`

## Quick Start

**Basic Usage:**
```bash
python src/simulate.py data/examples/ex1
```

**With Options:**
```bash
python src/simulate.py data/examples/ex1 \
  --model gpt-4o-mini \
  --max-turns 20 \
  --outputs-root data/outputs \
  --verbose
```

**Available Options:**
- `--model MODEL` - LLM model to use (default: gpt-4o-mini)
- `--max-turns N` - Maximum conversation turns (default: 20)
- `--api-key KEY` - OpenAI API key (or set OPENAI_API_KEY env var)
- `--verbose, -v` - Verbose console output
- `--system-agent-prompt FILE` - Custom system agent prompt file
- `--user-agent-prompt FILE` - Custom user agent prompt file  
- `--tool-agent-prompt FILE` - Custom tool agent prompt file

## How It Works

The simulator orchestrates conversations between three specialized AI agents to generate realistic user-system interactions with tool usage.

**The Agents:**
- **System Agent** - The main assistant that responds to users and makes tool calls
- **User Agent** - Simulates realistic user behavior based on scenario objectives  
- **Tool Agent** - Simulates external APIs and tools

**The Process:**
1. Load scenario (tools + user context) and agent prompts
2. User agent generates message → System agent responds (may call tools) → Tool agent processes calls → repeat
3. Maintains separate conversation histories for each agent's perspective
4. Terminates when user signals completion or max turns reached
5. Outputs JSON results + readable markdown transcripts for each agent

**Centralized Outputs (flattened):**
```
data/outputs/
├── index.jsonl                               # Global manifest (one line per run)
└── <scenario_key>__simulate_<timestamp>/     # e.g., restaurant_booking.dine_in.rb_003__simulate_20251018_163313
    ├── simulate.out                          # JSON results (with metadata per message)
    ├── simulate.log                          # Execution log
    ├── agent_flow.log                        # Agent input/output actions
    ├── system.md                             # System agent transcript
    ├── user.md                               # User agent transcript
    └── tool.md                               # Tool agent transcript
```

## Project Structure

**Domains and Scenarios:**
```
data/domains/
├── restaurant_booking/
│   ├── tools.json
│   └── dine_in/
│       └── rb_001/
│           └── scenario.json
└── calendar_assistant/
    └── schedule_meeting/
        └── ca_001/
            └── scenario.json
```

**Agent Prompts:**
```
prompts/
├── system_agent/v1.txt         # System agent instructions
├── user_agent/v1.txt           # User simulation instructions  
└── tool_agent/v1.txt           # Tool response instructions
```