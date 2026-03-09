"""Shared test fixtures using an in-memory graph store that mimics Neo4j."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import pytest

from nexus_agents.core import NexusCore
from nexus_agents.facade import NexusAgents
from nexus_agents.managers.agent_manager import AgentManager
from nexus_agents.managers.log_manager import LogManager
from nexus_agents.managers.memory_manager import MemoryManager
from nexus_agents.managers.relationship_manager import RelationshipManager
from nexus_agents.managers.tool_manager import ToolManager
from nexus_agents.orchestrator import Orchestrator


class FakeGraph:
    """Minimal in-memory graph store that interprets a subset of Cypher.

    This is intentionally simple -- it covers the patterns used by the
    NexusAgents managers so we can test without a running Neo4j instance.
    """

    def __init__(self) -> None:
        # label -> list[dict]
        self.nodes: dict[str, list[dict[str, Any]]] = {}
        # list of (from_label, from_id, rel_type, to_label, to_id, props)
        self.relationships: list[tuple[str, str, str, str, str, dict[str, Any]]] = []

    # -- Node helpers ----------------------------------------------------------

    def create_node(self, label: str, props: dict[str, Any]) -> dict[str, Any]:
        self.nodes.setdefault(label, [])
        self.nodes[label].append(dict(props))
        return props

    def find_node(self, label: str, **match: Any) -> dict[str, Any] | None:
        for n in self.nodes.get(label, []):
            if all(n.get(k) == v for k, v in match.items()):
                return n
        return None

    def find_nodes(self, label: str, **match: Any) -> list[dict[str, Any]]:
        results = []
        for n in self.nodes.get(label, []):
            if all(n.get(k) == v for k, v in match.items()):
                results.append(n)
        return results

    def update_node(self, label: str, node_id: str, props: dict[str, Any]) -> dict[str, Any] | None:
        node = self.find_node(label, id=node_id)
        if node is not None:
            node.update(props)
        return node

    def delete_node(self, label: str, node_id: str) -> bool:
        nodes = self.nodes.get(label, [])
        for i, n in enumerate(nodes):
            if n.get("id") == node_id:
                nodes.pop(i)
                # Remove related relationships
                self.relationships = [
                    r for r in self.relationships if r[1] != node_id and r[4] != node_id
                ]
                return True
        return False

    # -- Relationship helpers --------------------------------------------------

    def create_rel(
        self,
        from_label: str,
        from_id: str,
        rel_type: str,
        to_label: str,
        to_id: str,
        props: dict[str, Any] | None = None,
    ) -> bool:
        self.relationships.append(
            (from_label, from_id, rel_type, to_label, to_id, props or {})
        )
        return True

    def find_rel(
        self,
        from_id: str,
        rel_type: str,
        to_id: str,
    ) -> tuple | None:
        for r in self.relationships:
            if r[1] == from_id and r[2] == rel_type and r[4] == to_id:
                return r
        return None

    def get_neighbors(
        self,
        node_id: str,
        rel_type: str | None = None,
        direction: str = "outgoing",
    ) -> list[dict[str, Any]]:
        results = []
        for fl, fid, rt, tl, tid, rp in self.relationships:
            if direction in ("outgoing", "both") and fid == node_id:
                if rel_type and rt != rel_type:
                    continue
                target = self.find_node(tl, id=tid)
                if target:
                    results.append({
                        "node": dict(target),
                        "rel_type": rt,
                        "rel_props": rp,
                        "labels": [tl],
                    })
            if direction in ("incoming", "both") and tid == node_id:
                if rel_type and rt != rel_type:
                    continue
                source = self.find_node(fl, id=fid)
                if source:
                    results.append({
                        "node": dict(source),
                        "rel_type": rt,
                        "rel_props": rp,
                        "labels": [fl],
                    })
        return results


class FakeNexusCore(NexusCore):
    """A NexusCore replacement backed by FakeGraph instead of Neo4j."""

    def __init__(self) -> None:
        # Skip parent __init__ which connects to Neo4j
        self._graph = FakeGraph()

    def initialize_schema(self) -> None:
        pass  # no-op

    def close(self) -> None:
        pass

    def get_session(self, **kwargs: Any):  # noqa: ANN201
        raise NotImplementedError("FakeNexusCore doesn't provide sessions")

    def run_query(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Interpret a small subset of Cypher used by the managers."""
        params = params or {}
        return self._interpret(query, params)

    # -- Cypher interpreter (minimal) ------------------------------------------

    def _interpret(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        q = query.strip()

        # CREATE (x:Label $props)
        m = re.match(r"CREATE\s+\(\w+:(\w+)\s+\$(\w+)\)", q)
        if m:
            label, param_key = m.group(1), m.group(2)
            props = params[param_key]
            self._graph.create_node(label, props)
            return []

        # MATCH (a:Label {id: $id}) RETURN a
        m = re.match(r"MATCH\s+\(\w+:(\w+)\s+\{id:\s*\$(\w+)\}\)\s+RETURN\s+(\w+)\s*$", q)
        if m:
            label, param_key, alias = m.group(1), m.group(2), m.group(3)
            node = self._graph.find_node(label, id=params[param_key])
            if node:
                return [{alias: dict(node)}]
            return []

        # MATCH (a:Label {id: $id}) SET a += $props RETURN a
        m = re.match(
            r"MATCH\s+\(\w+:(\w+)\s+\{id:\s*\$(\w+)\}\)\s+SET\s+\w+\s*\+=\s*\$(\w+)\s+RETURN\s+(\w+)",
            q,
        )
        if m:
            label, id_key, props_key, alias = m.groups()
            node = self._graph.update_node(label, params[id_key], params[props_key])
            if node:
                return [{alias: dict(node)}]
            return []

        # MATCH (w:WorkflowExecution {id: $id}) SET w += $props  (no RETURN)
        m = re.match(
            r"MATCH\s+\(\w+:(\w+)\s+\{id:\s*\$(\w+)\}\)\s+SET\s+\w+\s*\+=\s*\$(\w+)\s*$",
            q,
        )
        if m:
            label, id_key, props_key = m.groups()
            self._graph.update_node(label, params[id_key], params[props_key])
            return []

        # MATCH (a:Label {id: $id}) DETACH DELETE a RETURN count(a) AS deleted
        m = re.match(
            r"MATCH\s+\(\w+:(\w+)\s+\{id:\s*\$(\w+)\}\)\s+DETACH DELETE\s+\w+\s+RETURN\s+count\(\w+\)\s+AS\s+(\w+)",
            q,
        )
        if m:
            label, id_key, alias = m.groups()
            deleted = self._graph.delete_node(label, params[id_key])
            return [{alias: 1 if deleted else 0}]

        # MATCH (a:Label) RETURN a ...  (with optional WHERE)
        m = re.match(r"MATCH\s+\(\w+:(\w+)\)\s+(WHERE\s+(.+?)\s+)?RETURN\s+(\w+)", q)
        if m:
            label = m.group(1)
            where_clause = m.group(3)
            alias = m.group(4)
            filters = {}
            if where_clause:
                # parse simple AND-joined equality and CONTAINS conditions
                conditions = re.split(r"\s+AND\s+", where_clause)
                contains_key = None
                contains_val = None
                for cond in conditions:
                    cond = cond.strip()
                    contains_match = re.match(r"\(?\w+\.(\w+)\s+CONTAINS\s+\$(\w+)", cond)
                    eq_match = re.match(r"\w+\.(\w+)\s*=\s*\$(\w+)", cond)
                    if contains_match:
                        if contains_key is None:
                            contains_key = contains_match.group(1)
                            contains_val = params[contains_match.group(2)]
                    elif eq_match:
                        filters[eq_match.group(1)] = params[eq_match.group(2)]

                nodes = self._graph.find_nodes(label, **filters)
                if contains_key and contains_val:
                    nodes = [
                        n for n in nodes
                        if contains_val in str(n.get(contains_key, "")) or contains_val in str(n.get("value", ""))
                    ]
            else:
                nodes = self._graph.find_nodes(label)
            return [{alias: dict(n)} for n in nodes]

        # CREATE relationship with MATCH on two nodes
        # MATCH (a:L1 {id: $from_id}), (b:L2 {id: $to_id}) CREATE (a)-[r:REL ...]->(b) RETURN ...
        m = re.match(
            r"MATCH\s+\((\w+):(\w+)\s+\{id:\s*\$(\w+)\}\),\s*\((\w+):(\w+)\s+\{id:\s*\$(\w+)\}\)\s+"
            r"CREATE\s+\(\1\)-\[(\w+):(\w+)(.*?)\]->\(\4\)\s+"
            r"RETURN\s+(.+)",
            q,
        )
        if m:
            from_label = m.group(2)
            from_id_key = m.group(3)
            to_label = m.group(5)
            to_id_key = m.group(6)
            rel_type = m.group(8)
            props_part = m.group(9).strip()
            from_id = params[from_id_key]
            to_id = params[to_id_key]

            # Check nodes exist
            from_node = self._graph.find_node(from_label, id=from_id)
            to_node = self._graph.find_node(to_label, id=to_id)
            if not from_node or not to_node:
                return []

            rel_props = {}
            if "$" in props_part:
                # e.g. " $props" or " {strength: $strength}"
                prop_ref = re.search(r"\$(\w+)", props_part)
                if prop_ref:
                    val = params.get(prop_ref.group(1))
                    if isinstance(val, dict):
                        rel_props = val
                    else:
                        # single property like strength
                        key_match = re.search(r"\{(\w+):", props_part)
                        if key_match:
                            rel_props = {key_match.group(1): val}
                        else:
                            rel_props = params.get(prop_ref.group(1), {})
                            if not isinstance(rel_props, dict):
                                rel_props = {}

            self._graph.create_rel(from_label, from_id, rel_type, to_label, to_id, rel_props)
            return [{"rel": rel_type}]

        # MATCH pattern for getting relationships and their properties
        # Used by RelationshipManager.get_relationship
        m = re.match(
            r"MATCH\s+\(\w+:(\w+)\s+\{id:\s*\$from_id\}\)-\[\w+:(\w+)\]->\(\w+:(\w+)\s+\{id:\s*\$to_id\}\)\s+"
            r"RETURN\s+type\(\w+\)\s+AS\s+type,\s*properties\(\w+\)\s+AS\s+props,\s*\w+\.id\s+AS\s+from_id,\s*\w+\.id\s+AS\s+to_id",
            q,
        )
        if m:
            rel_type = m.group(2)
            rel = self._graph.find_rel(params["from_id"], rel_type, params["to_id"])
            if rel:
                return [{"type": rel[2], "props": rel[5], "from_id": rel[1], "to_id": rel[4]}]
            return []

        # DELETE relationship
        m = re.match(
            r"MATCH\s+\(\w+:(\w+)\s+\{id:\s*\$from_id\}\)-\[\w+:(\w+)\]->\(\w+:(\w+)\s+\{id:\s*\$to_id\}\)\s+"
            r"DELETE\s+\w+\s+RETURN\s+count\(\w+\)\s+AS\s+(\w+)",
            q,
        )
        if m:
            rel_type = m.group(2)
            before = len(self._graph.relationships)
            self._graph.relationships = [
                r for r in self._graph.relationships
                if not (r[1] == params["from_id"] and r[2] == rel_type and r[4] == params["to_id"])
            ]
            deleted = before - len(self._graph.relationships)
            return [{m.group(4): deleted}]

        # Update relationship SET r += $props
        m = re.match(
            r"MATCH\s+\(\w+:(\w+)\s+\{id:\s*\$from_id\}\)-\[\w+:(\w+)\]->\(\w+:(\w+)\s+\{id:\s*\$to_id\}\)\s+"
            r"SET\s+\w+\s*\+=\s*\$(\w+)\s+RETURN",
            q,
        )
        if m:
            rel_type = m.group(2)
            props_key = m.group(4)
            for i, r in enumerate(self._graph.relationships):
                if r[1] == params["from_id"] and r[2] == rel_type and r[4] == params["to_id"]:
                    updated_props = dict(r[5])
                    updated_props.update(params[props_key])
                    self._graph.relationships[i] = (r[0], r[1], r[2], r[3], r[4], updated_props)
                    return [{"rel": rel_type}]
            return []

        # GET neighbors: MATCH (n {id: $node_id})-[r...]->(m) or <-
        m = re.match(
            r"MATCH\s+\((\w+)\s+\{id:\s*\$node_id\}\)([<\-\[\]:\w>]+)\((\w+)\)\s+"
            r"RETURN\s+(\w+)\s+AS\s+node",
            q,
        )
        if m:
            rel_part = m.group(2)
            rel_type_match = re.search(r":(\w+)", rel_part)
            rel_type = rel_type_match.group(1) if rel_type_match else None
            if "<-" in rel_part:
                direction = "incoming"
            elif "->" in rel_part:
                direction = "outgoing"
            else:
                direction = "both"
            return self._graph.get_neighbors(params["node_id"], rel_type, direction)

        # MATCH (s:Type {id: $source_id}) CREATE (l:Log $props) CREATE (s)-[:REL]->(l) RETURN l.id AS log_id
        m = re.match(
            r"MATCH\s+\(\w+:(\w+)\s+\{id:\s*\$source_id\}\)\s+"
            r"CREATE\s+\(\w+:Log\s+\$(\w+)\)\s+"
            r"CREATE\s+\(\w+\)-\[:(\w+)\]->\(\w+\)\s+"
            r"RETURN\s+\w+\.id\s+AS\s+log_id",
            q,
        )
        if m:
            source_label = m.group(1)
            props_key = m.group(2)
            rel_type = m.group(3)
            source = self._graph.find_node(source_label, id=params["source_id"])
            if not source:
                return []
            props = params[props_key]
            self._graph.create_node("Log", props)
            self._graph.create_rel(source_label, params["source_id"], rel_type, "Log", props["id"])
            return [{"log_id": props["id"]}]

        # Fallback: unrecognized query
        return []


@pytest.fixture
def fake_core() -> FakeNexusCore:
    return FakeNexusCore()


@pytest.fixture
def agent_manager(fake_core: FakeNexusCore) -> AgentManager:
    return AgentManager(fake_core)


@pytest.fixture
def tool_manager(fake_core: FakeNexusCore) -> ToolManager:
    return ToolManager(fake_core)


@pytest.fixture
def memory_manager(fake_core: FakeNexusCore) -> MemoryManager:
    return MemoryManager(fake_core)


@pytest.fixture
def relationship_manager(fake_core: FakeNexusCore) -> RelationshipManager:
    return RelationshipManager(fake_core)


@pytest.fixture
def log_manager(fake_core: FakeNexusCore) -> LogManager:
    return LogManager(fake_core)


@pytest.fixture
def orchestrator(fake_core: FakeNexusCore) -> Orchestrator:
    am = AgentManager(fake_core)
    tm = ToolManager(fake_core)
    mm = MemoryManager(fake_core)
    rm = RelationshipManager(fake_core)
    lm = LogManager(fake_core)
    return Orchestrator(fake_core, am, tm, mm, rm, lm)
