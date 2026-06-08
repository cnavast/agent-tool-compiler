import re
from typing import Any

from agent_tool_compiler.capabilities.executor import WorkflowExecutor
from agent_tool_compiler.capabilities.models import Capability


class CapabilityValidator:
    def __init__(self, executor: WorkflowExecutor) -> None:
        self.executor = executor

    def validate(self, capability: Capability) -> None:
        self._validate_templates(capability)
        self._validate_step_flow(capability)
        params = {param.name: param.default for param in capability.parameters}
        output = self.executor.execute(capability, params)
        if isinstance(output, str) and output.lower().startswith("sql error"):
            raise ValueError(f"Capability validation failed: {output}")

    def _validate_templates(self, capability: Capability) -> None:
        parameter_names = {param.name for param in capability.parameters}
        rendered_text = "\n".join(self._strings_from_value(step.args_template) for step in capability.workflow)
        for name in parameter_names:
            if f"{{{name}}}" not in rendered_text:
                raise ValueError(f"Capability parameter {name!r} is not used in the workflow.")
            quoted_placeholder = re.compile(rf"(['\"])\{{{re.escape(name)}\}}\1")
            if quoted_placeholder.search(rendered_text):
                raise ValueError(
                    f"Placeholder {{{name}}} is manually quoted. "
                    "Templates must leave quoting to the runtime."
                )

    def _validate_step_flow(self, capability: Capability) -> None:
        for index, step in enumerate(capability.workflow[:-1]):
            later_values = "\n".join(
                self._strings_from_value(later_step.args_template)
                for later_step in capability.workflow[index + 1 :]
            )
            if f"{{{step.name}}}" not in later_values:
                raise ValueError(
                    f"Workflow step {step.name!r} does not feed a later step. "
                    "Exploration steps should not be persisted in capabilities."
                )

    def _strings_from_value(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return "\n".join(self._strings_from_value(item) for item in value.values())
        if isinstance(value, list):
            return "\n".join(self._strings_from_value(item) for item in value)
        return ""
