"""Tests for ToolManager."""

from nexus_agents.managers.tool_manager import ToolManager


class TestToolManager:
    def test_create_and_get(self, tool_manager: ToolManager):
        tool_id = tool_manager.create_tool("Search", "search", "Web search", config={"engine": "ddg"})
        tool = tool_manager.get_tool(tool_id)
        assert tool is not None
        assert tool.name == "Search"
        assert tool.config == {"engine": "ddg"}

    def test_update(self, tool_manager: ToolManager):
        tool_id = tool_manager.create_tool("Calc", "math", "Calculator")
        assert tool_manager.update_tool(tool_id, {"description": "Advanced calculator"}) is True

    def test_delete(self, tool_manager: ToolManager):
        tool_id = tool_manager.create_tool("Tmp", "tmp", "Temp tool")
        assert tool_manager.delete_tool(tool_id) is True
        assert tool_manager.get_tool(tool_id) is None

    def test_list_tools(self, tool_manager: ToolManager):
        tool_manager.create_tool("T1", "a", "d1")
        tool_manager.create_tool("T2", "b", "d2")
        assert len(tool_manager.list_tools()) == 2
