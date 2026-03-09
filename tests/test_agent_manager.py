"""Tests for AgentManager."""

import pytest

from nexus_agents.managers.agent_manager import AgentManager
from nexus_agents.models import AgentType


class TestAgentManager:
    def test_create_and_get(self, agent_manager: AgentManager):
        agent_id = agent_manager.create_agent("TestBot", AgentType.ASSISTANT, {"model": "gpt-4"})
        assert agent_id is not None

        agent = agent_manager.get_agent(agent_id)
        assert agent is not None
        assert agent.name == "TestBot"
        assert agent.type == AgentType.ASSISTANT
        assert agent.config == {"model": "gpt-4"}

    def test_get_nonexistent(self, agent_manager: AgentManager):
        assert agent_manager.get_agent("nope") is None

    def test_update(self, agent_manager: AgentManager):
        agent_id = agent_manager.create_agent("Bot", AgentType.REASONING)
        result = agent_manager.update_agent(agent_id, {"status": "running"})
        assert result is True

        agent = agent_manager.get_agent(agent_id)
        assert agent.status == "running"

    def test_delete(self, agent_manager: AgentManager):
        agent_id = agent_manager.create_agent("ToDelete", AgentType.EXECUTOR)
        assert agent_manager.delete_agent(agent_id) is True
        assert agent_manager.get_agent(agent_id) is None

    def test_list_agents(self, agent_manager: AgentManager):
        agent_manager.create_agent("A1", AgentType.ASSISTANT)
        agent_manager.create_agent("A2", AgentType.ROUTER)
        agents = agent_manager.list_agents()
        assert len(agents) == 2

    def test_list_agents_filtered(self, agent_manager: AgentManager):
        agent_manager.create_agent("A1", AgentType.ASSISTANT)
        agent_manager.create_agent("A2", AgentType.ROUTER)
        agents = agent_manager.list_agents({"type": "assistant"})
        assert len(agents) == 1
        assert agents[0].name == "A1"

    def test_connect_agents(self, agent_manager: AgentManager):
        a1 = agent_manager.create_agent("A1", AgentType.PLANNER)
        a2 = agent_manager.create_agent("A2", AgentType.EXECUTOR)
        result = agent_manager.connect_agents(a1, a2, "DELEGATES_TO", {"priority": 1})
        assert result is True

    def test_connect_agents_invalid_rel(self, agent_manager: AgentManager):
        a1 = agent_manager.create_agent("A1", AgentType.PLANNER)
        a2 = agent_manager.create_agent("A2", AgentType.EXECUTOR)
        with pytest.raises(ValueError):
            agent_manager.connect_agents(a1, a2, "INVALID_REL")
