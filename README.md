# NexusAgents

A graph-based agentic framework that uses **Neo4j** as a unified backbone for agent orchestration, tool management, memory (short-term and long-term), and structured logging.

Rather than stitching together fragmented libraries, NexusAgents co-locates every part of the agent lifecycle in a single graph database — making introspection, debugging, and dynamic reconfiguration first-class features.

## Why a Graph?

| Capability | How Neo4j Helps |
|---|---|
| **Dynamic orchestration** | Agent sequences adapt at runtime by following `TRANSITIONS_TO` edges with conditional routing |
| **System introspection** | Every operation is a node — visualize actual execution flows directly in the graph |
| **Runtime reconfiguration** | Change agent wiring by updating relationships, no redeployment needed |
| **Contextual logging** | Log nodes are connected to the agents and tools that produced them |
| **Scalable multi-agent design** | Add specialized agents without modifying existing ones |
| **Persistent state** | Agent state survives restarts; Neo4j transactions provide atomicity |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       NexusAgents                           │
│                     (Facade / Entry Point)                  │
├─────────────────────────────────────────────────────────────┤
│  AgentManager  ToolManager  MemoryManager  LogManager  ...  │
├──────────────────────┬──────────────────────────────────────┤
│     Orchestrator     │         ToolRegistry                 │
│  (Workflow Engine)   │  (name → Python callable)            │
├──────────────────────┼──────────────────────────────────────┤
│                  AgentRunner                                │
│    (LLM calls + tool-use loop + memory injection)           │
├─────────────────────────────────────────────────────────────┤
│                    LLMProvider                              │
│   (AnthropicProvider or any Protocol-compatible impl)       │
├─────────────────────────────────────────────────────────────┤
│                      NexusCore                              │
│                (Neo4j Driver + Schema)                      │
└─────────────────────────────────────────────────────────────┘
```

## Graph Schema

### Node Types

| Node | Key Properties |
|------|---------------|
| **Agent** | `id`, `name`, `type`, `status`, `config` (model, system_prompt, temperature, ...) |
| **Tool** | `id`, `name`, `type`, `description`, `config` (input_schema, ...) |
| **Memory** | `id`, `key`, `value`, `memory_type`, `priority`, `expiration` |
| **Log** | `id`, `message`, `level`, `details`, `timestamp` |
| **AgentRun** | `id`, `agent_id`, `workflow_id`, `status`, `input`, `output`, `tool_calls`, `duration_ms` |

### Relationships

```
Agent  ─[CAN_USE]──────────→ Tool
Agent  ─[DELEGATES_TO]─────→ Agent
Agent  ─[COMMUNICATES_WITH]─→ Agent
Agent  ─[TRANSITIONS_TO]───→ Agent    (with condition properties)
Agent  ─[GENERATED]────────→ Log
Agent  ─[STORES]───────────→ Memory
Memory ─[INFORMS]──────────→ Agent    (with relevance_score)
Memory ─[REFERENCES]───────→ Memory   (with strength)
Tool   ─[PRODUCED]─────────→ Log
Log    ─[CONTRIBUTES_TO]───→ Memory   (with weight)
```

## Installation

```bash
pip install -e .

# With Anthropic LLM support
pip install -e ".[anthropic]"
```

**Requirements:** Python 3.10+ and a running [Neo4j](https://neo4j.com/) instance (5.x+).

## Quick Start

### Full execution with LLM

Agents are defined in the graph with their config (model, system prompt, etc.). Tools are registered as Python callables. The orchestrator walks the graph, calls the LLM at each agent, executes tools, and passes output forward.

```python
from nexus_agents import NexusAgents, AgentType, MemoryType
from nexus_agents.providers import AnthropicProvider

# 1. Connect with an LLM provider
nexus = NexusAgents(
    uri="bolt://localhost:7687",
    username="neo4j",
    password="password",
    llm=AnthropicProvider(api_key="sk-ant-..."),
)
nexus.initialize()

# 2. Create agents with LLM config stored in the graph
planner_id = nexus.agent_manager.create_agent("Planner", AgentType.PLANNER, {
    "model": "claude-sonnet-4-20250514",
    "system_prompt": "You are a planning agent. Break tasks into steps.",
    "temperature": 0.7,
})
executor_id = nexus.agent_manager.create_agent("Executor", AgentType.EXECUTOR, {
    "model": "claude-sonnet-4-20250514",
    "system_prompt": "You execute plans. Use tools when needed.",
})

# 3. Wire agents into a pipeline
nexus.relationship_manager.create_relationship(
    planner_id, "Agent", executor_id, "Agent", "TRANSITIONS_TO"
)

# 4. Register a tool (graph node + Python implementation)
search_id = nexus.tool_manager.create_tool(
    "web_search", "search", "Search the web for information",
    config={
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }
    },
)
nexus.relationship_manager.create_relationship(
    executor_id, "Agent", search_id, "Tool", "CAN_USE"
)

# Register the actual Python function
nexus.tool_registry.register("web_search", lambda inp: {
    "results": my_search_api(inp["query"])
})

# 5. Add memory that informs an agent
mem_id = nexus.memory_manager.create_memory(
    key="project_goal",
    value="Build a recommendation engine",
    memory_type=MemoryType.LONG_TERM,
    priority=10,
)
nexus.relationship_manager.create_relationship(
    mem_id, "Memory", executor_id, "Agent", "INFORMS"
)

# 6. Run the workflow — agents actually execute
workflow = nexus.orchestrator.start_workflow(
    {"message": "Design and build a recommendation engine"},
    start_agent_id=planner_id,
)
result = nexus.orchestrator.execute_agent_chain(workflow)

for step in result["steps"]:
    print(f"{step['agent_name']}: {step['output']['response'][:80]}...")
    if step.get("tool_calls"):
        for tc in step["tool_calls"]:
            print(f"  └─ {tc['name']}({tc['input']}) → {tc['output']}")

nexus.close()
```

### How execution works

```
                    ┌──────────────┐
                    │  Orchestrator │
                    └──────┬───────┘
                           │ for each agent in TRANSITIONS_TO chain:
                           ▼
                    ┌──────────────┐
                    │  AgentRunner  │
                    └──────┬───────┘
                           │ 1. Load agent config from graph
                           │ 2. Gather memories (INFORMS edges)
                           │ 3. Gather tools (CAN_USE edges)
                           │ 4. Call LLM with system prompt + tools
                           ▼
              ┌────────────────────────┐
              │      LLM Provider      │
              │  (Anthropic, custom)   │
              └────────────┬───────────┘
                           │ if stop_reason == "tool_use":
                           ▼
              ┌────────────────────────┐
              │     ToolRegistry       │──→ execute Python callable
              │ (name → function map) │←── return result to LLM
              └────────────────────────┘
                           │ loop until end_turn or max rounds
                           ▼
              ┌────────────────────────┐
              │  AgentRun persisted    │──→ saved as node in Neo4j
              │  to graph with full    │    (input, output, tool_calls,
              │  execution trace       │     duration, status, error)
              └────────────────────────┘
```

### Conditional routing

Use a **Router** agent to branch execution based on context:

```python
router_id   = nexus.agent_manager.create_agent("Router", AgentType.ROUTER, {
    "system_prompt": "Classify the request as 'research' or 'code'. Respond with just the type.",
})
research_id = nexus.agent_manager.create_agent("Researcher", AgentType.ASSISTANT)
coder_id    = nexus.agent_manager.create_agent("Coder",      AgentType.EXECUTOR)

nexus.relationship_manager.create_relationship(
    router_id, "Agent", research_id, "Agent", "TRANSITIONS_TO",
    {"condition": "type=research"},
)
nexus.relationship_manager.create_relationship(
    router_id, "Agent", coder_id, "Agent", "TRANSITIONS_TO",
    {"condition": "type=code"},
)
```

### Custom LLM providers

Any object implementing the `LLMProvider` protocol works:

```python
class MyProvider:
    def chat(self, messages, model=None, system=None, tools=None,
             temperature=None, max_tokens=None) -> dict:
        # Call your LLM and return:
        return {
            "content": "response text",        # or list of content blocks
            "stop_reason": "end_turn",          # or "tool_use"
            "model": "my-model",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }

nexus = NexusAgents(uri="...", username="...", password="...", llm=MyProvider())
```

## API Reference

### NexusAgents (Facade)

| Method / Property | Description |
|--------|-------------|
| `initialize()` | Create database constraints and indexes |
| `close()` | Close the Neo4j connection |
| `tool_registry` | Access the `ToolRegistry` to register tool implementations |

Exposes: `agent_manager`, `tool_manager`, `memory_manager`, `relationship_manager`, `log_manager`, `orchestrator`.

### AgentManager

| Method | Description |
|--------|-------------|
| `create_agent(name, agent_type, config=None)` | Create an agent node, returns its ID |
| `get_agent(agent_id)` | Retrieve an agent by ID |
| `update_agent(agent_id, properties)` | Update agent properties |
| `delete_agent(agent_id)` | Delete an agent and its relationships |
| `list_agents(filters=None)` | List agents with optional filters |
| `connect_agents(from_id, to_id, rel_type, properties=None)` | Create an inter-agent relationship |

### ToolManager + ToolRegistry

| Method | Description |
|--------|-------------|
| **ToolManager** | |
| `create_tool(name, tool_type, description, config=None)` | Create a tool node in the graph |
| `get_tool(tool_id)` | Retrieve a tool by ID |
| `list_tools(filters=None)` | List tools with optional filters |
| **ToolRegistry** | |
| `register(tool_name, fn)` | Register a Python callable for a tool name |
| `execute(tool_name, tool_input)` | Execute a registered tool |
| `build_tool_specs(tools)` | Build Anthropic-style tool specs from Tool models |

### MemoryManager

| Method | Description |
|--------|-------------|
| `create_memory(key, value, memory_type, priority=0, expiration=None)` | Store a memory node |
| `get_memory(memory_id)` | Retrieve a memory by ID |
| `search_memories(query, filters=None)` | Search by key/value content |
| `connect_memories(from_id, to_id, strength=1.0)` | Link related memories via `REFERENCES` |

### LogManager

| Method | Description |
|--------|-------------|
| `log(source_id, source_type, message, level=INFO, details=None)` | Create a log linked to an Agent or Tool |
| `get_logs(filters=None)` | Retrieve logs with optional filters |
| `search_logs(query)` | Search logs by message content |

### Orchestrator

| Method | Description |
|--------|-------------|
| `start_workflow(input_data, start_agent_id)` | Initialize a workflow execution |
| `execute_agent_chain(workflow)` | Run agents following `TRANSITIONS_TO` edges, executing each via `AgentRunner` |
| `get_next_agent(current_agent_id, result=None)` | Resolve the next agent with condition evaluation |
| `visualize_workflow(workflow_id)` | Get a text summary of workflow execution |

### AgentRunner

| Method | Description |
|--------|-------------|
| `run(agent, tools, input_data, workflow_id, memories=None)` | Execute a single agent to completion (LLM + tool loop) |

Returns an `AgentRun` with: `status`, `output`, `tool_calls`, `messages`, `duration_ms`, `error`.

## Enums

```python
AgentType:    REASONING | ROUTER | ASSISTANT | PLANNER | EXECUTOR | CRITIC
MemoryType:   LONG_TERM | SHORT_TERM | CONTEXT | EPISODIC | SEMANTIC
LogLevel:     DEBUG | INFO | WARNING | ERROR | CRITICAL
AgentStatus:  IDLE | RUNNING | PAUSED | ERROR | TERMINATED
RunStatus:    PENDING | RUNNING | COMPLETED | FAILED | TOOL_CALLING
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests (no Neo4j instance required — uses in-memory fake graph)
pytest

# 71 tests covering models, managers, tool registry, runner, and orchestrator
```

## License

MIT
