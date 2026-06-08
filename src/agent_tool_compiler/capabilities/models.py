from typing import Any, Literal

from pydantic import BaseModel, Field


class CapabilityParameter(BaseModel):
    name: str
    type: str = "str"
    default: Any = None
    description: str = ""


class WorkflowStep(BaseModel):
    type: Literal["tool"] = "tool"
    name: str
    tool_name: str
    args_template: dict[str, Any] = Field(default_factory=dict)


class Capability(BaseModel):
    name: str
    description: str
    parameters: list[CapabilityParameter] = Field(default_factory=list)
    workflow: list[WorkflowStep] = Field(default_factory=list)
    status: str = "active"
