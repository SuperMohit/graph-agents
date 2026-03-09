"""Tests for the Orchestrator."""

import pytest

from nexus_agents.managers.agent_manager import AgentManager
from nexus_agents.managers.log_manager import LogManager
from nexus_agents.managers.memory_manager import MemoryManager
from nexus_agents.managers.relationship_manager import RelationshipManager
from nexus_agents.managers.tool_manager import ToolManager
from nexus_agents.models import AgentType, WorkflowStatus
from nexus_agents.orchestrator import Orchestrator
from tests.conftest import FakeNexusCore


@pytest.fixture
def full_setup(fake_core: FakeNexusCore):
    am = AgentManager(fake_core)
    tm = ToolManager(fake_core)
    mm = MemoryManager(fake_core)
    rm = RelationshipManager(fake_core)
    lm = LogManager(fake_core)
    orch = Orchestrator(fake_core, am, tm, mm, rm, lm)
    return orch, am, tm, rm


class TestOrchestrator:
    def test_start_workflow(self, full_setup):
        orch, am, tm, rm = full_setup
        a1 = am.create_agent("Start", AgentType.PLANNER)
        wf = orch.start_workflow({"query": "test"}, a1)
        assert wf.status == WorkflowStatus.PENDING.value
        assert wf.agent_sequence == [a1]

    def test_start_workflow_bad_agent(self, full_setup):
        orch, am, tm, rm = full_setup
        with pytest.raises(ValueError):
            orch.start_workflow({}, "nonexistent")

    def test_single_agent_chain(self, full_setup):
        orch, am, tm, rm = full_setup
        a1 = am.create_agent("Solo", AgentType.ASSISTANT)
        wf = orch.start_workflow({"data": "hello"}, a1)
        result = orch.execute_agent_chain(wf)
        assert result["steps"][0]["agent_name"] == "Solo"
        assert wf.status == WorkflowStatus.COMPLETED.value

    def test_multi_agent_chain(self, full_setup):
        orch, am, tm, rm = full_setup
        a1 = am.create_agent("Planner", AgentType.PLANNER)
        a2 = am.create_agent("Executor", AgentType.EXECUTOR)
        a3 = am.create_agent("Critic", AgentType.CRITIC)

        rm.create_relationship(a1, "Agent", a2, "Agent", "TRANSITIONS_TO")
        rm.create_relationship(a2, "Agent", a3, "Agent", "TRANSITIONS_TO")

        wf = orch.start_workflow({"task": "build feature"}, a1)
        result = orch.execute_agent_chain(wf)

        assert len(result["steps"]) == 3
        assert result["steps"][0]["agent_name"] == "Planner"
        assert result["steps"][1]["agent_name"] == "Executor"
        assert result["steps"][2]["agent_name"] == "Critic"

    def test_conditional_transition(self, full_setup):
        orch, am, tm, rm = full_setup
        router = am.create_agent("Router", AgentType.ROUTER)
        research = am.create_agent("Research", AgentType.ASSISTANT)
        code = am.create_agent("Code", AgentType.EXECUTOR)

        rm.create_relationship(
            router, "Agent", research, "Agent", "TRANSITIONS_TO",
            {"condition": "type=research"},
        )
        rm.create_relationship(
            router, "Agent", code, "Agent", "TRANSITIONS_TO",
            {"condition": "type=code"},
        )

        next_id = orch.get_next_agent(router, {"type": "research"})
        assert next_id == research

    def test_visualize_workflow(self, full_setup):
        orch, am, tm, rm = full_setup
        a1 = am.create_agent("Agent", AgentType.ASSISTANT)
        wf = orch.start_workflow({"q": "test"}, a1)
        orch.execute_agent_chain(wf)
        viz = orch.visualize_workflow(wf.id)
        assert "completed" in viz.lower()

    def test_evaluate_condition(self):
        assert Orchestrator._evaluate_condition("status=success", {"status": "success"}) is True
        assert Orchestrator._evaluate_condition("status=success", {"status": "fail"}) is False
        assert Orchestrator._evaluate_condition("key", {"key": 1}) is True
        assert Orchestrator._evaluate_condition("key", {}) is False

    def test_agent_with_tools_in_chain(self, full_setup):
        orch, am, tm, rm = full_setup
        a1 = am.create_agent("Agent", AgentType.ASSISTANT)
        t1 = tm.create_tool("Search", "search", "Web search")
        rm.create_relationship(a1, "Agent", t1, "Tool", "CAN_USE", {"priority": 1})

        wf = orch.start_workflow({"q": "test"}, a1)
        result = orch.execute_agent_chain(wf)
        assert t1 in result["steps"][0]["available_tools"]
