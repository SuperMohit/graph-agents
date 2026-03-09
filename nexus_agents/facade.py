"""NexusAgents - Main facade providing a unified interface to the system."""

from __future__ import annotations

from nexus_agents.core import NexusCore
from nexus_agents.managers.agent_manager import AgentManager
from nexus_agents.managers.log_manager import LogManager
from nexus_agents.managers.memory_manager import MemoryManager
from nexus_agents.managers.relationship_manager import RelationshipManager
from nexus_agents.managers.tool_manager import ToolManager
from nexus_agents.orchestrator import Orchestrator


class NexusAgents:
    """Facade class providing a simplified interface to the NexusAgents system.

    Usage::

        nexus = NexusAgents(uri="bolt://localhost:7687", username="neo4j", password="password")
        nexus.initialize()

        agent_id = nexus.agent_manager.create_agent("My Agent", AgentType.ASSISTANT)
        # ... use managers and orchestrator ...

        nexus.close()
    """

    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j") -> None:
        self._core = NexusCore(uri, username, password, database)

        self.agent_manager = AgentManager(self._core)
        self.tool_manager = ToolManager(self._core)
        self.memory_manager = MemoryManager(self._core)
        self.relationship_manager = RelationshipManager(self._core)
        self.log_manager = LogManager(self._core)
        self.orchestrator = Orchestrator(
            core=self._core,
            agent_manager=self.agent_manager,
            tool_manager=self.tool_manager,
            memory_manager=self.memory_manager,
            relationship_manager=self.relationship_manager,
            log_manager=self.log_manager,
        )

    def initialize(self) -> None:
        """Initialize the database schema (constraints and indexes)."""
        self._core.initialize_schema()

    def close(self) -> None:
        """Close the database connection."""
        self._core.close()

    def __enter__(self) -> NexusAgents:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        self.close()
