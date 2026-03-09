"""NexusAgents - Main facade providing a unified interface to the system."""

from __future__ import annotations

from typing import Any

from nexus_agents.core import NexusCore
from nexus_agents.managers.agent_manager import AgentManager
from nexus_agents.managers.log_manager import LogManager
from nexus_agents.managers.memory_manager import MemoryManager
from nexus_agents.managers.relationship_manager import RelationshipManager
from nexus_agents.managers.tool_manager import ToolManager
from nexus_agents.orchestrator import Orchestrator
from nexus_agents.runner import AgentRunner, LLMProvider
from nexus_agents.tool_registry import ToolRegistry


class NexusAgents:
    """Facade class providing a simplified interface to the NexusAgents system.

    Usage::

        from nexus_agents.providers import AnthropicProvider

        nexus = NexusAgents(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="password",
            llm=AnthropicProvider(api_key="sk-..."),
        )
        nexus.initialize()

        agent_id = nexus.agents.create_agent("My Agent", AgentType.ASSISTANT, {
            "model": "claude-sonnet-4-20250514",
            "system_prompt": "You are a helpful assistant.",
        })

        # Register tool implementations
        nexus.tool_registry.register("web_search", my_search_fn)

        # Run a workflow
        wf = nexus.orchestrator.start_workflow({"task": "..."}, agent_id)
        result = nexus.orchestrator.execute_agent_chain(wf)

        nexus.close()
    """

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        database: str = "neo4j",
        llm: LLMProvider | None = None,
        tool_registry: ToolRegistry | None = None,
        max_tool_rounds: int = 10,
    ) -> None:
        self._core = NexusCore(uri, username, password, database)

        self.agent_manager = AgentManager(self._core)
        self.tool_manager = ToolManager(self._core)
        self.memory_manager = MemoryManager(self._core)
        self.relationship_manager = RelationshipManager(self._core)
        self.log_manager = LogManager(self._core)

        self._tool_registry = tool_registry or ToolRegistry()

        # Build runner only if an LLM provider is given
        runner: AgentRunner | None = None
        if llm is not None:
            runner = AgentRunner(
                llm=llm,
                tool_registry=self._tool_registry,
                max_tool_rounds=max_tool_rounds,
            )

        self.orchestrator = Orchestrator(
            core=self._core,
            agent_manager=self.agent_manager,
            tool_manager=self.tool_manager,
            memory_manager=self.memory_manager,
            relationship_manager=self.relationship_manager,
            log_manager=self.log_manager,
            runner=runner,
            tool_registry=self._tool_registry,
        )

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._tool_registry

    def initialize(self) -> None:
        """Initialize the database schema (constraints and indexes)."""
        self._core.initialize_schema()

    def close(self) -> None:
        """Close the database connection."""
        self._core.close()

    def __enter__(self) -> NexusAgents:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
