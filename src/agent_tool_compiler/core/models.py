from typing import Any

from pydantic import BaseModel, Field


class LLMUsage(BaseModel):
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0


class RunStep(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    output: Any = None
    success: bool = True


class CompileCandidate(BaseModel):
    question: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[RunStep] = Field(default_factory=list)
    llm_usage: LLMUsage = Field(default_factory=LLMUsage)
    final_answer: str = ""


class ATCSummary(BaseModel):
    tool_names: list[str]
    total_tokens: int
    output_tokens: int
    final_answer_tokens: int
    work_to_answer_ratio: str


class DecoratedResponse(BaseModel):
    answer: str
    atc: dict[str, Any]
