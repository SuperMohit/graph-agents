"""MemoryManager - CRUD and search operations for Memory nodes in Neo4j."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from nexus_agents.core import NexusCore
from nexus_agents.models import Memory, MemoryType


class MemoryManager:
    """Manages Memory nodes in the graph database."""

    def __init__(self, core: NexusCore) -> None:
        self._core = core

    def create_memory(
        self,
        key: str,
        value: Any,
        memory_type: MemoryType,
        priority: int = 0,
        expiration: datetime | None = None,
    ) -> str:
        """Create a new Memory node and return its id."""
        memory = Memory(
            id=str(uuid.uuid4()),
            key=key,
            value=value,
            memory_type=memory_type,
            priority=priority,
            expiration=expiration,
        )
        props = memory.to_dict()
        self._core.run_query(
            "CREATE (m:Memory $props)",
            {"props": props},
        )
        return memory.id

    def get_memory(self, memory_id: str) -> Memory | None:
        """Retrieve a Memory by id."""
        rows = self._core.run_query(
            "MATCH (m:Memory {id: $id}) RETURN m",
            {"id": memory_id},
        )
        if not rows:
            return None
        return Memory.from_dict(dict(rows[0]["m"]))

    def update_memory(self, memory_id: str, properties: dict[str, Any]) -> bool:
        """Update properties on an existing Memory node."""
        rows = self._core.run_query(
            "MATCH (m:Memory {id: $id}) SET m += $props RETURN m",
            {"id": memory_id, "props": properties},
        )
        return len(rows) > 0

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a Memory and its relationships."""
        rows = self._core.run_query(
            "MATCH (m:Memory {id: $id}) DETACH DELETE m RETURN count(m) AS deleted",
            {"id": memory_id},
        )
        return rows[0]["deleted"] > 0 if rows else False

    def search_memories(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
    ) -> list[Memory]:
        """Search memories by key or value content, with optional filters."""
        where_clauses = ["(m.key CONTAINS $query OR m.value CONTAINS $query)"]
        params: dict[str, Any] = {"query": query}
        if filters:
            for k, v in filters.items():
                where_clauses.append(f"m.{k} = ${k}")
                params[k] = v
        where = " AND ".join(where_clauses)
        cypher = f"MATCH (m:Memory) WHERE {where} RETURN m ORDER BY m.priority DESC, m.created_at DESC"
        rows = self._core.run_query(cypher, params)
        return [Memory.from_dict(dict(row["m"])) for row in rows]

    def connect_memories(self, from_id: str, to_id: str, strength: float = 1.0) -> bool:
        """Create a REFERENCES relationship between two Memory nodes."""
        rows = self._core.run_query(
            "MATCH (a:Memory {id: $from_id}), (b:Memory {id: $to_id}) "
            "CREATE (a)-[r:REFERENCES {strength: $strength}]->(b) "
            "RETURN type(r) AS rel",
            {"from_id": from_id, "to_id": to_id, "strength": strength},
        )
        return len(rows) > 0
