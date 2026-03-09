"""Core data models for NexusAgents."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AgentType(str, Enum):
    """Types of agents in the system."""

    REASONING = "reasoning"
    ROUTER = "router"
    ASSISTANT = "assistant"
    PLANNER = "planner"
    EXECUTOR = "executor"
    CRITIC = "critic"


class MemoryType(str, Enum):
    """Types of memory storage."""

    LONG_TERM = "long_term"
    SHORT_TERM = "short_term"
    CONTEXT = "context"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


class LogLevel(str, Enum):
    """Log severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AgentStatus(str, Enum):
    """Agent operational status."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    TERMINATED = "terminated"


class WorkflowStatus(str, Enum):
    """Workflow execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Agent:
    """Represents an AI agent with specific capabilities."""

    id: str
    name: str
    type: AgentType
    status: str = AgentStatus.IDLE.value
    config: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value if isinstance(self.type, AgentType) else self.type,
            "status": self.status,
            "config": json.dumps(self.config),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Agent:
        config = data.get("config", "{}")
        if isinstance(config, str):
            config = json.loads(config)
        agent_type = data.get("type", "assistant")
        if not isinstance(agent_type, AgentType):
            try:
                agent_type = AgentType(agent_type)
            except ValueError:
                agent_type = AgentType.ASSISTANT
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif not isinstance(created_at, datetime):
            created_at = datetime.utcnow()
        return cls(
            id=data["id"],
            name=data["name"],
            type=agent_type,
            status=data.get("status", AgentStatus.IDLE.value),
            config=config,
            created_at=created_at,
        )


@dataclass
class Tool:
    """External capability that agents can use."""

    id: str
    name: str
    type: str
    description: str
    function: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "function": self.function,
            "config": json.dumps(self.config),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tool:
        config = data.get("config", "{}")
        if isinstance(config, str):
            config = json.loads(config)
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif not isinstance(created_at, datetime):
            created_at = datetime.utcnow()
        return cls(
            id=data["id"],
            name=data["name"],
            type=data.get("type", ""),
            description=data.get("description", ""),
            function=data.get("function", ""),
            config=config,
            created_at=created_at,
        )


@dataclass
class Memory:
    """Persistent information storage node."""

    id: str
    key: str
    value: Any
    memory_type: MemoryType
    priority: int = 0
    expiration: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        value = self.value
        if not isinstance(value, str):
            value = json.dumps(value)
        return {
            "id": self.id,
            "key": self.key,
            "value": value,
            "memory_type": self.memory_type.value if isinstance(self.memory_type, MemoryType) else self.memory_type,
            "priority": self.priority,
            "expiration": self.expiration.isoformat() if self.expiration else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Memory:
        value = data.get("value", "")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass
        memory_type = data.get("memory_type", "short_term")
        if not isinstance(memory_type, MemoryType):
            try:
                memory_type = MemoryType(memory_type)
            except ValueError:
                memory_type = MemoryType.SHORT_TERM
        expiration = data.get("expiration")
        if isinstance(expiration, str):
            expiration = datetime.fromisoformat(expiration)
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif not isinstance(created_at, datetime):
            created_at = datetime.utcnow()
        return cls(
            id=data["id"],
            key=data["key"],
            value=value,
            memory_type=memory_type,
            priority=data.get("priority", 0),
            expiration=expiration,
            created_at=created_at,
        )


@dataclass
class Log:
    """Record of an agent or tool operation."""

    id: str
    message: str
    level: LogLevel
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "message": self.message,
            "level": self.level.value if isinstance(self.level, LogLevel) else self.level,
            "details": json.dumps(self.details),
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Log:
        details = data.get("details", "{}")
        if isinstance(details, str):
            details = json.loads(details)
        level = data.get("level", "info")
        if not isinstance(level, LogLevel):
            try:
                level = LogLevel(level)
            except ValueError:
                level = LogLevel.INFO
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif not isinstance(timestamp, datetime):
            timestamp = datetime.utcnow()
        return cls(
            id=data["id"],
            message=data.get("message", ""),
            level=level,
            details=details,
            timestamp=timestamp,
        )


@dataclass
class WorkflowExecution:
    """Represents a workflow run through the agent system."""

    id: str
    status: str = WorkflowStatus.PENDING.value
    input: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    agent_sequence: list[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "input": json.dumps(self.input),
            "result": json.dumps(self.result),
            "agent_sequence": json.dumps(self.agent_sequence),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowExecution:
        input_data = data.get("input", "{}")
        if isinstance(input_data, str):
            input_data = json.loads(input_data)
        result = data.get("result", "{}")
        if isinstance(result, str):
            result = json.loads(result)
        agent_sequence = data.get("agent_sequence", "[]")
        if isinstance(agent_sequence, str):
            agent_sequence = json.loads(agent_sequence)
        start_time = data.get("start_time")
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        elif not isinstance(start_time, datetime):
            start_time = datetime.utcnow()
        end_time = data.get("end_time")
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)
        return cls(
            id=data["id"],
            status=data.get("status", WorkflowStatus.PENDING.value),
            input=input_data,
            result=result,
            agent_sequence=agent_sequence,
            start_time=start_time,
            end_time=end_time,
        )
