"""Tests for MemoryManager."""

from nexus_agents.managers.memory_manager import MemoryManager
from nexus_agents.models import MemoryType


class TestMemoryManager:
    def test_create_and_get(self, memory_manager: MemoryManager):
        mid = memory_manager.create_memory("fact", "The sky is blue", MemoryType.LONG_TERM, priority=3)
        mem = memory_manager.get_memory(mid)
        assert mem is not None
        assert mem.key == "fact"
        assert mem.priority == 3

    def test_update(self, memory_manager: MemoryManager):
        mid = memory_manager.create_memory("k", "v", MemoryType.SHORT_TERM)
        assert memory_manager.update_memory(mid, {"priority": 10}) is True

    def test_delete(self, memory_manager: MemoryManager):
        mid = memory_manager.create_memory("k", "v", MemoryType.CONTEXT)
        assert memory_manager.delete_memory(mid) is True
        assert memory_manager.get_memory(mid) is None

    def test_search(self, memory_manager: MemoryManager):
        memory_manager.create_memory("color", "blue sky", MemoryType.LONG_TERM)
        memory_manager.create_memory("food", "pizza", MemoryType.SHORT_TERM)
        results = memory_manager.search_memories("sky")
        assert len(results) >= 1
        assert any(m.key == "color" for m in results)

    def test_connect_memories(self, memory_manager: MemoryManager):
        m1 = memory_manager.create_memory("a", "x", MemoryType.SEMANTIC)
        m2 = memory_manager.create_memory("b", "y", MemoryType.SEMANTIC)
        assert memory_manager.connect_memories(m1, m2, strength=0.8) is True
