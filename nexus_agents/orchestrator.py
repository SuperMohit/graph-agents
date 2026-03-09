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
from nexus_agents.models import LogLevel, WorkflowExecution, WorkflowStatus


class Orchestrator:
    """Coordinates workflow execution across agents in the graph.

    The orchestrator follows TRANSITIONS_TO relationships to determine
    the execution order of agents, evaluating conditions on each edge
    to decide which agent to execute next.
    """

    def __init__(
        self,
        core: NexusCore,
        agent_manager: AgentManager,
        tool_manager: ToolManager,
        memory_manager: MemoryManager,
        relationship_manager: RelationshipManager,
        log_manager: LogManager,
    ) -> None:
        self._core = core
        self._agent_manager = agent_manager
        self._tool_manager = tool_manager
        self._memory_manager = memory_manager
        self._relationship_manager = relationship_manager
        self._log_manager = log_manager

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

        # Persist the workflow node
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

    def get_next_agent(
        self,
        current_agent_id: str,
        result: dict[str, Any] | None = None,
    ) -> str | None:
        """Determine the next agent based on TRANSITIONS_TO relationships.

        Evaluates conditions on transition edges against the current result
        to pick the appropriate next agent. Returns None if no transition exists.
        """
        neighbors = self._relationship_manager.get_neighbors(
            node_id=current_agent_id,
            rel_type="TRANSITIONS_TO",
            direction="outgoing",
        )

        if not neighbors:
            return None

        # Evaluate conditions: pick the first matching transition, or
        # fallback to the first unconditional one.
        fallback: str | None = None
        for neighbor in neighbors:
            rel_props = neighbor.get("rel_props", {})
            condition = rel_props.get("condition")
            next_id = neighbor["node"]["id"]

            if condition is None:
                if fallback is None:
                    fallback = next_id
                continue

            # Simple condition evaluation: check if a key in result matches
            if result and self._evaluate_condition(condition, result):
                return next_id

        return fallback

    def execute_agent_chain(self, workflow: WorkflowExecution) -> dict[str, Any]:
        """Execute a chain of agents following TRANSITIONS_TO edges.

        Walks through the agent graph starting from the first agent in the
        workflow's sequence, collecting results at each step.
        """
        workflow.status = WorkflowStatus.RUNNING.value
        self._update_workflow(workflow)

        current_agent_id = workflow.agent_sequence[0]
        chain_result: dict[str, Any] = {"steps": [], "input": workflow.input}
        step_data = workflow.input.copy()

        visited: set[str] = set()
        max_steps = 50  # prevent infinite loops

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

            # Get tools available to this agent
            tool_neighbors = self._relationship_manager.get_neighbors(
                node_id=current_agent_id,
                rel_type="CAN_USE",
                direction="outgoing",
            )
            available_tools = [n["node"]["id"] for n in tool_neighbors]

            # Record step
            step = {
                "agent_id": current_agent_id,
                "agent_name": agent.name,
                "agent_type": agent.type.value if hasattr(agent.type, "value") else agent.type,
                "input": step_data,
                "available_tools": available_tools,
                "config": agent.config,
            }
            chain_result["steps"].append(step)

            if current_agent_id not in workflow.agent_sequence:
                workflow.agent_sequence.append(current_agent_id)

            self._log_manager.log(
                source_id=current_agent_id,
                source_type="Agent",
                message=f"Agent {agent.name} executed in workflow {workflow.id}",
                level=LogLevel.INFO,
                details={"step_data": step_data, "tools": available_tools},
            )

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
