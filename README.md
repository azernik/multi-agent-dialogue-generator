# Multi-Agent Dialogue Generator

## Setup

1. `pip install -r requirements.txt`
2. Create `.env` file and set `OPENAI_API_KEY=your_key_here`

## Data Structure

- `data/examples/` - Example scenarios (ex1, ex2, etc.)
- `data/system_prompts/` - Agent prompts (system_agent, user_agent, tool_agent)

## Running

```bash
python src/simulate.py data/examples/ex1
```

Optional flags: `--model gpt-4o-mini --max-turns 20 --verbose` 