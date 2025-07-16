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

## Project Structure

**Scenarios:**
```
data/examples/
├── ex1/
│   ├── scenario.json           # Tool definitions + user context
│   └── runs/                   # Simulation outputs
│       └── simulate_<timestamp>/
│           ├── simulate.out    # JSON results
│           ├── simulate.log    # Execution log
│           ├── agent_flow.log  # Agent input/output
│           ├── system.md       # System agent transcript
│           ├── user.md         # User agent transcript
│           └── tool.md         # Tool agent transcript
└── ex2/...
```

**Agent Prompts:**
```
data/system_prompts/
├── system_agent/v1.txt         # System agent instructions
├── user_agent/v1.txt           # User simulation instructions  
└── tool_agent/v1.txt           # Tool response instructions
``` 