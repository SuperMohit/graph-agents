"""Tests for LogManager."""

import pytest

from nexus_agents.managers.agent_manager import AgentManager
from nexus_agents.managers.log_manager import LogManager
from nexus_agents.models import AgentType, LogLevel
from tests.conftest import FakeNexusCore


@pytest.fixture
def setup(fake_core: FakeNexusCore):
    am = AgentManager(fake_core)
    lm = LogManager(fake_core)
    agent_id = am.create_agent("Logger", AgentType.ASSISTANT)
    return lm, agent_id


class TestLogManager:
    def test_log_from_agent(self, setup):
        lm, agent_id = setup
        log_id = lm.log(agent_id, "Agent", "Test message", LogLevel.INFO, {"key": "val"})
        assert log_id is not None

    def test_log_invalid_source(self, setup):
        lm, _ = setup
        with pytest.raises(ValueError):
            lm.log("id", "InvalidType", "msg")

    def test_log_nonexistent_source(self, setup):
        lm, _ = setup
        with pytest.raises(RuntimeError):
            lm.log("nonexistent", "Agent", "msg")

    def test_get_logs(self, setup):
        lm, agent_id = setup
        lm.log(agent_id, "Agent", "msg1", LogLevel.INFO)
        lm.log(agent_id, "Agent", "msg2", LogLevel.ERROR)
        logs = lm.get_logs()
        assert len(logs) == 2

    def test_search_logs(self, setup):
        lm, agent_id = setup
        lm.log(agent_id, "Agent", "connection failed", LogLevel.ERROR)
        lm.log(agent_id, "Agent", "all good", LogLevel.INFO)
        results = lm.search_logs("failed")
        assert len(results) >= 1
