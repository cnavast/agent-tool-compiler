from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_tool_compiler.capabilities.models import CapabilityParameter


class WorkflowStepSpec(BaseModel):
    type: Literal["tool"] = "tool"
    name: str
    tool_name: str | None = None
    args_template: dict[str, Any] = Field(default_factory=dict)


class CapabilitySpec(BaseModel):
    name: str
    description: str
    parameters: list[CapabilityParameter] = Field(default_factory=list)
    workflow: list[WorkflowStepSpec] = Field(default_factory=list)
    status: str = "active"
