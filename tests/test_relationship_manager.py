"""Tests for RelationshipManager."""

import pytest

from nexus_agents.managers.agent_manager import AgentManager
from nexus_agents.managers.relationship_manager import RelationshipManager
from nexus_agents.managers.tool_manager import ToolManager
from nexus_agents.models import AgentType
from tests.conftest import FakeNexusCore


@pytest.fixture
def setup(fake_core: FakeNexusCore):
    am = AgentManager(fake_core)
    tm = ToolManager(fake_core)
    rm = RelationshipManager(fake_core)
    a1 = am.create_agent("Agent1", AgentType.ASSISTANT)
    a2 = am.create_agent("Agent2", AgentType.EXECUTOR)
    t1 = tm.create_tool("Tool1", "search", "A search tool")
    return rm, a1, a2, t1


class TestRelationshipManager:
    def test_create_and_get(self, setup):
        rm, a1, a2, t1 = setup
        assert rm.create_relationship(a1, "Agent", t1, "Tool", "CAN_USE", {"priority": 1}) is True
        rel = rm.get_relationship(a1, t1, "CAN_USE")
        assert rel is not None
        assert rel["type"] == "CAN_USE"

    def test_invalid_relationship_type(self, setup):
        rm, a1, a2, _ = setup
        with pytest.raises(ValueError):
            rm.create_relationship(a1, "Agent", a2, "Agent", "FAKE_REL")

    def test_delete_relationship(self, setup):
        rm, a1, a2, _ = setup
        rm.create_relationship(a1, "Agent", a2, "Agent", "DELEGATES_TO")
        assert rm.delete_relationship(a1, a2, "DELEGATES_TO") is True

    def test_get_neighbors(self, setup):
        rm, a1, a2, t1 = setup
        rm.create_relationship(a1, "Agent", t1, "Tool", "CAN_USE")
        rm.create_relationship(a1, "Agent", a2, "Agent", "TRANSITIONS_TO")
        neighbors = rm.get_neighbors(a1, direction="outgoing")
        assert len(neighbors) == 2

    def test_get_neighbors_filtered(self, setup):
        rm, a1, a2, t1 = setup
        rm.create_relationship(a1, "Agent", t1, "Tool", "CAN_USE")
        rm.create_relationship(a1, "Agent", a2, "Agent", "TRANSITIONS_TO")
        neighbors = rm.get_neighbors(a1, rel_type="CAN_USE", direction="outgoing")
        assert len(neighbors) == 1
        assert neighbors[0]["rel_type"] == "CAN_USE"
