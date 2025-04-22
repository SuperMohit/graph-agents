# Neo4j backed Agentic System




## Node Types

1. **Agent**
   - Represents an AI agent with specific capabilities
   - Properties: id, name, type, status, LLM configuration, etc.
   - Types can include: reasoning, router, assistant, etc.

2. **Tool**
   - External capabilities that agents can use
   - Properties: id, name, type, description, configuration
   - Examples: search tools, calculators, code execution, etc.

3. **Log**
   - Records of agent and tool operations
   - Properties: id, timestamp, level, message, execution details
   - Captures inputs, outputs, durations, errors

4. **Memory**
   - Persistent information storage
   - Properties: id, key, value, memory_type, priority, expiration
   - Types: long-term, short-term, context, etc.

## Key Relationships

1. **Agent → Tool**: `CAN_USE`
   - Defines which tools an agent has access to
   - Properties: priority, permissions

2. **Agent → Agent**: `DELEGATES_TO`
   - Allows agents to pass tasks to other specialized agents
   - Properties: condition, priority

3. **Agent → Log**: `GENERATED`
   - Records actions taken by agents

4. **Agent → Memory**: `STORES`
   - Agent writes information to memory

5. **Memory → Agent**: `INFORMS`
   - Memory provides context to agent operations
   - Properties: relevance_score

6. **Tool → Log**: `PRODUCED`
   - Tools generate logs of their operations

7. **Log → Memory**: `CONTRIBUTES_TO`
   - Logs can be processed to update memory
   - Properties: weight

8. **Agent → Agent**: `COMMUNICATES_WITH`
   - Direct communication between agents
   - Properties: protocol

9. **Memory → Memory**: `REFERENCES`
   - Links between related memory nodes
   - Properties: strength

10. **Agent → Agent**: `TRANSITIONS_TO`
    - Execution flow between agents
    - Properties: condition
