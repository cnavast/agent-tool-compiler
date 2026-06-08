from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

from agent_tool_compiler.capabilities.executor import WorkflowExecutor
from agent_tool_compiler.capabilities.models import Capability
from agent_tool_compiler.capabilities.registry import CapabilityRegistry
from agent_tool_compiler.compiler.compiler import CapabilityCompiler
from agent_tool_compiler.compiler.validator import CapabilityValidator
from agent_tool_compiler.core.models import CompileCandidate, LLMUsage, RunStep
from agent_tool_compiler.tools.registry import ToolRegistry


class ATC:
    def __init__(self, project_dir: str = ".atc", semantic_model: Any = None) -> None:
        self.project_dir = project_dir
        self.semantic_model = semantic_model
        self.tool_registry = ToolRegistry()
        self.capability_registry = CapabilityRegistry(project_dir)

    def tools(self, base_tools: list[Any]) -> list[Any]:
        self.tool_registry.register_many(base_tools)
        generated = [self._capability_tool(capability) for capability in self.capability_registry.list()]
        self.tool_registry.register_many(generated)
        return [*base_tools, *generated]

    def decorate_response(self, question: str, agent_result: Any) -> dict[str, Any]:
        messages = self._extract_messages(agent_result)
        answer = self._final_answer(messages, agent_result)
        steps = self._extract_steps(messages)
        usage = self._extract_usage(messages, agent_result)
        final_answer_tokens = max(len(answer.split()), 1)
        ratio = round(usage.total_tokens / final_answer_tokens) if usage.total_tokens else 0
        tool_names = []
        for step in steps:
            if step.tool_name not in tool_names:
                tool_names.append(step.tool_name)
        candidate = CompileCandidate(
            question=question,
            messages=[self._message_to_dict(message) for message in messages],
            steps=steps,
            llm_usage=usage,
            final_answer=answer,
        )
        return {
            "answer": answer,
            "atc": {
                "can_compile": any(step.tool_name == "run_sql" and step.success for step in steps),
                "candidate": candidate.model_dump(),
                "summary": {
                    "tool_names": tool_names,
                    "total_tokens": usage.total_tokens,
                    "output_tokens": usage.total_output_tokens,
                    "final_answer_tokens": final_answer_tokens,
                    "work_to_answer_ratio": f"{ratio}x",
                },
            },
        }

    def compile(self, candidate: CompileCandidate | dict[str, Any]) -> Capability:
        executor = WorkflowExecutor(self.tool_registry)
        compiler = CapabilityCompiler(
            semantic_model=self.semantic_model,
            registry=self.capability_registry,
            validator=CapabilityValidator(executor),
        )
        return compiler.compile(candidate)

    def _capability_tool(self, capability: Capability) -> StructuredTool:
        fields = {
            param.name: (
                str,
                Field(default=param.default, description=param.description),
            )
            for param in capability.parameters
        }
        args_schema = create_model(f"{capability.name}_args", **fields)

        def run_capability(**kwargs: Any) -> Any:
            executor = WorkflowExecutor(self.tool_registry)
            return executor.execute(capability, kwargs)

        return StructuredTool.from_function(
            func=run_capability,
            name=capability.name,
            description=capability.description,
            args_schema=args_schema,
        )

    def _extract_messages(self, agent_result: Any) -> list[Any]:
        if isinstance(agent_result, dict):
            return list(agent_result.get("messages", []))
        return list(getattr(agent_result, "messages", []))

    def _final_answer(self, messages: list[Any], agent_result: Any) -> str:
        for message in reversed(messages):
            content = getattr(message, "content", None)
            tool_calls = getattr(message, "tool_calls", None) or []
            if content and not tool_calls:
                return str(content)
        if isinstance(agent_result, dict):
            return str(agent_result.get("output", ""))
        return str(agent_result)

    def _extract_steps(self, messages: list[Any]) -> list[RunStep]:
        pending: dict[str, dict[str, Any]] = {}
        steps: list[RunStep] = []
        for message in messages:
            for call in getattr(message, "tool_calls", None) or []:
                call_id = call.get("id") or call.get("name")
                pending[call_id] = {"tool_name": call.get("name"), "args": call.get("args") or {}}
            msg_type = getattr(message, "type", "")
            if msg_type == "tool" or message.__class__.__name__ == "ToolMessage":
                name = getattr(message, "name", None)
                tool_call_id = getattr(message, "tool_call_id", None)
                data = pending.pop(tool_call_id, {"tool_name": name, "args": {}})
                output = getattr(message, "content", "")
                steps.append(
                    RunStep(
                        tool_name=data.get("tool_name") or name or "unknown_tool",
                        args=data.get("args") or {},
                        output=output,
                        success=not str(output).lower().startswith("sql error"),
                    )
                )
        return steps

    def _extract_usage(self, messages: list[Any], agent_result: Any) -> LLMUsage:
        usage = LLMUsage()
        for message in messages:
            meta = getattr(message, "usage_metadata", None) or {}
            usage.total_input_tokens += int(meta.get("input_tokens", 0) or 0)
            usage.total_output_tokens += int(meta.get("output_tokens", 0) or 0)
            usage.total_tokens += int(meta.get("total_tokens", 0) or 0)
            response_meta = getattr(message, "response_metadata", None) or {}
            token_usage = response_meta.get("token_usage") or {}
            usage.total_input_tokens += int(token_usage.get("prompt_tokens", 0) or 0)
            usage.total_output_tokens += int(token_usage.get("completion_tokens", 0) or 0)
            usage.total_tokens += int(token_usage.get("total_tokens", 0) or 0)
        if isinstance(agent_result, dict):
            raw = agent_result.get("llm_usage") or {}
            usage.total_input_tokens += int(raw.get("total_input_tokens", 0) or 0)
            usage.total_output_tokens += int(raw.get("total_output_tokens", 0) or 0)
            usage.total_tokens += int(raw.get("total_tokens", 0) or 0)
        if usage.total_tokens == 0:
            usage.total_tokens = usage.total_input_tokens + usage.total_output_tokens
        return usage

    def _message_to_dict(self, message: Any) -> dict[str, Any]:
        if hasattr(message, "model_dump"):
            return message.model_dump()
        return {
            "type": getattr(message, "type", message.__class__.__name__),
            "content": getattr(message, "content", str(message)),
            "name": getattr(message, "name", None),
        }
