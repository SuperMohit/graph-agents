"""Integration tests: Orchestrator + AgentRunner executing real agent chains."""

import pytest

from nexus_agents.managers.agent_manager import AgentManager
from nexus_agents.managers.log_manager import LogManager
from nexus_agents.managers.memory_manager import MemoryManager
from nexus_agents.managers.relationship_manager import RelationshipManager
from nexus_agents.managers.tool_manager import ToolManager
from nexus_agents.models import AgentType, MemoryType, RunStatus, WorkflowStatus
from nexus_agents.orchestrator import Orchestrator
from nexus_agents.runner import AgentRunner
from nexus_agents.tool_registry import ToolRegistry
from tests.conftest import FakeNexusCore


class FakeLLM:
    """Deterministic LLM that returns responses based on call count."""

    def __init__(self, responses=None):
        self._responses = list(responses or [])
        self._call_count = 0
        self.calls = []

    def chat(self, messages, model=None, system=None, tools=None,
             temperature=None, max_tokens=None):
        self.calls.append({
            "messages": messages,
            "model": model,
            "system": system,
            "tools": tools,
        })
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
        else:
            resp = {"content": f"Agent response #{self._call_count}", "stop_reason": "end_turn"}
        self._call_count += 1
        return resp


def _build_system(fake_core, llm, registry=None):
    """Wire up the full system with a fake core and fake LLM."""
    am = AgentManager(fake_core)
    tm = ToolManager(fake_core)
    mm = MemoryManager(fake_core)
    rm = RelationshipManager(fake_core)
    lm = LogManager(fake_core)
    reg = registry or ToolRegistry()
    runner = AgentRunner(llm=llm, tool_registry=reg)
    orch = Orchestrator(fake_core, am, tm, mm, rm, lm, runner=runner, tool_registry=reg)
    return orch, am, tm, mm, rm


class TestAgentChainExecution:
    def test_single_agent_runs(self, fake_core):
        llm = FakeLLM([{
            "content": "I've analyzed the task.",
            "stop_reason": "end_turn",
            "model": "test",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }])
        orch, am, tm, mm, rm = _build_system(fake_core, llm)

        agent_id = am.create_agent("Analyzer", AgentType.ASSISTANT, {
            "model": "test-model",
            "system_prompt": "Analyze tasks.",
        })

        wf = orch.start_workflow({"message": "Analyze this data"}, agent_id)
        result = orch.execute_agent_chain(wf)

        assert wf.status == WorkflowStatus.COMPLETED.value
        assert len(result["steps"]) == 1
        step = result["steps"][0]
        assert step["status"] == RunStatus.COMPLETED.value
        assert step["output"]["response"] == "I've analyzed the task."
        assert "run_id" in step
        assert step["duration_ms"] > 0

    def test_multi_agent_chain_passes_output(self, fake_core):
        """Output from agent A becomes input to agent B."""
        llm = FakeLLM([
            {"content": "Plan: Step 1, Step 2", "stop_reason": "end_turn"},
            {"content": "Executed all steps.", "stop_reason": "end_turn"},
            {"content": "Looks good, approved.", "stop_reason": "end_turn"},
        ])
        orch, am, tm, mm, rm = _build_system(fake_core, llm)

        planner = am.create_agent("Planner", AgentType.PLANNER, {"system_prompt": "Plan tasks."})
        executor = am.create_agent("Executor", AgentType.EXECUTOR, {"system_prompt": "Execute."})
        critic = am.create_agent("Critic", AgentType.CRITIC, {"system_prompt": "Review."})

        rm.create_relationship(planner, "Agent", executor, "Agent", "TRANSITIONS_TO")
        rm.create_relationship(executor, "Agent", critic, "Agent", "TRANSITIONS_TO")

        wf = orch.start_workflow({"message": "Build a feature"}, planner)
        result = orch.execute_agent_chain(wf)

        assert len(result["steps"]) == 3
        assert result["steps"][0]["output"]["response"] == "Plan: Step 1, Step 2"
        assert result["steps"][1]["output"]["response"] == "Executed all steps."
        assert result["steps"][2]["output"]["response"] == "Looks good, approved."

        # Verify the output of each agent was passed as input to the next
        # Agent 2 should have received agent 1's output
        second_call_messages = llm.calls[1]["messages"]
        user_msg = second_call_messages[-1]["content"]
        # The output dict becomes the input, converted via str()
        assert "response" in user_msg or "Plan" in user_msg

    def test_agent_with_tool_use(self, fake_core):
        """Agent calls a tool, gets result, and produces final output."""
        llm = FakeLLM([
            {
                "content": [{
                    "type": "tool_use",
                    "id": "call_1",
                    "name": "web_search",
                    "input": {"query": "Neo4j best practices"},
                }],
                "stop_reason": "tool_use",
            },
            {
                "content": "Based on the search: use indexes.",
                "stop_reason": "end_turn",
            },
        ])
        registry = ToolRegistry()
        registry.register("web_search", lambda inp: {
            "results": [{"title": "Neo4j Guide", "url": "https://example.com"}]
        })

        orch, am, tm, mm, rm = _build_system(fake_core, llm, registry)

        agent_id = am.create_agent("Researcher", AgentType.ASSISTANT)
        tool_id = tm.create_tool("web_search", "search", "Search the web", config={
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
        })
        rm.create_relationship(agent_id, "Agent", tool_id, "Tool", "CAN_USE")

        wf = orch.start_workflow({"message": "How to use Neo4j?"}, agent_id)
        result = orch.execute_agent_chain(wf)

        step = result["steps"][0]
        assert step["status"] == RunStatus.COMPLETED.value
        assert len(step["tool_calls"]) == 1
        assert step["tool_calls"][0]["name"] == "web_search"
        assert "Neo4j Guide" in str(step["tool_calls"][0]["output"])
        assert "search" in step["output"]["response"].lower() or "index" in step["output"]["response"].lower()

    def test_agent_with_memory(self, fake_core):
        """Agent receives memories as context."""
        llm = FakeLLM([{
            "content": "Hello Alice! I know you prefer dark mode.",
            "stop_reason": "end_turn",
        }])
        orch, am, tm, mm, rm = _build_system(fake_core, llm)

        agent_id = am.create_agent("Greeter", AgentType.ASSISTANT)
        mem_id = mm.create_memory("user_name", "Alice", MemoryType.LONG_TERM)

        # Memory INFORMS the agent
        rm.create_relationship(mem_id, "Memory", agent_id, "Agent", "INFORMS")

        wf = orch.start_workflow({"message": "Hi there!"}, agent_id)
        result = orch.execute_agent_chain(wf)

        # Verify memory was injected into the LLM call
        first_call = llm.calls[0]["messages"]
        memory_msg = first_call[0]["content"]
        assert "Alice" in memory_msg

    def test_conditional_routing_with_execution(self, fake_core):
        """Router agent's output determines which branch to follow."""
        llm = FakeLLM([
            # Router responds
            {"content": "This is a research question.", "stop_reason": "end_turn"},
            # Research agent responds
            {"content": "Research findings: ...", "stop_reason": "end_turn"},
        ])
        orch, am, tm, mm, rm = _build_system(fake_core, llm)

        router = am.create_agent("Router", AgentType.ROUTER)
        researcher = am.create_agent("Researcher", AgentType.ASSISTANT)
        coder = am.create_agent("Coder", AgentType.EXECUTOR)

        # Unconditional fallback goes to researcher
        rm.create_relationship(router, "Agent", researcher, "Agent", "TRANSITIONS_TO")
        rm.create_relationship(router, "Agent", coder, "Agent", "TRANSITIONS_TO",
                               {"condition": "type=code"})

        wf = orch.start_workflow({"message": "What is graph theory?"}, router)
        result = orch.execute_agent_chain(wf)

        assert len(result["steps"]) == 2
        assert result["steps"][0]["agent_name"] == "Router"
        assert result["steps"][1]["agent_name"] == "Researcher"

    def test_failed_agent_aborts_workflow(self, fake_core):
        """If an agent fails (LLM error), the workflow is marked failed."""
        class FailingLLM:
            def chat(self, **kwargs):
                raise RuntimeError("API error")

        orch, am, tm, mm, rm = _build_system(fake_core, FailingLLM())

        a1 = am.create_agent("Failer", AgentType.ASSISTANT)
        a2 = am.create_agent("Unreachable", AgentType.ASSISTANT)
        rm.create_relationship(a1, "Agent", a2, "Agent", "TRANSITIONS_TO")

        wf = orch.start_workflow({"message": "test"}, a1)
        result = orch.execute_agent_chain(wf)

        assert wf.status == WorkflowStatus.FAILED.value
        assert "API error" in result["error"]
        assert len(result["steps"]) == 1

    def test_agent_run_persisted_to_graph(self, fake_core):
        llm = FakeLLM([{"content": "done", "stop_reason": "end_turn"}])
        orch, am, tm, mm, rm = _build_system(fake_core, llm)

        agent_id = am.create_agent("Worker", AgentType.ASSISTANT)
        wf = orch.start_workflow({"message": "work"}, agent_id)
        orch.execute_agent_chain(wf)

        # Check that an AgentRun node was created in the graph
        runs = fake_core._graph.find_nodes("AgentRun")
        assert len(runs) == 1
        assert runs[0]["agent_id"] == agent_id
        assert runs[0]["workflow_id"] == wf.id

    def test_backward_compat_no_runner(self, fake_core):
        """Without a runner, orchestrator does metadata-only walk (backward compat)."""
        am = AgentManager(fake_core)
        tm = ToolManager(fake_core)
        mm = MemoryManager(fake_core)
        rm = RelationshipManager(fake_core)
        lm = LogManager(fake_core)
        orch = Orchestrator(fake_core, am, tm, mm, rm, lm)  # no runner

        a1 = am.create_agent("Solo", AgentType.ASSISTANT)
        wf = orch.start_workflow({"data": "hello"}, a1)
        result = orch.execute_agent_chain(wf)

        assert result["steps"][0]["agent_name"] == "Solo"
        assert "run_id" not in result["steps"][0]
        assert wf.status == WorkflowStatus.COMPLETED.value
