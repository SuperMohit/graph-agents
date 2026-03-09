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
┌─────────────────────────────────────────────────────────┐
│                     NexusAgents                         │
│                   (Facade / Entry Point)                │
├──────────┬──────────┬──────────┬──────────┬─────────────┤
│  Agent   │   Tool   │  Memory  │   Log    │Relationship │
│  Manager │  Manager │  Manager │  Manager │  Manager    │
├──────────┴──────────┴──────────┴──────────┴─────────────┤
│                     Orchestrator                        │
│            (Workflow Execution Engine)                   │
├─────────────────────────────────────────────────────────┤
│                      NexusCore                          │
│              (Neo4j Driver + Schema)                    │
└─────────────────────────────────────────────────────────┘
```

## Graph Schema

### Node Types

| Node | Key Properties |
|------|---------------|
| **Agent** | `id`, `name`, `type`, `status`, `config` |
| **Tool** | `id`, `name`, `type`, `description`, `function`, `config` |
| **Memory** | `id`, `key`, `value`, `memory_type`, `priority`, `expiration` |
| **Log** | `id`, `message`, `level`, `details`, `timestamp` |

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
```

**Requirements:** Python 3.10+ and a running [Neo4j](https://neo4j.com/) instance (5.x+).

## Quick Start

```python
from nexus_agents import NexusAgents, AgentType, MemoryType, LogLevel

# Connect and initialize the schema
with NexusAgents(uri="bolt://localhost:7687", username="neo4j", password="password") as nexus:
    nexus.initialize()

    # --- Create agents ---
    planner_id  = nexus.agent_manager.create_agent("Planner",  AgentType.PLANNER)
    executor_id = nexus.agent_manager.create_agent("Executor", AgentType.EXECUTOR)
    critic_id   = nexus.agent_manager.create_agent("Critic",   AgentType.CRITIC)

    # --- Wire them into a pipeline ---
    nexus.relationship_manager.create_relationship(
        planner_id, "Agent", executor_id, "Agent", "TRANSITIONS_TO"
    )
    nexus.relationship_manager.create_relationship(
        executor_id, "Agent", critic_id, "Agent", "TRANSITIONS_TO"
    )

    # --- Attach a tool ---
    search_id = nexus.tool_manager.create_tool(
        "WebSearch", "search", "Search the web for information"
    )
    nexus.relationship_manager.create_relationship(
        executor_id, "Agent", search_id, "Tool", "CAN_USE", {"priority": 1}
    )

    # --- Store a memory ---
    nexus.memory_manager.create_memory(
        key="project_context",
        value={"goal": "Build a recommendation engine"},
        memory_type=MemoryType.LONG_TERM,
        priority=10,
    )

    # --- Run a workflow ---
    workflow = nexus.orchestrator.start_workflow(
        {"task": "Design and build a recommendation engine"},
        start_agent_id=planner_id,
    )
    result = nexus.orchestrator.execute_agent_chain(workflow)

    print(result)
    # {
    #   "workflow_id": "...",
    #   "status": "completed",
    #   "steps": [
    #     {"agent_id": "...", "agent_name": "Planner",  "available_tools": []},
    #     {"agent_id": "...", "agent_name": "Executor", "available_tools": ["..."]},
    #     {"agent_id": "...", "agent_name": "Critic",   "available_tools": []},
    #   ]
    # }
```

### Conditional Routing

Use a **Router** agent to branch execution based on context:

```python
router_id   = nexus.agent_manager.create_agent("Router",   AgentType.ROUTER)
research_id = nexus.agent_manager.create_agent("Research", AgentType.ASSISTANT)
code_id     = nexus.agent_manager.create_agent("Coder",    AgentType.EXECUTOR)

nexus.relationship_manager.create_relationship(
    router_id, "Agent", research_id, "Agent", "TRANSITIONS_TO",
    {"condition": "type=research"},
)
nexus.relationship_manager.create_relationship(
    router_id, "Agent", code_id, "Agent", "TRANSITIONS_TO",
    {"condition": "type=code"},
)

# The orchestrator evaluates conditions against the result dict
next_agent = nexus.orchestrator.get_next_agent(router_id, {"type": "research"})
# → research_id
```

## API Reference

### NexusAgents (Facade)

| Method | Description |
|--------|-------------|
| `initialize()` | Create database constraints and indexes |
| `close()` | Close the Neo4j connection |

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

### ToolManager

| Method | Description |
|--------|-------------|
| `create_tool(name, tool_type, description, function="", config=None)` | Create a tool node |
| `get_tool(tool_id)` | Retrieve a tool by ID |
| `update_tool(tool_id, properties)` | Update tool properties |
| `delete_tool(tool_id)` | Delete a tool |
| `list_tools(filters=None)` | List tools with optional filters |

### MemoryManager

| Method | Description |
|--------|-------------|
| `create_memory(key, value, memory_type, priority=0, expiration=None)` | Store a memory node |
| `get_memory(memory_id)` | Retrieve a memory by ID |
| `update_memory(memory_id, properties)` | Update memory properties |
| `delete_memory(memory_id)` | Delete a memory |
| `search_memories(query, filters=None)` | Search by key/value content |
| `connect_memories(from_id, to_id, strength=1.0)` | Link related memories via `REFERENCES` |

### LogManager

| Method | Description |
|--------|-------------|
| `log(source_id, source_type, message, level=INFO, details=None)` | Create a log linked to an Agent or Tool |
| `get_logs(filters=None)` | Retrieve logs with optional filters |
| `search_logs(query)` | Search logs by message content |

### RelationshipManager

| Method | Description |
|--------|-------------|
| `create_relationship(from_id, from_type, to_id, to_type, rel_type, properties=None)` | Create any valid relationship |
| `get_relationship(from_id, to_id, rel_type)` | Get relationship details |
| `update_relationship(from_id, to_id, rel_type, properties)` | Update relationship properties |
| `delete_relationship(from_id, to_id, rel_type)` | Remove a relationship |
| `get_neighbors(node_id, rel_type=None, direction="outgoing")` | Find connected nodes |

### Orchestrator

| Method | Description |
|--------|-------------|
| `start_workflow(input_data, start_agent_id)` | Initialize a workflow execution |
| `execute_agent_chain(workflow)` | Run agents following `TRANSITIONS_TO` edges |
| `get_next_agent(current_agent_id, result=None)` | Resolve the next agent with condition evaluation |
| `visualize_workflow(workflow_id)` | Get a text summary of workflow execution |

## Enums

```python
AgentType:    REASONING | ROUTER | ASSISTANT | PLANNER | EXECUTOR | CRITIC
MemoryType:   LONG_TERM | SHORT_TERM | CONTEXT | EPISODIC | SEMANTIC
LogLevel:     DEBUG | INFO | WARNING | ERROR | CRITICAL
AgentStatus:  IDLE | RUNNING | PAUSED | ERROR | TERMINATED
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests (no Neo4j instance required — uses in-memory fake graph)
pytest
```

## License

MIT
