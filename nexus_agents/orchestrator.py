"""Orchestrator - Workflow execution and agent chain coordination."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from nexus_agents.core import NexusCore
from nexus_agents.managers.agent_manager import AgentManager
from nexus_agents.managers.log_manager import LogManager
from nexus_agents.managers.memory_manager import MemoryManager
from nexus_agents.managers.relationship_manager import RelationshipManager
from nexus_agents.managers.tool_manager import ToolManager
from nexus_agents.models import (
    AgentRun,
    AgentStatus,
    LogLevel,
    RunStatus,
    WorkflowExecution,
    WorkflowStatus,
)
from nexus_agents.runner import AgentRunner
from nexus_agents.tool_registry import ToolRegistry


class Orchestrator:
    """Coordinates workflow execution across agents in the graph.

    The orchestrator:
    1. Reads agent definitions, tools, and memories from Neo4j.
    2. Uses ``AgentRunner`` to actually execute each agent (LLM calls + tool use).
    3. Follows ``TRANSITIONS_TO`` edges with condition evaluation.
    4. Persists ``AgentRun`` nodes back to the graph for full observability.
    """

    def __init__(
        self,
        core: NexusCore,
        agent_manager: AgentManager,
        tool_manager: ToolManager,
        memory_manager: MemoryManager,
        relationship_manager: RelationshipManager,
        log_manager: LogManager,
        runner: AgentRunner | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._core = core
        self._agent_manager = agent_manager
        self._tool_manager = tool_manager
        self._memory_manager = memory_manager
        self._relationship_manager = relationship_manager
        self._log_manager = log_manager
        self._runner = runner
        self._tool_registry = tool_registry or ToolRegistry()

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._tool_registry

    # ------------------------------------------------------------------
    # Workflow lifecycle
    # ------------------------------------------------------------------

    def start_workflow(
        self,
        input_data: dict[str, Any],
        start_agent_id: str,
    ) -> WorkflowExecution:
        """Initialize a new workflow execution starting from the given agent."""
        agent = self._agent_manager.get_agent(start_agent_id)
        if agent is None:
            raise ValueError(f"Start agent '{start_agent_id}' not found")

        workflow = WorkflowExecution(
            id=str(uuid.uuid4()),
            status=WorkflowStatus.PENDING.value,
            input=input_data,
            agent_sequence=[start_agent_id],
        )

        self._core.run_query(
            "CREATE (w:WorkflowExecution $props)",
            {"props": workflow.to_dict()},
        )

        self._log_manager.log(
            source_id=start_agent_id,
            source_type="Agent",
            message=f"Workflow {workflow.id} started",
            level=LogLevel.INFO,
            details={"workflow_id": workflow.id, "input": input_data},
        )

        return workflow

    # ------------------------------------------------------------------
    # Agent chain execution
    # ------------------------------------------------------------------

    def execute_agent_chain(self, workflow: WorkflowExecution) -> dict[str, Any]:
        """Execute a chain of agents following TRANSITIONS_TO edges.

        When an ``AgentRunner`` is configured, each agent is actually
        executed (LLM call + tools).  Otherwise the orchestrator walks
        the graph recording metadata only (useful for dry-runs / tests).
        """
        workflow.status = WorkflowStatus.RUNNING.value
        self._update_workflow(workflow)

        current_agent_id = workflow.agent_sequence[0]
        chain_result: dict[str, Any] = {"steps": [], "input": workflow.input}
        step_data = workflow.input.copy()

        visited: set[str] = set()
        max_steps = 50

        for _ in range(max_steps):
            if current_agent_id in visited:
                self._log_manager.log(
                    source_id=current_agent_id,
                    source_type="Agent",
                    message=f"Cycle detected at agent {current_agent_id}, stopping",
                    level=LogLevel.WARNING,
                    details={"workflow_id": workflow.id},
                )
                break

            visited.add(current_agent_id)
            agent = self._agent_manager.get_agent(current_agent_id)
            if agent is None:
                self._log_manager.log(
                    source_id=workflow.agent_sequence[0],
                    source_type="Agent",
                    message=f"Agent {current_agent_id} not found during chain execution",
                    level=LogLevel.ERROR,
                    details={"workflow_id": workflow.id},
                )
                workflow.status = WorkflowStatus.FAILED.value
                self._update_workflow(workflow)
                chain_result["error"] = f"Agent {current_agent_id} not found"
                return chain_result

            # Gather tools linked via CAN_USE
            tool_neighbors = self._relationship_manager.get_neighbors(
                node_id=current_agent_id,
                rel_type="CAN_USE",
                direction="outgoing",
            )
            available_tool_ids = [n["node"]["id"] for n in tool_neighbors]
            available_tools = [
                self._tool_manager.get_tool(tid)
                for tid in available_tool_ids
            ]
            available_tools = [t for t in available_tools if t is not None]

            # Gather memories linked via INFORMS (Memory -> Agent)
            memory_neighbors = self._relationship_manager.get_neighbors(
                node_id=current_agent_id,
                rel_type="INFORMS",
                direction="incoming",
            )
            memories = [n["node"] for n in memory_neighbors]

            # Also get memories the agent STOREs (Agent -> Memory)
            stored_neighbors = self._relationship_manager.get_neighbors(
                node_id=current_agent_id,
                rel_type="STORES",
                direction="outgoing",
            )
            for n in stored_neighbors:
                if n["node"] not in memories:
                    memories.append(n["node"])

            # --- Actually execute the agent if a runner is configured ---
            agent_run: AgentRun | None = None
            if self._runner is not None:
                agent_run = self._runner.run(
                    agent=agent,
                    tools=available_tools,
                    input_data=step_data,
                    workflow_id=workflow.id,
                    memories=memories if memories else None,
                )

                # Persist AgentRun to graph
                self._core.run_query(
                    "CREATE (r:AgentRun $props)",
                    {"props": agent_run.to_dict()},
                )

                self._log_manager.log(
                    source_id=current_agent_id,
                    source_type="Agent",
                    message=f"Agent {agent.name} executed ({agent_run.status})",
                    level=LogLevel.INFO if agent_run.status == RunStatus.COMPLETED.value else LogLevel.ERROR,
                    details={
                        "run_id": agent_run.id,
                        "workflow_id": workflow.id,
                        "duration_ms": agent_run.duration_ms,
                        "tool_calls": len(agent_run.tool_calls),
                    },
                )

                # If the agent failed, abort the workflow
                if agent_run.status == RunStatus.FAILED.value:
                    workflow.status = WorkflowStatus.FAILED.value
                    self._update_workflow(workflow)
                    chain_result["error"] = agent_run.error
                    chain_result["steps"].append(
                        self._build_step(agent, available_tool_ids, step_data, agent_run)
                    )
                    return chain_result

                # Pass the agent's output as input to the next agent
                step_data = agent_run.output.copy()
            else:
                # No runner — metadata-only pass (backward compat)
                self._log_manager.log(
                    source_id=current_agent_id,
                    source_type="Agent",
                    message=f"Agent {agent.name} executed in workflow {workflow.id}",
                    level=LogLevel.INFO,
                    details={"step_data": step_data, "tools": available_tool_ids},
                )

            # Record step
            step = self._build_step(agent, available_tool_ids, step_data, agent_run)
            chain_result["steps"].append(step)

            if current_agent_id not in workflow.agent_sequence:
                workflow.agent_sequence.append(current_agent_id)

            # Determine next agent
            next_agent_id = self.get_next_agent(current_agent_id, step_data)
            if next_agent_id is None:
                break

            current_agent_id = next_agent_id

        workflow.status = WorkflowStatus.COMPLETED.value
        workflow.end_time = datetime.utcnow()
        workflow.result = chain_result
        self._update_workflow(workflow)

        return chain_result

    # ------------------------------------------------------------------
    # Transition resolution
    # ------------------------------------------------------------------

    def get_next_agent(
        self,
        current_agent_id: str,
        result: dict[str, Any] | None = None,
    ) -> str | None:
        """Determine the next agent based on TRANSITIONS_TO relationships.

        Evaluates conditions on transition edges against the current result.
        """
        neighbors = self._relationship_manager.get_neighbors(
            node_id=current_agent_id,
            rel_type="TRANSITIONS_TO",
            direction="outgoing",
        )

        if not neighbors:
            return None

        fallback: str | None = None
        for neighbor in neighbors:
            rel_props = neighbor.get("rel_props", {})
            condition = rel_props.get("condition")
            next_id = neighbor["node"]["id"]

            if condition is None:
                if fallback is None:
                    fallback = next_id
                continue

            if result and self._evaluate_condition(condition, result):
                return next_id

        return fallback

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------

    def visualize_workflow(self, workflow_id: str) -> str:
        """Generate a text representation of a workflow's execution path."""
        rows = self._core.run_query(
            "MATCH (w:WorkflowExecution {id: $id}) RETURN w",
            {"id": workflow_id},
        )
        if not rows:
            return f"Workflow {workflow_id} not found"

        wf = WorkflowExecution.from_dict(dict(rows[0]["w"]))
        lines = [
            f"Workflow: {wf.id}",
            f"Status: {wf.status}",
            f"Started: {wf.start_time.isoformat()}",
            f"Ended: {wf.end_time.isoformat() if wf.end_time else 'In progress'}",
            f"Agent sequence: {' -> '.join(wf.agent_sequence)}",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _build_step(
        agent: Any,
        tool_ids: list[str],
        step_data: dict[str, Any],
        agent_run: AgentRun | None,
    ) -> dict[str, Any]:
        step: dict[str, Any] = {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "agent_type": agent.type.value if hasattr(agent.type, "value") else agent.type,
            "input": step_data,
            "available_tools": tool_ids,
            "config": agent.config,
        }
        if agent_run is not None:
            step["run_id"] = agent_run.id
            step["status"] = agent_run.status
            step["output"] = agent_run.output
            step["tool_calls"] = agent_run.tool_calls
            step["duration_ms"] = agent_run.duration_ms
            if agent_run.error:
                step["error"] = agent_run.error
        return step

    def _update_workflow(self, workflow: WorkflowExecution) -> None:
        """Persist workflow state to the database."""
        self._core.run_query(
            "MATCH (w:WorkflowExecution {id: $id}) SET w += $props",
            {"id": workflow.id, "props": workflow.to_dict()},
        )

    @staticmethod
    def _evaluate_condition(condition: str, result: dict[str, Any]) -> bool:
        """Evaluate a simple condition string against a result dict.

        Supports simple key=value checks like "status=success" or "type=research".
        """
        if "=" not in condition:
            return condition in result

        key, value = condition.split("=", 1)
        key = key.strip()
        value = value.strip()
        return str(result.get(key, "")) == value
