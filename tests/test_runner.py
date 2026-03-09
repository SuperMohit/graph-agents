"""Tests for the AgentRunner with a fake LLM provider."""

import pytest

from nexus_agents.models import Agent, AgentType, RunStatus, Tool
from nexus_agents.runner import AgentRunner
from nexus_agents.tool_registry import ToolRegistry


class FakeLLM:
    """Fake LLM provider that returns canned responses.

    Supports a sequence of responses for multi-turn (tool-use) conversations.
    """

    def __init__(self, responses: list[dict] | None = None) -> None:
        self._responses = list(responses or [])
        self._call_count = 0
        self.calls: list[dict] = []

    def add_response(self, response: dict) -> None:
        self._responses.append(response)

    def chat(self, messages, model=None, system=None, tools=None,
             temperature=None, max_tokens=None):
        self.calls.append({
            "messages": messages,
            "model": model,
            "system": system,
            "tools": tools,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
        else:
            resp = {"content": "default response", "stop_reason": "end_turn"}
        self._call_count += 1
        return resp


def _make_agent(**overrides) -> Agent:
    defaults = {
        "id": "agent-1",
        "name": "TestAgent",
        "type": AgentType.ASSISTANT,
        "config": {
            "model": "test-model",
            "system_prompt": "You are a test agent.",
            "temperature": 0.5,
            "max_tokens": 1024,
        },
    }
    defaults.update(overrides)
    return Agent(**defaults)


def _make_tool(**overrides) -> Tool:
    defaults = {
        "id": "tool-1",
        "name": "calculator",
        "type": "math",
        "description": "Perform arithmetic",
        "config": {
            "input_schema": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                },
            },
        },
    }
    defaults.update(overrides)
    return Tool(**defaults)


class TestAgentRunner:
    def test_simple_text_response(self):
        llm = FakeLLM([{
            "content": "Hello! I'm here to help.",
            "stop_reason": "end_turn",
            "model": "test-model",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }])
        registry = ToolRegistry()
        runner = AgentRunner(llm=llm, tool_registry=registry)

        agent = _make_agent()
        run = runner.run(agent, tools=[], input_data={"message": "Hi"}, workflow_id="wf-1")

        assert run.status == RunStatus.COMPLETED.value
        assert run.output["response"] == "Hello! I'm here to help."
        assert run.agent_id == "agent-1"
        assert run.workflow_id == "wf-1"
        assert run.duration_ms > 0
        assert run.end_time is not None
        assert run.tool_calls == []

    def test_text_response_from_content_blocks(self):
        llm = FakeLLM([{
            "content": [{"type": "text", "text": "Block response"}],
            "stop_reason": "end_turn",
            "model": "test-model",
            "usage": {},
        }])
        registry = ToolRegistry()
        runner = AgentRunner(llm=llm, tool_registry=registry)

        run = runner.run(_make_agent(), [], {"message": "test"}, "wf-1")
        assert run.output["response"] == "Block response"

    def test_tool_use_single_round(self):
        """LLM calls a tool, gets result, then gives final answer."""
        llm = FakeLLM([
            # Round 1: LLM requests tool use
            {
                "content": [
                    {"type": "text", "text": "Let me calculate that."},
                    {
                        "type": "tool_use",
                        "id": "call_123",
                        "name": "calculator",
                        "input": {"expression": "2+2"},
                    },
                ],
                "stop_reason": "tool_use",
            },
            # Round 2: LLM gives final answer after seeing tool result
            {
                "content": "The answer is 4.",
                "stop_reason": "end_turn",
                "model": "test-model",
                "usage": {"input_tokens": 20, "output_tokens": 10},
            },
        ])

        registry = ToolRegistry()
        registry.register("calculator", lambda inp: {"result": eval(inp["expression"])})

        runner = AgentRunner(llm=llm, tool_registry=registry)
        tool = _make_tool()
        run = runner.run(_make_agent(), [tool], {"message": "What is 2+2?"}, "wf-1")

        assert run.status == RunStatus.COMPLETED.value
        assert run.output["response"] == "The answer is 4."
        assert len(run.tool_calls) == 1
        assert run.tool_calls[0]["name"] == "calculator"
        assert run.tool_calls[0]["output"] == {"result": 4}
        assert run.tool_calls[0]["is_error"] is False

    def test_tool_execution_error(self):
        """Tool raises an exception — error is captured, not fatal."""
        llm = FakeLLM([
            {
                "content": [{
                    "type": "tool_use",
                    "id": "call_err",
                    "name": "calculator",
                    "input": {"expression": "bad"},
                }],
                "stop_reason": "tool_use",
            },
            {
                "content": "Sorry, that didn't work.",
                "stop_reason": "end_turn",
            },
        ])

        registry = ToolRegistry()
        registry.register("calculator", lambda inp: (_ for _ in ()).throw(ValueError("bad expr")))

        runner = AgentRunner(llm=llm, tool_registry=registry)
        run = runner.run(_make_agent(), [_make_tool()], {"message": "calc bad"}, "wf-1")

        assert run.status == RunStatus.COMPLETED.value
        assert len(run.tool_calls) == 1
        assert run.tool_calls[0]["is_error"] is True
        assert "bad expr" in str(run.tool_calls[0]["output"])

    def test_max_tool_rounds(self):
        """When tool rounds are exhausted, the run completes with truncation."""
        # LLM always requests tool use
        tool_response = {
            "content": [{
                "type": "tool_use",
                "id": "call_loop",
                "name": "calculator",
                "input": {"expression": "1+1"},
            }],
            "stop_reason": "tool_use",
        }
        llm = FakeLLM([tool_response] * 5)

        registry = ToolRegistry()
        registry.register("calculator", lambda inp: {"result": 2})

        runner = AgentRunner(llm=llm, tool_registry=registry, max_tool_rounds=3)
        run = runner.run(_make_agent(), [_make_tool()], {"message": "loop"}, "wf-1")

        assert run.status == RunStatus.COMPLETED.value
        assert run.output.get("truncated") is True

    def test_llm_exception_fails_run(self):
        """If the LLM itself raises, the run is marked failed."""
        class ExplodingLLM:
            def chat(self, **kwargs):
                raise ConnectionError("LLM down")

        registry = ToolRegistry()
        runner = AgentRunner(llm=ExplodingLLM(), tool_registry=registry)
        run = runner.run(_make_agent(), [], {"message": "hi"}, "wf-1")

        assert run.status == RunStatus.FAILED.value
        assert "LLM down" in run.error

    def test_system_prompt_passed_to_llm(self):
        llm = FakeLLM([{"content": "ok", "stop_reason": "end_turn"}])
        registry = ToolRegistry()
        runner = AgentRunner(llm=llm, tool_registry=registry)

        agent = _make_agent(config={"system_prompt": "Be concise.", "model": "m"})
        runner.run(agent, [], {"message": "hi"}, "wf-1")

        assert llm.calls[0]["system"] == "Be concise."
        assert llm.calls[0]["model"] == "m"

    def test_memories_injected_into_messages(self):
        llm = FakeLLM([{"content": "noted", "stop_reason": "end_turn"}])
        registry = ToolRegistry()
        runner = AgentRunner(llm=llm, tool_registry=registry)

        memories = [
            {"key": "user_name", "value": "Alice"},
            {"key": "preference", "value": "dark mode"},
        ]
        runner.run(_make_agent(), [], {"message": "hi"}, "wf-1", memories=memories)

        # First message should contain memory context
        first_msg = llm.calls[0]["messages"][0]
        assert "Alice" in first_msg["content"]
        assert "dark mode" in first_msg["content"]

    def test_input_data_message_key(self):
        llm = FakeLLM([{"content": "ok", "stop_reason": "end_turn"}])
        runner = AgentRunner(llm=llm, tool_registry=ToolRegistry())
        runner.run(_make_agent(), [], {"message": "specific input"}, "wf-1")
        user_msg = llm.calls[0]["messages"][-1]
        assert user_msg["content"] == "specific input"

    def test_input_data_task_key(self):
        llm = FakeLLM([{"content": "ok", "stop_reason": "end_turn"}])
        runner = AgentRunner(llm=llm, tool_registry=ToolRegistry())
        runner.run(_make_agent(), [], {"task": "do something"}, "wf-1")
        user_msg = llm.calls[0]["messages"][-1]
        assert user_msg["content"] == "do something"

    def test_messages_recorded_in_run(self):
        llm = FakeLLM([{"content": "response", "stop_reason": "end_turn"}])
        runner = AgentRunner(llm=llm, tool_registry=ToolRegistry())
        run = runner.run(_make_agent(), [], {"message": "hello"}, "wf-1")
        assert len(run.messages) >= 1
        assert run.messages[-1]["role"] == "user"
        assert run.messages[-1]["content"] == "hello"
