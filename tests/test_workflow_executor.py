from agent_tool_compiler.capabilities.executor import WorkflowExecutor
from agent_tool_compiler.capabilities.models import Capability, CapabilityParameter, WorkflowStep
from agent_tool_compiler.compiler.validator import CapabilityValidator
from agent_tool_compiler.tools.registry import ToolRegistry


class FakeSQLTool:
    name = "run_sql"

    def invoke(self, args):
        return args["query"]


class ErrorSQLTool:
    name = "run_sql"

    def invoke(self, args):
        return "SQL error: near \"EXPRESS\": syntax error"


def test_workflow_executor_renders_params_and_escapes_sql_literals():
    registry = ToolRegistry()
    registry.register(FakeSQLTool())
    executor = WorkflowExecutor(registry)
    capability = Capability(
        name="orders_by_country",
        description="Orders by country.",
        parameters=[
            CapabilityParameter(name="country", default="IT"),
            CapabilityParameter(name="start_date", default="2026-06-06"),
        ],
        workflow=[
            WorkflowStep(
                name="main_query",
                tool_name="run_sql",
                args_template={
                    "query": (
                        "select * from orders where country = {country} "
                        "and order_date >= {start_date}"
                    )
                },
            )
        ],
    )

    rendered = executor.execute(capability, {"country": "O'Reilly"})

    assert "country = 'O''Reilly'" in rendered
    assert "order_date >= '2026-06-06'" in rendered


def test_workflow_executor_can_log_capability_execution(capsys):
    registry = ToolRegistry()
    registry.register(FakeSQLTool())
    executor = WorkflowExecutor(registry, log_execution=True)
    capability = Capability(
        name="orders_by_country",
        description="Orders by country.",
        parameters=[CapabilityParameter(name="country", default="IT")],
        workflow=[
            WorkflowStep(
                name="main_query",
                tool_name="run_sql",
                args_template={"query": "select * from orders where country = {country}"},
            )
        ],
    )

    executor.execute(capability, {"country": "ES"})

    output = capsys.readouterr().out
    assert "Capability execution:" in output
    assert "- name: orders_by_country" in output
    assert "- params:" in output
    assert "tool: run_sql" in output
    assert "select * from orders where country = 'ES'" in output
    assert "- result:" in output


def test_capability_validator_rejects_sql_error_outputs():
    registry = ToolRegistry()
    registry.register(ErrorSQLTool())
    validator = CapabilityValidator(WorkflowExecutor(registry))
    capability = Capability(
        name="bad_sql",
        description="Bad SQL.",
        workflow=[
            WorkflowStep(
                name="main_query",
                tool_name="run_sql",
                args_template={"query": "select broken"},
            )
        ],
    )

    try:
        validator.validate(capability)
    except ValueError as exc:
        assert "SQL error" in str(exc)
    else:
        raise AssertionError("Expected SQL error validation failure.")
