from typing import Any

from agent_tool_compiler.capabilities.models import Capability
from agent_tool_compiler.tools.registry import ToolRegistry


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int | float):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


class _SQLFormatDict(dict):
    def __missing__(self, key: str) -> str:
        raise KeyError(f"Missing workflow parameter: {key}")

    def __getitem__(self, key: str) -> str:
        return sql_literal(super().__getitem__(key))


class WorkflowExecutor:
    def __init__(self, tool_registry: ToolRegistry, log_execution: bool = False) -> None:
        self.tool_registry = tool_registry
        self.log_execution = log_execution

    def execute(self, capability: Capability, params: dict[str, Any] | None = None) -> Any:
        runtime_params = {param.name: param.default for param in capability.parameters}
        runtime_params.update(params or {})
        context: dict[str, Any] = {}
        final_output: Any = None
        self._log_start(capability, runtime_params)
        try:
            for index, step in enumerate(capability.workflow, start=1):
                if step.type != "tool":
                    raise ValueError(f"Unsupported workflow step type: {step.type}")
                args = self._render_args(step.args_template, runtime_params | context)
                self._log_step(index, step.name, step.tool_name, args)
                final_output = self.tool_registry.invoke(step.tool_name, args)
                self._log_output(final_output)
                context[step.name] = final_output
            self._log_done(final_output)
            return final_output
        except Exception as exc:
            self._log_error(exc)
            raise

    def _render_args(self, value: Any, params: dict[str, Any]) -> Any:
        if isinstance(value, str):
            return value.format_map(_SQLFormatDict(params))
        if isinstance(value, dict):
            return {key: self._render_args(item, params) for key, item in value.items()}
        if isinstance(value, list):
            return [self._render_args(item, params) for item in value]
        return value

    def _log_start(self, capability: Capability, params: dict[str, Any]) -> None:
        if not self.log_execution:
            return
        print("\nCapability execution:")
        print(f"- name: {capability.name}")
        print(f"- params: {params}")

    def _log_step(self, index: int, step_name: str, tool_name: str, args: dict[str, Any]) -> None:
        if not self.log_execution:
            return
        print(f"- step {index}: {step_name}")
        print(f"  tool: {tool_name}")
        print(f"  args: {self._truncate(args)}")

    def _log_output(self, output: Any) -> None:
        if not self.log_execution:
            return
        print(f"  output: {self._truncate(output)}")

    def _log_done(self, final_output: Any) -> None:
        if not self.log_execution:
            return
        print(f"- result: {self._truncate(final_output)}\n")

    def _log_error(self, exc: Exception) -> None:
        if not self.log_execution:
            return
        print(f"- error: {exc.__class__.__name__}: {exc}\n")

    def _truncate(self, value: Any, limit: int = 1200) -> str:
        text = str(value)
        if len(text) <= limit:
            return text
        return f"{text[:limit]}... [truncated {len(text) - limit} chars]"
