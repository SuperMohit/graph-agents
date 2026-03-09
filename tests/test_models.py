"""Tests for the data models."""

import json
from datetime import datetime

from nexus_agents.models import (
    Agent,
    AgentStatus,
    AgentType,
    Log,
    LogLevel,
    Memory,
    MemoryType,
    Tool,
    WorkflowExecution,
    WorkflowStatus,
)


class TestAgent:
    def test_to_dict_and_back(self):
        agent = Agent(
            id="a1",
            name="Test",
            type=AgentType.ASSISTANT,
            config={"model": "gpt-4"},
        )
        d = agent.to_dict()
        assert d["id"] == "a1"
        assert d["type"] == "assistant"
        assert json.loads(d["config"]) == {"model": "gpt-4"}

        restored = Agent.from_dict(d)
        assert restored.id == agent.id
        assert restored.type == AgentType.ASSISTANT
        assert restored.config == {"model": "gpt-4"}

    def test_from_dict_defaults(self):
        agent = Agent.from_dict({"id": "x", "name": "Y"})
        assert agent.type == AgentType.ASSISTANT
        assert agent.status == AgentStatus.IDLE.value


class TestTool:
    def test_roundtrip(self):
        tool = Tool(id="t1", name="Search", type="search", description="Web search", config={"engine": "ddg"})
        d = tool.to_dict()
        restored = Tool.from_dict(d)
        assert restored.name == "Search"
        assert restored.config == {"engine": "ddg"}


class TestMemory:
    def test_roundtrip(self):
        mem = Memory(id="m1", key="fact", value={"data": 42}, memory_type=MemoryType.LONG_TERM, priority=5)
        d = mem.to_dict()
        restored = Memory.from_dict(d)
        assert restored.value == {"data": 42}
        assert restored.memory_type == MemoryType.LONG_TERM
        assert restored.priority == 5

    def test_string_value(self):
        mem = Memory.from_dict({"id": "m2", "key": "k", "value": "hello", "memory_type": "short_term"})
        assert mem.value == "hello"


class TestLog:
    def test_roundtrip(self):
        log = Log(id="l1", message="test", level=LogLevel.WARNING, details={"code": 42})
        d = log.to_dict()
        restored = Log.from_dict(d)
        assert restored.level == LogLevel.WARNING
        assert restored.details == {"code": 42}


class TestWorkflowExecution:
    def test_roundtrip(self):
        wf = WorkflowExecution(
            id="w1",
            status=WorkflowStatus.RUNNING.value,
            input={"query": "test"},
            agent_sequence=["a1", "a2"],
        )
        d = wf.to_dict()
        restored = WorkflowExecution.from_dict(d)
        assert restored.agent_sequence == ["a1", "a2"]
        assert restored.status == "running"
