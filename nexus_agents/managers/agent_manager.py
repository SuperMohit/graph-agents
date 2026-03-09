"""AgentManager - CRUD operations for Agent nodes in Neo4j."""

from __future__ import annotations

import uuid
from typing import Any

from nexus_agents.core import NexusCore
from nexus_agents.models import Agent, AgentType


class AgentManager:
    """Manages Agent nodes in the graph database."""

    def __init__(self, core: NexusCore) -> None:
        self._core = core

    def create_agent(
        self,
        name: str,
        agent_type: AgentType,
        config: dict[str, Any] | None = None,
    ) -> str:
        """Create a new Agent node and return its id."""
        agent = Agent(
            id=str(uuid.uuid4()),
            name=name,
            type=agent_type,
            config=config or {},
        )
        props = agent.to_dict()
        self._core.run_query(
            "CREATE (a:Agent $props)",
            {"props": props},
        )
        return agent.id

    def get_agent(self, agent_id: str) -> Agent | None:
        """Retrieve an Agent by id."""
        rows = self._core.run_query(
            "MATCH (a:Agent {id: $id}) RETURN a",
            {"id": agent_id},
        )
        if not rows:
            return None
        return Agent.from_dict(dict(rows[0]["a"]))

    def update_agent(self, agent_id: str, properties: dict[str, Any]) -> bool:
        """Update properties on an existing Agent node."""
        rows = self._core.run_query(
            "MATCH (a:Agent {id: $id}) SET a += $props RETURN a",
            {"id": agent_id, "props": properties},
        )
        return len(rows) > 0

    def delete_agent(self, agent_id: str) -> bool:
        """Delete an Agent and its relationships."""
        rows = self._core.run_query(
            "MATCH (a:Agent {id: $id}) DETACH DELETE a RETURN count(a) AS deleted",
            {"id": agent_id},
        )
        return rows[0]["deleted"] > 0 if rows else False

    def list_agents(self, filters: dict[str, Any] | None = None) -> list[Agent]:
        """List agents, optionally filtered by properties."""
        if filters:
            where_clauses = [f"a.{k} = ${k}" for k in filters]
            where = " AND ".join(where_clauses)
            query = f"MATCH (a:Agent) WHERE {where} RETURN a ORDER BY a.created_at DESC"
        else:
            query = "MATCH (a:Agent) RETURN a ORDER BY a.created_at DESC"
        rows = self._core.run_query(query, filters or {})
        return [Agent.from_dict(dict(row["a"])) for row in rows]

    def connect_agents(
        self,
        from_id: str,
        to_id: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> bool:
        """Create a relationship between two agents.

        Supported relationship types: DELEGATES_TO, COMMUNICATES_WITH, TRANSITIONS_TO.
        """
        allowed = {"DELEGATES_TO", "COMMUNICATES_WITH", "TRANSITIONS_TO"}
        if relationship_type not in allowed:
            raise ValueError(f"relationship_type must be one of {allowed}")
        props_clause = " $props" if properties else ""
        query = (
            f"MATCH (a:Agent {{id: $from_id}}), (b:Agent {{id: $to_id}}) "
            f"CREATE (a)-[r:{relationship_type}{props_clause}]->(b) "
            f"RETURN type(r) AS rel"
        )
        params: dict[str, Any] = {"from_id": from_id, "to_id": to_id}
        if properties:
            params["props"] = properties
        rows = self._core.run_query(query, params)
        return len(rows) > 0
