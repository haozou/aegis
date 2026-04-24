"""Unit tests for core types."""

from aegis.core.types import AgentConfig, StreamEvent, StreamEventType


def test_agent_config_defaults():
    config = AgentConfig()
    assert config.provider == "anthropic"
    assert config.model == "claude-sonnet-4-5"
    assert config.temperature == 0.7
    assert config.max_tokens == 4096
    assert config.system_prompt == ""
    assert config.enable_memory is True
    assert config.enable_skills is True
    assert config.tool_names is None
    assert config.max_tool_iterations == 50


def test_agent_config_custom():
    config = AgentConfig(
        provider="openai",
        model="gpt-4o",
        temperature=0.3,
        system_prompt="Be helpful.",
        tool_names=["bash", "web_fetch"],
    )
    assert config.provider == "openai"
    assert config.model == "gpt-4o"
    assert config.tool_names == ["bash", "web_fetch"]


def test_stream_event_text_delta():
    event = StreamEvent(type=StreamEventType.TEXT_DELTA, text="hello")
    d = event.to_ws_dict()
    assert d["type"] == "text_delta"
    assert d["text"] == "hello"
    assert "tool_name" not in d  # None fields excluded


def test_stream_event_done():
    event = StreamEvent(
        type=StreamEventType.DONE,
        message_id="msg_123",
        usage={"input": 10, "output": 20},
    )
    d = event.to_ws_dict()
    assert d["type"] == "done"
    assert d["message_id"] == "msg_123"
    assert d["usage"] == {"input": 10, "output": 20}


def test_stream_event_error():
    event = StreamEvent(type=StreamEventType.ERROR, error="something broke")
    d = event.to_ws_dict()
    assert d["type"] == "error"
    assert d["error"] == "something broke"


def test_stream_event_tool_start():
    event = StreamEvent(
        type=StreamEventType.TOOL_START,
        tool_name="bash",
        tool_id="tc_123",
        tool_input={"command": "ls"},
    )
    d = event.to_ws_dict()
    assert d["type"] == "tool_start"
    assert d["tool_name"] == "bash"
    assert d["tool_id"] == "tc_123"
    assert d["tool_input"] == {"command": "ls"}
