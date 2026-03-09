"""AgentRunner - Executes a single agent: calls the LLM, runs tools, returns output."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Protocol

from nexus_agents.models import Agent, AgentRun, AgentStatus, LogLevel, RunStatus, Tool
from nexus_agents.tool_registry import ToolRegistry


# ---------------------------------------------------------------------------
# LLM provider protocol – any object that implements ``chat`` works.
# ---------------------------------------------------------------------------

class LLMProvider(Protocol):
    """Protocol for LLM providers.

    Implementations must provide a ``chat`` method that accepts messages
    and optional tool specifications and returns a response dict.
    """

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Send messages to the LLM and return a response.

        Expected response format::

            {
                "content": "text response" | [content_blocks],
                "stop_reason": "end_turn" | "tool_use",
                "model": "model-id",
                "usage": {"input_tokens": N, "output_tokens": N},
            }

        When ``stop_reason`` is ``"tool_use"``, ``content`` must be a list
        of content blocks where tool-use blocks look like::

            {
                "type": "tool_use",
                "id": "call_xxx",
                "name": "tool_name",
                "input": { ... }
            }
        """
        ...


# ---------------------------------------------------------------------------
# AgentRunner
# ---------------------------------------------------------------------------

class AgentRunner:
    """Runs a single agent to completion (including tool-use loops).

    The runner:
    1. Builds a message list from the agent's system prompt + input.
    2. Calls the LLM provider.
    3. If the LLM requests tool use, executes tools via the ToolRegistry and
       feeds results back (up to ``max_tool_rounds``).
    4. Returns an ``AgentRun`` with full execution trace.
    """

    def __init__(
        self,
        llm: LLMProvider,
        tool_registry: ToolRegistry,
        max_tool_rounds: int = 10,
    ) -> None:
        self._llm = llm
        self._tool_registry = tool_registry
        self._max_tool_rounds = max_tool_rounds

    def run(
        self,
        agent: Agent,
        tools: list[Tool],
        input_data: dict[str, Any],
        workflow_id: str,
        memories: list[dict[str, Any]] | None = None,
    ) -> AgentRun:
        """Execute the agent and return a completed AgentRun."""
        agent_run = AgentRun(
            id=str(uuid.uuid4()),
            agent_id=agent.id,
            workflow_id=workflow_id,
            status=RunStatus.RUNNING.value,
            input=input_data,
            start_time=datetime.utcnow(),
        )

        config = agent.config or {}
        model = config.get("model", "claude-sonnet-4-20250514")
        system_prompt = config.get("system_prompt")
        temperature = config.get("temperature")
        max_tokens = config.get("max_tokens", 4096)

        # Build initial messages
        messages: list[dict[str, Any]] = []

        # Inject memories as context
        if memories:
            memory_text = "\n".join(
                f"- [{m.get('key', '')}]: {m.get('value', '')}" for m in memories
            )
            messages.append({
                "role": "user",
                "content": f"Relevant context from memory:\n{memory_text}",
            })
            messages.append({
                "role": "assistant",
                "content": "I'll take this context into account.",
            })

        # User input
        user_content = input_data.get("message") or input_data.get("task") or str(input_data)
        messages.append({"role": "user", "content": user_content})

        # Build tool specs for LLM
        tool_specs = self._tool_registry.build_tool_specs(tools) if tools else None

        t0 = time.monotonic()
        try:
            agent_run = self._run_loop(
                agent_run=agent_run,
                messages=messages,
                model=model,
                system=system_prompt,
                tools=tool_specs,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            agent_run.status = RunStatus.FAILED.value
            agent_run.error = str(exc)
        finally:
            agent_run.end_time = datetime.utcnow()
            agent_run.duration_ms = (time.monotonic() - t0) * 1000
            agent_run.messages = messages

        return agent_run

    # ------------------------------------------------------------------

    def _run_loop(
        self,
        agent_run: AgentRun,
        messages: list[dict[str, Any]],
        model: str,
        system: str | None,
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int,
    ) -> AgentRun:
        """LLM call + tool-use loop."""
        for _ in range(self._max_tool_rounds + 1):
            response = self._llm.chat(
                messages=messages,
                model=model,
                system=system,
                tools=tools if tools else None,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            stop_reason = response.get("stop_reason", "end_turn")

            if stop_reason != "tool_use":
                # Final text response
                content = response.get("content", "")
                if isinstance(content, list):
                    text_parts = [
                        b["text"] for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    content = "\n".join(text_parts)
                agent_run.output = {
                    "response": content,
                    "model": response.get("model"),
                    "usage": response.get("usage"),
                }
                agent_run.status = RunStatus.COMPLETED.value
                return agent_run

            # Handle tool use
            agent_run.status = RunStatus.TOOL_CALLING.value
            content_blocks = response.get("content", [])
            if not isinstance(content_blocks, list):
                agent_run.output = {"response": str(content_blocks)}
                agent_run.status = RunStatus.COMPLETED.value
                return agent_run

            # Append assistant message with tool-use blocks
            messages.append({"role": "assistant", "content": content_blocks})

            # Execute each tool call and collect results
            tool_results: list[dict[str, Any]] = []
            for block in content_blocks:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue

                tool_name = block["name"]
                tool_input = block.get("input", {})
                call_id = block.get("id", str(uuid.uuid4()))

                try:
                    tool_output = self._tool_registry.execute(tool_name, tool_input)
                    result_content = tool_output
                    is_error = False
                except Exception as exc:
                    result_content = {"error": str(exc)}
                    is_error = True

                agent_run.tool_calls.append({
                    "id": call_id,
                    "name": tool_name,
                    "input": tool_input,
                    "output": result_content,
                    "is_error": is_error,
                })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": str(result_content),
                    "is_error": is_error,
                })

            messages.append({"role": "user", "content": tool_results})

        # Exhausted tool rounds
        agent_run.status = RunStatus.COMPLETED.value
        agent_run.output = {"response": "Max tool rounds reached", "truncated": True}
        return agent_run
