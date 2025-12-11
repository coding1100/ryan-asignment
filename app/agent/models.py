from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    """Minimal tool metadata passed to the LLM."""

    name: str
    description: str
    input_schema: dict[str, Any]


class ToolAction(BaseModel):
    """One tool invocation that the LLM wants to execute."""

    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reasoning: Optional[str] = None


class ToolExecution(BaseModel):
    """Execution record for a tool call."""

    step: int
    tool: str
    arguments: dict[str, Any]
    status: Literal["success", "error"]
    output: Any = None
    error: Optional[str] = None
    reasoning: Optional[str] = None


class AgentResult(BaseModel):
    """Structured output returned to API consumers."""

    status: Literal["success", "partial", "error"]
    output: Any
    trace: list[ToolExecution] = Field(default_factory=list)
    notes: Optional[str] = None


class PlanResponse(BaseModel):
    """LLM-produced plan for the agent."""

    actions: list[ToolAction] = Field(default_factory=list)
    direct_response: Optional[str] = Field(
        default=None,
        description="If present, the agent can answer without tools.",
    )
    reasoning: Optional[str] = None
