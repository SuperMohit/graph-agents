"""NexusCore - Neo4j database driver wrapper and schema management."""

from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase, Session


class NexusCore:
    """Core database layer wrapping the Neo4j driver.

    Handles connection lifecycle, schema initialization, and query execution.
    """

    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j") -> None:
        self._uri = uri
        self._username = username
        self._password = password
        self._database = database
        self._driver = GraphDatabase.driver(uri, auth=(username, password))

    def initialize_schema(self) -> None:
        """Create constraints and indexes for the graph schema."""
        constraints = [
            "CREATE CONSTRAINT agent_id IF NOT EXISTS FOR (a:Agent) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT tool_id IF NOT EXISTS FOR (t:Tool) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT memory_id IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE",
            "CREATE CONSTRAINT log_id IF NOT EXISTS FOR (l:Log) REQUIRE l.id IS UNIQUE",
            "CREATE CONSTRAINT workflow_id IF NOT EXISTS FOR (w:WorkflowExecution) REQUIRE w.id IS UNIQUE",
        ]
        indexes = [
            "CREATE INDEX agent_name IF NOT EXISTS FOR (a:Agent) ON (a.name)",
            "CREATE INDEX agent_type IF NOT EXISTS FOR (a:Agent) ON (a.type)",
            "CREATE INDEX agent_status IF NOT EXISTS FOR (a:Agent) ON (a.status)",
            "CREATE INDEX tool_name IF NOT EXISTS FOR (t:Tool) ON (t.name)",
            "CREATE INDEX tool_type IF NOT EXISTS FOR (t:Tool) ON (t.type)",
            "CREATE INDEX memory_key IF NOT EXISTS FOR (m:Memory) ON (m.key)",
            "CREATE INDEX memory_type IF NOT EXISTS FOR (m:Memory) ON (m.memory_type)",
            "CREATE INDEX log_level IF NOT EXISTS FOR (l:Log) ON (l.level)",
            "CREATE INDEX log_timestamp IF NOT EXISTS FOR (l:Log) ON (l.timestamp)",
        ]
        with self.get_session() as session:
            for stmt in constraints + indexes:
                session.run(stmt)

    def close(self) -> None:
        """Close the Neo4j driver connection."""
        self._driver.close()

    def get_session(self, **kwargs: Any) -> Session:
        """Get a new Neo4j session."""
        return self._driver.session(database=self._database, **kwargs)

    def run_query(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a Cypher query and return results as a list of dicts."""
        with self.get_session() as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]
