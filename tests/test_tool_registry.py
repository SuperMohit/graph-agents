"""Tests for the ToolRegistry."""

import pytest

from nexus_agents.models import Tool
from nexus_agents.tool_registry import ToolRegistry


def _echo_tool(inp: dict) -> dict:
    return {"echo": inp}


def _add_tool(inp: dict) -> dict:
    return {"result": inp["a"] + inp["b"]}


class TestToolRegistry:
    def test_register_and_execute(self):
        reg = ToolRegistry()
        reg.register("echo", _echo_tool)
        result = reg.execute("echo", {"msg": "hi"})
        assert result == {"echo": {"msg": "hi"}}

    def test_execute_unregistered_raises(self):
        reg = ToolRegistry()
        with pytest.raises(KeyError, match="no_such_tool"):
            reg.execute("no_such_tool", {})

    def test_unregister(self):
        reg = ToolRegistry()
        reg.register("echo", _echo_tool)
        assert reg.unregister("echo") is True
        assert reg.unregister("echo") is False
        assert not reg.is_registered("echo")

    def test_list_registered(self):
        reg = ToolRegistry()
        reg.register("echo", _echo_tool)
        reg.register("add", _add_tool)
        assert set(reg.list_registered()) == {"echo", "add"}

    def test_build_tool_specs(self):
        reg = ToolRegistry()
        reg.register("echo", _echo_tool)
        tools = [
            Tool(id="1", name="echo", type="util", description="Echo input",
                 config={"input_schema": {"type": "object", "properties": {"msg": {"type": "string"}}}}),
            Tool(id="2", name="not_registered", type="util", description="Nope"),
        ]
        specs = reg.build_tool_specs(tools)
        assert len(specs) == 1
        assert specs[0]["name"] == "echo"
        assert specs[0]["description"] == "Echo input"
        assert "properties" in specs[0]["input_schema"]

    def test_build_tool_specs_default_schema(self):
        reg = ToolRegistry()
        reg.register("echo", _echo_tool)
        tools = [Tool(id="1", name="echo", type="util", description="Echo")]
        specs = reg.build_tool_specs(tools)
        assert specs[0]["input_schema"] == {"type": "object", "properties": {}}

    def test_execute_with_exception(self):
        def bad_tool(inp):
            raise RuntimeError("boom")
        reg = ToolRegistry()
        reg.register("bad", bad_tool)
        with pytest.raises(RuntimeError, match="boom"):
            reg.execute("bad", {})
