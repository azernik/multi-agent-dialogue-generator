"""Core conversion functions for APIGen-MT dataset."""

import json
from typing import Dict, Any, List, Tuple

from core import LLMClient


def parse_tools(tools_str: str) -> Dict[str, Any]:
    """Parse tools string to dict."""
    try:
        return json.loads(tools_str)
    except json.JSONDecodeError:
        try:
            return eval(tools_str)
        except:
            return {}


def generate_think_plan(
    system_prompt: str,
    tools: Dict[str, Any],
    conversation_history: List[Dict[str, str]],
    original_response: str,
    is_first_turn_after_user: bool,
    openai_client: LLMClient
) -> Tuple[str, str]:
    """Generate <think> and <plan> blocks using OpenAI API.
    
    Returns:
        tuple: (think_block, plan_block) - both as strings
    """
    history_text = ""
    for turn in conversation_history:
        role = turn.get("role", "")
        content = turn.get("content", "")
        if role == "user":
            history_text += f"User: {content}\n"
        elif role == "tool":
            history_text += f"Tool Result: {content}\n"
    
    tools_json = json.dumps(tools, indent=2)
    
    system_content = f"""{system_prompt}

Available Tools:
{tools_json}

TASK: Generate <think> and <plan> blocks that explain an assistant's response.

<think> requirements:
- Explain what information the assistant currently has
- Explain what the user just said or what tool result was just received
- Explain what the assistant is deciding to do next and why
- Must be 2-3 sentences minimum
- Use the exact format: <think>...</think> (no backticks, no quotes)

<plan> requirements:
- Only include if this is the FIRST assistant response after a user message
- Numbered list of remaining steps to complete the user's goal
- Must include at least one item
- Describe what the assistant will do, including tool calls
- Use the exact format: <plan>...</plan>
"""

    user_content = f"""Conversation History:
---
{history_text}
---

Current Assistant Response (to explain):
{original_response}

Context:
- Is first turn after user message: {is_first_turn_after_user}
- Preceding turn type: {"user" if is_first_turn_after_user else "observation"}

Generate:
1. <think> block explaining the assistant's reasoning
2. <plan> block (ONLY if is_first_turn_after_user is True, otherwise omit it)

Output ONLY the <think> and <plan> blocks in the exact format shown above, nothing else. Do not use backticks or quotes around the tags."""

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content}
    ]
    
    response = openai_client.chat_completion(messages, temperature=0.3, max_tokens=500)
    
    think_block = ""
    plan_block = ""
    
    for tag_name in ["think", "redacted_reasoning"]:
        open_tag = f"<{tag_name}>"
        close_tag = f"</{tag_name}>"
        if open_tag in response:
            start = response.find(open_tag)
            end = response.find(close_tag, start)
            if end != -1:
                think_start = response.find(">", start) + 1
                think_block = response[think_start:end].strip()
                break
    
    if "<plan>" in response:
        start = response.find("<plan>")
        end = response.find("</plan>", start)
        if end != -1:
            plan_start = response.find(">", start) + 1
            plan_block = response[plan_start:end].strip()
    
    return think_block, plan_block


def convert_apigen_to_conversation_json(
    apigen_entry: Dict[str, Any],
    conversation_id: str,
    openai_client: LLMClient
) -> Dict[str, Any]:
    """Convert one APIGen-MT entry to conversation.json format."""
    conversations = apigen_entry.get("conversations", [])
    system_prompt = apigen_entry.get("system", "")
    tools_str = apigen_entry.get("tools", "{}")
    tools = parse_tools(tools_str)
    
    messages: List[Dict[str, Any]] = []
    turn_id = 1
    step_index = 1
    conversation_history: List[Dict[str, str]] = []
    last_turn_was_user = False
    
    i = 0
    while i < len(conversations):
        turn = conversations[i]
        from_type = turn.get("from")
        value = turn.get("value", "")
        
        if from_type == "human":
            messages.append({
                "turn_id": turn_id,
                "role": "user",
                "output_raw": value
            })
            conversation_history.append({"role": "user", "content": value})
            last_turn_was_user = True
            turn_id += 1
            step_index = 1
            
        elif from_type == "gpt":
            is_first = last_turn_was_user
            
            think, plan = generate_think_plan(
                system_prompt,
                tools,
                conversation_history,
                value,
                is_first,
                openai_client
            )
            
            output_parts = []
            if think:
                output_parts.append(f"<think>\n{think}\n</think>")
            if plan and is_first:
                output_parts.append(f"<plan>\n{plan}\n</plan>")
            
            output_parts.append(f'<action type="say">\n{value}\n</action>')
            output_raw = "\n".join(output_parts)
            
            observation_data = None
            action_structured = None
            
            if i + 1 < len(conversations):
                next_turn = conversations[i + 1]
                if next_turn.get("from") == "function_call":
                    func_call_str = next_turn.get("value", "{}")
                    try:
                        func_call = json.loads(func_call_str)
                        tool_name = func_call.get("name", "")
                        tool_args = func_call.get("arguments", {})
                        
                        action_structured = {
                            "type": "tool_call",
                            "name": tool_name,
                            "args": tool_args
                        }
                        
                        if i + 2 < len(conversations) and conversations[i + 2].get("from") == "observation":
                            obs_value = conversations[i + 2].get("value", "")
                            observation_data = {
                                "raw": obs_value,
                                "parsed": json.loads(obs_value) if obs_value.startswith("[") or obs_value.startswith("{") else obs_value
                            }
                            i += 2
                    except:
                        pass
            
            messages.append({
                "turn_id": turn_id - 1 if last_turn_was_user else turn_id,
                "role": "assistant",
                "steps": [{
                    "step_index": step_index,
                    "output_raw": output_raw,
                    "action_structured": action_structured,
                    "observation": observation_data
                }]
            })
            
            conversation_history.append({"role": "assistant", "content": output_raw})
            if observation_data:
                conversation_history.append({"role": "tool", "content": observation_data["raw"]})
            
            last_turn_was_user = False
            step_index += 1
        
        i += 1
    
    conversation_json = {
        "meta": {
            "conversation_id": conversation_id,
            "prompt_versions": {
                "system_agent": "v3"
            }
        },
        "config": {
            "scenario_name": f"apigen_{conversation_id}",
            "tools": tools
        },
        "messages": messages
    }
    
    return conversation_json
