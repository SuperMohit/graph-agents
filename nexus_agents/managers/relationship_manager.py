"""RelationshipManager - Generic relationship operations across node types."""

from __future__ import annotations

from typing import Any

from nexus_agents.core import NexusCore

# Valid relationship types with their expected (from_label, to_label) pairs.
VALID_RELATIONSHIPS: dict[str, tuple[str, str]] = {
    "CAN_USE": ("Agent", "Tool"),
    "DELEGATES_TO": ("Agent", "Agent"),
    "GENERATED": ("Agent", "Log"),
    "STORES": ("Agent", "Memory"),
    "INFORMS": ("Memory", "Agent"),
    "PRODUCED": ("Tool", "Log"),
    "CONTRIBUTES_TO": ("Log", "Memory"),
    "COMMUNICATES_WITH": ("Agent", "Agent"),
    "REFERENCES": ("Memory", "Memory"),
    "TRANSITIONS_TO": ("Agent", "Agent"),
}


class RelationshipManager:
    """Manages relationships between nodes in the graph database."""

    def __init__(self, core: NexusCore) -> None:
        self._core = core

    def create_relationship(
        self,
        from_id: str,
        from_type: str,
        to_id: str,
        to_type: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> bool:
        """Create a relationship between two nodes."""
        if rel_type not in VALID_RELATIONSHIPS:
            raise ValueError(f"Unknown relationship type: {rel_type}. Must be one of {list(VALID_RELATIONSHIPS)}")

        props_clause = " $props" if properties else ""
        query = (
            f"MATCH (a:{from_type} {{id: $from_id}}), (b:{to_type} {{id: $to_id}}) "
            f"CREATE (a)-[r:{rel_type}{props_clause}]->(b) "
            f"RETURN type(r) AS rel"
        )
        params: dict[str, Any] = {"from_id": from_id, "to_id": to_id}
        if properties:
            params["props"] = properties
        rows = self._core.run_query(query, params)
        return len(rows) > 0

    def get_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
    ) -> dict[str, Any] | None:
        """Get a relationship and its properties."""
        if rel_type not in VALID_RELATIONSHIPS:
            raise ValueError(f"Unknown relationship type: {rel_type}")
        from_label, to_label = VALID_RELATIONSHIPS[rel_type]
        query = (
            f"MATCH (a:{from_label} {{id: $from_id}})-[r:{rel_type}]->(b:{to_label} {{id: $to_id}}) "
            f"RETURN type(r) AS type, properties(r) AS props, a.id AS from_id, b.id AS to_id"
        )
        rows = self._core.run_query(query, {"from_id": from_id, "to_id": to_id})
        if not rows:
            return None
        row = rows[0]
        return {
            "type": row["type"],
            "from_id": row["from_id"],
            "to_id": row["to_id"],
            "properties": row["props"],
        }

    def update_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        properties: dict[str, Any],
    ) -> bool:
        """Update properties on an existing relationship."""
        if rel_type not in VALID_RELATIONSHIPS:
            raise ValueError(f"Unknown relationship type: {rel_type}")
        from_label, to_label = VALID_RELATIONSHIPS[rel_type]
        query = (
            f"MATCH (a:{from_label} {{id: $from_id}})-[r:{rel_type}]->(b:{to_label} {{id: $to_id}}) "
            f"SET r += $props RETURN type(r) AS rel"
        )
        rows = self._core.run_query(query, {"from_id": from_id, "to_id": to_id, "props": properties})
        return len(rows) > 0

    def delete_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
    ) -> bool:
        """Delete a specific relationship between two nodes."""
        if rel_type not in VALID_RELATIONSHIPS:
            raise ValueError(f"Unknown relationship type: {rel_type}")
        from_label, to_label = VALID_RELATIONSHIPS[rel_type]
        query = (
            f"MATCH (a:{from_label} {{id: $from_id}})-[r:{rel_type}]->(b:{to_label} {{id: $to_id}}) "
            f"DELETE r RETURN count(r) AS deleted"
        )
        rows = self._core.run_query(query, {"from_id": from_id, "to_id": to_id})
        return rows[0]["deleted"] > 0 if rows else False

    def get_neighbors(
        self,
        node_id: str,
        rel_type: str | None = None,
        direction: str = "outgoing",
    ) -> list[dict[str, Any]]:
        """Get neighboring nodes connected by relationships.

        Args:
            node_id: The id of the source node.
            rel_type: Optional relationship type filter.
            direction: "outgoing", "incoming", or "both".
        """
        rel_pattern = f":{rel_type}" if rel_type else ""

        if direction == "outgoing":
            pattern = f"(n {{id: $node_id}})-[r{rel_pattern}]->(m)"
        elif direction == "incoming":
            pattern = f"(n {{id: $node_id}})<-[r{rel_pattern}]-(m)"
        else:
            pattern = f"(n {{id: $node_id}})-[r{rel_pattern}]-(m)"

        query = (
            f"MATCH {pattern} "
            f"RETURN m AS node, type(r) AS rel_type, properties(r) AS rel_props, labels(m) AS labels"
        )
        rows = self._core.run_query(query, {"node_id": node_id})
        return [
            {
                "node": dict(row["node"]),
                "rel_type": row["rel_type"],
                "rel_props": row["rel_props"],
                "labels": row["labels"],
            }
            for row in rows
        ]
