import re
from typing import Any

from agent_tool_compiler.capabilities.models import Capability, WorkflowStep
from agent_tool_compiler.capabilities.registry import CapabilityRegistry
from agent_tool_compiler.compiler.models import CapabilitySpec
from agent_tool_compiler.compiler.validator import CapabilityValidator
from agent_tool_compiler.core.models import CompileCandidate, RunStep


COMPILER_RULES = """You are the Agent Tool Compiler.

Your job is to convert one successful agent execution into a reusable capability.

Think in this order:
1. Infer the user's reusable intent from the full conversation, not only the last message.
2. Observe how the agent actually solved that intent: which tools it called, in what order, with
   what arguments, which calls failed, which calls succeeded, and what outputs supported the answer.
3. Decide which tool calls are part of the reusable workflow and which were only exploration or
   repair. Keep the reusable workflow minimal but faithful.
   Schema inspection calls such as list_tables/describe_table are usually compile-time exploration;
   do not include them in the reusable workflow unless their output is consumed by a later runtime
   step through a placeholder/reference.
4. Generalize concrete user-specific values into parameters. If the user asked for Spain, generate
   a country-like parameter with default Spain. If the user asked for a service, status, category,
   id, threshold, boolean, or date, generalize that value when it is likely to vary in future runs.
5. For natural-language dates such as yesterday, last week, or between two dates, prefer reusable
   date parameters instead of one-off hardcoded dates. Choose names that fit the business concept.
6. Generate a concise snake_case tool name. Prefer clear action names such as calc_delays,
   rank_carriers_by_delay, get_orders_by_status, summarize_revenue, etc. Do not use the user's
   follow-up wording as the name.
7. Do not bake parameter values into the tool name or description. If EXPRESS becomes a service
   parameter, do not call the tool get_express_delays; use something like calc_delays_by_service.
   If Spain becomes a country parameter, do not call the tool get_spain_orders.
8. Generate a short useful description that says what the capability does, not how it was compiled,
   and describe the generalized parameters rather than the original concrete values.

Rules:
- Use only available tool names.
- workflow[].tool_name must be copied exactly from available_tools. Never invent helper tool names,
  subroutine names, or internal function names such as calculate_x, filter_y, transform_z.
  The capability.name is the reusable tool name; workflow step tool_name values are existing tools.
- Preserve the semantics of the successful execution.
- Do not invent filters or behavior that were not required by the conversation or successful tool
  execution.
- Every parameter must be used in the workflow.
- Every non-final workflow step must feed a later step; otherwise it was exploration and should be
  omitted.
- For this MVP, prefer a single runtime tool step whenever possible. If multiple independent SQL
  queries are needed, combine them into one run_sql query rather than storing unrelated run_sql
  steps whose outputs are not joined by the workflow.
- Use Python .format placeholders in workflow arg templates.
- Do not quote placeholders manually in SQL or other string templates when the runtime is expected
  to inject literal values. Correct: country = {country}. Wrong: country = '{country}'.
- Return structured data only."""


class CapabilityCompiler:
    def __init__(
        self,
        semantic_model: Any,
        registry: CapabilityRegistry,
        validator: CapabilityValidator,
    ) -> None:
        self.semantic_model = semantic_model
        self.registry = registry
        self.validator = validator

    def compile(self, candidate: CompileCandidate | dict[str, Any]) -> Capability:
        candidate = CompileCandidate.model_validate(candidate)
        if not self._successful_steps(candidate):
            raise ValueError("No successful tool steps found in compile candidate.")
        if self.semantic_model is None:
            raise ValueError("A semantic_model is required to compile a reusable capability.")

        capability = self._compile_and_validate(candidate)
        self.registry.save(capability)
        return capability

    def _compile_and_validate(self, candidate: CompileCandidate) -> Capability:
        previous_capability = None
        validation_error = None
        for attempt in range(2):
            capability = None
            try:
                capability = self._compile_with_model(
                    candidate,
                    previous_capability=previous_capability,
                    validation_error=validation_error,
                )
                capability = self._normalize_capability(capability)
                self.validator.validate(capability)
                return capability
            except ValueError as exc:
                previous_capability = capability
                validation_error = str(exc)
                if attempt == 1:
                    raise
        raise ValueError("Compiler model failed to produce a valid capability.")

    def _compile_with_model(
        self,
        candidate: CompileCandidate,
        previous_capability: Capability | None = None,
        validation_error: str | None = None,
    ) -> Capability:
        payload = self._build_payload(candidate)
        if previous_capability is not None:
            payload["previous_invalid_capability"] = previous_capability.model_dump()
        if validation_error is not None:
            payload["validation_error"] = validation_error
            payload["repair_instruction"] = (
                "The previous capability failed validation. Return a corrected capability. "
                "Do not repeat the same validation error."
            )
        prompt = f"{COMPILER_RULES}\n\nExecution payload:\n{payload}"
        try:
            if hasattr(self.semantic_model, "with_structured_output"):
                result = self.semantic_model.with_structured_output(
                    CapabilitySpec,
                    method="function_calling",
                ).invoke(prompt)
            elif hasattr(self.semantic_model, "invoke"):
                result = self.semantic_model.invoke(prompt)
            else:
                result = self.semantic_model(prompt)
            return self._capability_from_model_result(result)
        except Exception as exc:
            raise ValueError(f"Compiler model failed to produce a valid capability: {exc}") from exc

    def _capability_from_model_result(self, result: Any) -> Capability:
        if isinstance(result, Capability):
            return result
        spec = CapabilitySpec.model_validate(result)
        available_tools = set(self._available_tool_names())
        workflow = []
        for index, step in enumerate(spec.workflow, start=1):
            tool_name = step.tool_name
            step_name = step.name
            if not tool_name and step.name in available_tools:
                tool_name = step.name
                step_name = f"{self._slug(step.name)}_{index}"
            if not tool_name:
                raise ValueError(
                    f"Workflow step {step.name!r} is missing tool_name. "
                    "tool_name must be one of available_tools."
                )
            workflow.append(
                WorkflowStep(
                    type=step.type,
                    name=step_name,
                    tool_name=tool_name,
                    args_template=step.args_template,
                )
            )
        return Capability(
            name=spec.name,
            description=spec.description,
            parameters=spec.parameters,
            workflow=workflow,
            status=spec.status,
        )

    def _build_payload(self, candidate: CompileCandidate) -> dict[str, Any]:
        return {
            "available_tools": self._available_tool_names(),
            "conversation": self._conversation(candidate),
            "latest_user_question": candidate.question,
            "tool_steps": [step.model_dump() for step in candidate.steps],
            "successful_tool_steps": [step.model_dump() for step in self._successful_steps(candidate)],
            "failed_tool_steps": [step.model_dump() for step in candidate.steps if not step.success],
            "final_answer": candidate.final_answer,
            "llm_usage": candidate.llm_usage.model_dump(),
        }

    def _available_tool_names(self) -> list[str]:
        try:
            return self.validator.executor.tool_registry.names()
        except Exception:
            return []

    def _conversation(self, candidate: CompileCandidate) -> list[dict[str, str]]:
        conversation = []
        for message in candidate.messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            role = message.get("type") or message.get("role") or "message"
            conversation.append({"role": str(role), "content": content})
        return conversation

    def _successful_steps(self, candidate: CompileCandidate) -> list[RunStep]:
        return [step for step in candidate.steps if step.success]

    def _normalize_capability(self, capability: Capability) -> Capability:
        capability.name = self._slug(capability.name)
        if not capability.name:
            raise ValueError("Compiled capability must have a name.")
        if not capability.workflow:
            raise ValueError("Compiled capability must include at least one workflow step.")

        available_tools = set(self._available_tool_names())
        for step in capability.workflow:
            step.tool_name = self._normalize_tool_name(step.tool_name, available_tools)
        return capability

    def _normalize_tool_name(self, tool_name: str, available_tools: set[str]) -> str:
        if tool_name in available_tools:
            return tool_name
        normalized = self._slug(tool_name)
        for available in available_tools:
            if self._slug(available) == normalized:
                return available
        raise ValueError(
            f"Compiled capability references unknown tool {tool_name!r}. "
            f"Available tools: {sorted(available_tools)}"
        )

    def _slug(self, text: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
