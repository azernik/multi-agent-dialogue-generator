"""Minimal tests for HuggingFace format conversion functions."""

from core import Message, MessageRole, convert_messages_to_hf_format, build_hf_prompt


def test_convert_messages_basic():
    """Test basic message conversion."""
    messages = [
        Message(MessageRole.USER, "Hello"),
        Message(MessageRole.ASSISTANT, "<think>Thinking...</think>\n<action type=\"say\">Hi there!</action>"),
        Message(MessageRole.TOOL, '{"result": "ok"}')
    ]
    
    result = convert_messages_to_hf_format(messages)
    
    assert "<user> Hello </user>" in result
    assert "<think>Thinking...</think>" in result
    assert "<obs> {\"result\": \"ok\"} </obs>" in result
    assert result.count("\n\n") == 2  # Two separators between three blocks


def test_convert_messages_empty():
    """Test conversion with empty message list."""
    result = convert_messages_to_hf_format([])
    assert result == ""


def test_build_prompt_basic():
    """Test prompt building with basic inputs."""
    system_prompt = "You are helpful"
    tools = {"tool1": {"description": "A tool"}}
    history = "<user> Hello </user>"
    
    prompt = build_hf_prompt(system_prompt, tools, history)
    
    assert "<system>" in prompt
    assert "You are helpful" in prompt
    assert "Available Tools:" in prompt
    assert '"tool1"' in prompt
    assert history in prompt


def test_build_prompt_empty_tools():
    """Test prompt building with empty tools."""
    system_prompt = "You are helpful"
    tools = {}
    history = "<user> Hello </user>"
    
    prompt = build_hf_prompt(system_prompt, tools, history)
    
    assert "<system>" in prompt
    assert "Available Tools:" in prompt
    assert history in prompt


def test_convert_messages_plain_text_assistant():
    """Test that plain text assistant messages are wrapped in structured format."""
    messages = [
        Message(MessageRole.ASSISTANT, "Hi there! How can I help you today?")
    ]
    
    result = convert_messages_to_hf_format(messages)
    
    assert "<action type=\"say\">" in result
    assert "Hi there! How can I help you today?" in result
    assert "</action>" in result
    # Should NOT have think/reasoning for simple plain text
    assert "<think>" not in result
    assert "<think>" not in result


if __name__ == "__main__":
    test_convert_messages_basic()
    print("✓ test_convert_messages_basic passed")
    
    test_convert_messages_empty()
    print("✓ test_convert_messages_empty passed")
    
    test_build_prompt_basic()
    print("✓ test_build_prompt_basic passed")
    
    test_build_prompt_empty_tools()
    print("✓ test_build_prompt_empty_tools passed")
    
    test_convert_messages_plain_text_assistant()
    print("✓ test_convert_messages_plain_text_assistant passed")
    
    print("\nAll tests passed!")

