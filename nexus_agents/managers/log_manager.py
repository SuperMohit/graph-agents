"""LogManager - Logging operations for the agent system."""

from __future__ import annotations

import uuid
from typing import Any

from nexus_agents.core import NexusCore
from nexus_agents.models import Log, LogLevel


class LogManager:
    """Manages Log nodes in the graph database."""

    def __init__(self, core: NexusCore) -> None:
        self._core = core

    def log(
        self,
        source_id: str,
        source_type: str,
        message: str,
        level: LogLevel = LogLevel.INFO,
        details: dict[str, Any] | None = None,
    ) -> str:
        """Create a log entry and link it to the source node.

        Creates a Log node and a GENERATED (from Agent) or PRODUCED (from Tool)
        relationship to the source.
        """
        log_entry = Log(
            id=str(uuid.uuid4()),
            message=message,
            level=level,
            details=details or {},
        )
        props = log_entry.to_dict()

        if source_type == "Agent":
            rel_type = "GENERATED"
        elif source_type == "Tool":
            rel_type = "PRODUCED"
        else:
            raise ValueError(f"source_type must be 'Agent' or 'Tool', got '{source_type}'")

        query = (
            f"MATCH (s:{source_type} {{id: $source_id}}) "
            f"CREATE (l:Log $props) "
            f"CREATE (s)-[:{rel_type}]->(l) "
            f"RETURN l.id AS log_id"
        )
        rows = self._core.run_query(query, {"source_id": source_id, "props": props})
        if not rows:
            raise RuntimeError(f"Source node {source_type}({source_id}) not found")
        return log_entry.id

    def get_logs(self, filters: dict[str, Any] | None = None) -> list[Log]:
        """Retrieve logs with optional filters (level, etc.)."""
        if filters:
            where_clauses = [f"l.{k} = ${k}" for k in filters]
            where = " AND ".join(where_clauses)
            query = f"MATCH (l:Log) WHERE {where} RETURN l ORDER BY l.timestamp DESC"
        else:
            query = "MATCH (l:Log) RETURN l ORDER BY l.timestamp DESC"
        rows = self._core.run_query(query, filters or {})
        return [Log.from_dict(dict(row["l"])) for row in rows]

    def search_logs(self, query: str) -> list[Log]:
        """Search logs by message content."""
        cypher = (
            "MATCH (l:Log) WHERE l.message CONTAINS $query "
            "RETURN l ORDER BY l.timestamp DESC"
        )
        rows = self._core.run_query(cypher, {"query": query})
        return [Log.from_dict(dict(row["l"])) for row in rows]
