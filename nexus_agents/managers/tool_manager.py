"""ToolManager - CRUD operations for Tool nodes in Neo4j."""

from __future__ import annotations

import uuid
from typing import Any

from nexus_agents.core import NexusCore
from nexus_agents.models import Tool


class ToolManager:
    """Manages Tool nodes in the graph database."""

    def __init__(self, core: NexusCore) -> None:
        self._core = core

    def create_tool(
        self,
        name: str,
        tool_type: str,
        description: str,
        function: str = "",
        config: dict[str, Any] | None = None,
    ) -> str:
        """Create a new Tool node and return its id."""
        tool = Tool(
            id=str(uuid.uuid4()),
            name=name,
            type=tool_type,
            description=description,
            function=function,
            config=config or {},
        )
        props = tool.to_dict()
        self._core.run_query(
            "CREATE (t:Tool $props)",
            {"props": props},
        )
        return tool.id

    def get_tool(self, tool_id: str) -> Tool | None:
        """Retrieve a Tool by id."""
        rows = self._core.run_query(
            "MATCH (t:Tool {id: $id}) RETURN t",
            {"id": tool_id},
        )
        if not rows:
            return None
        return Tool.from_dict(dict(rows[0]["t"]))

    def update_tool(self, tool_id: str, properties: dict[str, Any]) -> bool:
        """Update properties on an existing Tool node."""
        rows = self._core.run_query(
            "MATCH (t:Tool {id: $id}) SET t += $props RETURN t",
            {"id": tool_id, "props": properties},
        )
        return len(rows) > 0

    def delete_tool(self, tool_id: str) -> bool:
        """Delete a Tool and its relationships."""
        rows = self._core.run_query(
            "MATCH (t:Tool {id: $id}) DETACH DELETE t RETURN count(t) AS deleted",
            {"id": tool_id},
        )
        return rows[0]["deleted"] > 0 if rows else False

    def list_tools(self, filters: dict[str, Any] | None = None) -> list[Tool]:
        """List tools, optionally filtered by properties."""
        if filters:
            where_clauses = [f"t.{k} = ${k}" for k in filters]
            where = " AND ".join(where_clauses)
            query = f"MATCH (t:Tool) WHERE {where} RETURN t ORDER BY t.created_at DESC"
        else:
            query = "MATCH (t:Tool) RETURN t ORDER BY t.created_at DESC"
        rows = self._core.run_query(query, filters or {})
        return [Tool.from_dict(dict(row["t"])) for row in rows]
