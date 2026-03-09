"""ToolRegistry - Maps tool names to callable implementations."""

from __future__ import annotations

import json
from typing import Any, Callable

from nexus_agents.models import Tool


# Type alias for a tool function: takes input dict, returns output dict.
ToolFunction = Callable[[dict[str, Any]], dict[str, Any]]


class ToolRegistry:
    """Registry that maps Tool graph nodes to actual callable implementations.

    Tools stored in Neo4j describe *what* a tool does (name, description,
    schema).  The registry holds the *how* — the Python callable that
    executes when an agent invokes the tool.

    Usage::

        registry = ToolRegistry()
        registry.register("web_search", my_search_function)

        result = registry.execute("web_search", {"query": "hello"})
    """

    def __init__(self) -> None:
        self._functions: dict[str, ToolFunction] = {}

    def register(self, tool_name: str, fn: ToolFunction) -> None:
        """Register a callable implementation for a tool name."""
        self._functions[tool_name] = fn

    def unregister(self, tool_name: str) -> bool:
        """Remove a tool implementation. Returns True if it existed."""
        return self._functions.pop(tool_name, None) is not None

    def is_registered(self, tool_name: str) -> bool:
        return tool_name in self._functions

    def list_registered(self) -> list[str]:
        return list(self._functions.keys())

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Execute a registered tool by name.

        Raises KeyError if the tool has no registered implementation.
        """
        fn = self._functions.get(tool_name)
        if fn is None:
            raise KeyError(f"No implementation registered for tool '{tool_name}'")
        return fn(tool_input)

    def build_tool_specs(self, tools: list[Tool]) -> list[dict[str, Any]]:
        """Build Anthropic-style tool specifications from Tool models.

        Only includes tools that have a registered implementation.
        Each Tool's ``config`` may contain an ``input_schema`` key that
        defines the JSON Schema for the tool's parameters.
        """
        specs = []
        for tool in tools:
            if not self.is_registered(tool.name):
                continue
            schema = tool.config.get("input_schema", {"type": "object", "properties": {}})
            if isinstance(schema, str):
                schema = json.loads(schema)
            specs.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": schema,
            })
        return specs
