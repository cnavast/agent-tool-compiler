import pytest

from agent_tool_compiler.capabilities.executor import WorkflowExecutor
from agent_tool_compiler.capabilities.models import Capability, CapabilityParameter, WorkflowStep
from agent_tool_compiler.capabilities.registry import CapabilityRegistry
from agent_tool_compiler.compiler.compiler import CapabilityCompiler
from agent_tool_compiler.compiler.validator import CapabilityValidator
from agent_tool_compiler.core.models import CompileCandidate, RunStep
from agent_tool_compiler.tools.registry import ToolRegistry


class FakeCompilerModel:
    def __init__(self, capability: Capability | list[Capability]) -> None:
        self.capabilities = capability if isinstance(capability, list) else [capability]
        self.calls = 0
        self.prompt = ""
        self.prompts = []

    def with_structured_output(self, schema, **kwargs):
        assert kwargs["method"] == "function_calling"
        return self

    def invoke(self, prompt):
        self.prompt = prompt
        self.prompts.append(prompt)
        capability = self.capabilities[min(self.calls, len(self.capabilities) - 1)]
        self.calls += 1
        return capability


class FakeSQLTool:
    name = "run_sql"

    def invoke(self, args):
        assert "{" not in args["query"]
        return "| carrier |\n| - |\n| DHL |"


def test_compiler_asks_llm_to_generate_capability_and_persists(tmp_path):
    model = FakeCompilerModel(
        Capability(
            name="calc_delays",
            description="Calculate delayed shipments by carrier.",
            parameters=[
                CapabilityParameter(name="country", default="IT"),
                CapabilityParameter(name="start_date", default="2026-06-06"),
                CapabilityParameter(name="end_date", default="2026-06-07"),
                CapabilityParameter(name="service", default="EXPRESS"),
            ],
            workflow=[
                WorkflowStep(
                    name="main_query",
                    tool_name="run_sql",
                    args_template={
                        "query": (
                            "select carrier, count(*) as delay_count from shipments s "
                            "join orders o on s.order_id = o.order_id "
                            "where o.country = {country} "
                            "and o.promised_delivery_date >= {start_date} "
                            "and o.promised_delivery_date < {end_date} "
                            "and o.service = {service} "
                            "group by carrier"
                        )
                    },
                )
            ],
        )
    )
    compiler = make_compiler(tmp_path, model)

    capability = compiler.compile(make_candidate())

    assert capability.name == "calc_delays"
    assert [param.name for param in capability.parameters] == [
        "country",
        "start_date",
        "end_date",
        "service",
    ]
    assert compiler.registry.load("calc_delays").name == "calc_delays"
    assert "Infer the user's reusable intent from the full conversation" in model.prompt
    assert "available_tools" in model.prompt
    assert "successful_tool_steps" in model.prompt
    assert "failed_tool_steps" in model.prompt
    assert "Do not bake parameter values into the tool name" in model.prompt
    assert "workflow[].tool_name must be copied exactly from available_tools" in model.prompt
    assert "qué transportistas tuvieron más retrasos ayer en Italia?" in model.prompt
    assert "y de estos cuantos eran express?" in model.prompt


def test_compiler_normalizes_tool_name_case_without_sql_alias_hacks(tmp_path):
    model = FakeCompilerModel(
        Capability(
            name="Calc Delays",
            description="Calculate delayed shipments.",
            parameters=[CapabilityParameter(name="country", default="IT")],
            workflow=[
                WorkflowStep(
                    name="main_query",
                    tool_name="RUN SQL",
                    args_template={"query": "select carrier from shipments where country = {country}"},
                )
            ],
        )
    )
    compiler = make_compiler(tmp_path, model)

    capability = compiler.compile(make_candidate())

    assert capability.name == "calc_delays"
    assert capability.workflow[0].tool_name == "run_sql"


def test_compiler_recovers_when_model_puts_tool_name_in_step_name(tmp_path):
    model = FakeCompilerModel(
        {
            "name": "calc_delays",
            "description": "Calculate delayed shipments.",
            "parameters": [CapabilityParameter(name="country", default="IT").model_dump()],
            "workflow": [
                {
                    "type": "tool",
                    "name": "run_sql",
                    "args_template": {"query": "select carrier from shipments where country = {country}"},
                }
            ],
        }
    )
    compiler = make_compiler(tmp_path, model)

    capability = compiler.compile(make_candidate())

    assert capability.workflow[0].tool_name == "run_sql"
    assert capability.workflow[0].name == "run_sql_1"


def test_compiler_rejects_unknown_tool_from_model(tmp_path):
    model = FakeCompilerModel(
        Capability(
            name="bad_tool",
            description="Bad tool.",
            workflow=[
                WorkflowStep(
                    name="main_query",
                    tool_name="query_database",
                    args_template={"query": "select 1"},
                )
            ],
        )
    )
    compiler = make_compiler(tmp_path, model)

    with pytest.raises(ValueError, match="unknown tool"):
        compiler.compile(make_candidate())


def test_compiler_repairs_missing_tool_name_when_not_deducible(tmp_path):
    bad_result = {
        "name": "calc_delays",
        "description": "Calculate delayed shipments.",
        "parameters": [CapabilityParameter(name="country", default="IT").model_dump()],
        "workflow": [
            {
                "type": "tool",
                "name": "main_query",
                "args_template": {"query": "select carrier from shipments where country = {country}"},
            }
        ],
    }
    repaired = Capability(
        name="calc_delays",
        description="Calculate delayed shipments.",
        parameters=[CapabilityParameter(name="country", default="IT")],
        workflow=[
            WorkflowStep(
                name="main_query",
                tool_name="run_sql",
                args_template={"query": "select carrier from shipments where country = {country}"},
            )
        ],
    )
    model = FakeCompilerModel([bad_result, repaired])
    compiler = make_compiler(tmp_path, model)

    capability = compiler.compile(make_candidate())

    assert capability.workflow[0].tool_name == "run_sql"
    assert model.calls == 2
    assert "missing tool_name" in model.prompts[1]


def test_compiler_rejects_exploration_steps_in_persisted_workflow(tmp_path):
    model = FakeCompilerModel(
        Capability(
            name="calc_delays",
            description="Calculate delayed shipments.",
            parameters=[CapabilityParameter(name="service", default="EXPRESS")],
            workflow=[
                WorkflowStep(
                    name="inspect_orders",
                    tool_name="describe_table",
                    args_template={"table_name": "orders"},
                ),
                WorkflowStep(
                    name="main_query",
                    tool_name="run_sql",
                    args_template={"query": "select * from orders where service = {service}"},
                ),
            ],
        )
    )
    compiler = make_compiler(tmp_path, model, include_describe_table=True)

    with pytest.raises(ValueError, match="does not feed a later step"):
        compiler.compile(make_candidate())


def test_compiler_rejects_manually_quoted_placeholders(tmp_path):
    model = FakeCompilerModel(
        Capability(
            name="calc_delays",
            description="Calculate delayed shipments.",
            parameters=[CapabilityParameter(name="service", default="EXPRESS")],
            workflow=[
                WorkflowStep(
                    name="main_query",
                    tool_name="run_sql",
                    args_template={"query": "select * from orders where service = '{service}'"},
                )
            ],
        )
    )
    compiler = make_compiler(tmp_path, model)

    with pytest.raises(ValueError, match="manually quoted"):
        compiler.compile(make_candidate())


def test_compiler_repairs_invalid_model_capability(tmp_path):
    bad_capability = Capability(
        name="calc_delays",
        description="Calculate delayed shipments.",
        parameters=[CapabilityParameter(name="service", default="EXPRESS")],
        workflow=[
            WorkflowStep(
                name="inspect_orders",
                tool_name="describe_table",
                args_template={"table_name": "orders"},
            ),
            WorkflowStep(
                name="main_query",
                tool_name="run_sql",
                args_template={"query": "select * from orders where service = {service}"},
            ),
        ],
    )
    repaired_capability = Capability(
        name="calc_delays",
        description="Calculate delayed shipments.",
        parameters=[CapabilityParameter(name="service", default="EXPRESS")],
        workflow=[
            WorkflowStep(
                name="main_query",
                tool_name="run_sql",
                args_template={"query": "select * from orders where service = {service}"},
            )
        ],
    )
    model = FakeCompilerModel([bad_capability, repaired_capability])
    compiler = make_compiler(tmp_path, model, include_describe_table=True)

    capability = compiler.compile(make_candidate())

    assert capability.workflow[0].tool_name == "run_sql"
    assert model.calls == 2
    assert "previous_invalid_capability" in model.prompts[1]
    assert "validation_error" in model.prompts[1]


def test_compiler_requires_semantic_model(tmp_path):
    compiler = make_compiler(tmp_path, None)

    with pytest.raises(ValueError, match="semantic_model is required"):
        compiler.compile(make_candidate())


def make_compiler(tmp_path, model, include_describe_table=False):
    tool_registry = ToolRegistry()
    tool_registry.register(FakeSQLTool())
    if include_describe_table:
        tool_registry.register(FakeDescribeTableTool())
    return CapabilityCompiler(
        semantic_model=model,
        registry=CapabilityRegistry(tmp_path / ".atc"),
        validator=CapabilityValidator(WorkflowExecutor(tool_registry)),
    )


class FakeDescribeTableTool:
    name = "describe_table"

    def invoke(self, args):
        return "order_id TEXT\nservice TEXT"


def make_candidate():
    return CompileCandidate(
        question="y de estos cuantos eran express?",
        messages=[
            {"type": "human", "content": "qué transportistas tuvieron más retrasos ayer en Italia?"},
            {"type": "ai", "content": "DHL, UPS y BRT tuvieron retrasos."},
            {"type": "human", "content": "y de estos cuantos eran express?"},
        ],
        steps=[
            RunStep(
                tool_name="run_sql",
                args={
                    "query": (
                        "select carrier, count(*) as delay_count from shipments s "
                        "join orders o on s.order_id = o.order_id "
                        "where o.country = 'IT' "
                        "and o.promised_delivery_date >= '2026-06-06' "
                        "and o.promised_delivery_date < '2026-06-07' "
                        "group by carrier"
                    )
                },
                output="| carrier | delay_count |\n| DHL | 5 |",
                success=True,
            ),
            RunStep(
                tool_name="run_sql",
                args={
                    "query": (
                        "select carrier, count(*) as delay_count from shipments s "
                        "join orders o on s.order_id = o.order_id "
                        "where o.country = 'IT' "
                        "and o.promised_delivery_date >= '2026-06-06' "
                        "and o.promised_delivery_date < '2026-06-07' "
                        "and o.service = 'EXPRESS' "
                        "group by carrier"
                    )
                },
                output="| carrier | delay_count |\n| DHL | 2 |",
                success=True,
            ),
        ],
        final_answer="DHL tuvo 2 retrasos express.",
    )
