# Neo4j Agents - Graph-Based Agentic Framework

A Python library for building, managing, and orchestrating AI agent systems using Neo4j as the underlying database for agents, tools, memory, and logging.

## Architecture

The library is designed around a graph-based architecture where agent relationships, memory, and execution paths are all stored in Neo4j.

### Class Diagram

```mermaid
classDiagram
    class Neo4jAgentSystem {
        -GraphDatabase driver
        +initialize_schema()
        +close()
        +create_agent(name, agent_type, config) string
        +create_tool(name, tool_type, description, function, config) string
        +create_memory(key, value, memory_type, priority, expiration) string
        +log(agent_id, message, level, details, tool_id) string
        +connect_agent_to_tool(agent_id, tool_id, priority, permissions)
        +connect_agent_to_agent(from_agent_id, to_agent_id, relationship_type, properties)
        +connect_agent_to_memory(agent_id, memory_id, relationship_type, properties)
        +connect_memory_to_memory(from_memory_id, to_memory_id, strength)
        +get_agent(agent_id) Agent
        +get_tool(tool_id) Tool
        +get_memory(memory_id) Memory
    }

    class Agent {
        +id string
        +name string
        +type AgentType
        +status string
        +config Dict
        +created_at datetime
        +run(input, context) Result
        +get_available_tools() List~Tool~
        +delegate(task, agent_id) Result
        +store_memory(key, value, memory_type) string
        +retrieve_memory(query) List~Memory~
    }

    class Tool {
        +id string
        +name string
        +type string
        +description string
        +function string
        +config Dict
        +created_at datetime
        +execute(params) Result
    }

    class Memory {
        +id string
        +key string
        +value Any
        +memory_type MemoryType
        +priority int
        +expiration datetime
        +created_at datetime
    }

    class Log {
        +id string
        +message string
        +level LogLevel
        +details Dict
        +timestamp datetime
    }

    class Orchestrator {
        +agent_system Neo4jAgentSystem
        +start_workflow(input_data, start_agent_id) WorkflowExecution
        +get_next_agent(current_agent_id, result) string
        +execute_agent_chain(workflow) Result
        +visualize_workflow(workflow_id) string
    }

    class WorkflowExecution {
        +id string
        +start_time datetime
        +end_time datetime
        +status string
        +input Dict
        +result Dict
        +agent_sequence List~string~
    }

    Neo4jAgentSystem --> Agent : creates/manages
    Neo4jAgentSystem --> Tool : creates/manages
    Neo4jAgentSystem --> Memory : creates/manages
    Neo4jAgentSystem --> Log : creates/manages
    Agent --> Tool : uses
    Agent --> Memory : reads/writes
    Agent --> Log : generates
    Tool --> Log : produces
    Orchestrator --> Neo4jAgentSystem : uses
    Orchestrator --> WorkflowExecution : manages
```

## Key Features

- **Dynamic Agent Orchestration**: Agent sequences adapt based on input or previous outcomes
- **System Introspection & Monitoring**: Every step in agent processing is tracked in the graph
- **Decentralized Configuration**: Agent behaviors and connections are defined as graph properties
- **Comprehensive Logging & Debugging**: Logs connected directly to relevant agents, tools, and memory
- **Scalable Multi-Agent Design**: Easily add new agent types for specific functions
