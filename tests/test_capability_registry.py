from agent_tool_compiler.capabilities.models import Capability, CapabilityParameter, WorkflowStep
from agent_tool_compiler.capabilities.registry import CapabilityRegistry


def test_capability_registry_save_load_delete(tmp_path):
    registry = CapabilityRegistry(tmp_path / ".atc")
    capability = Capability(
        name="get_late_shipments",
        description="Rank late shipments.",
        parameters=[CapabilityParameter(name="country", default="IT")],
        workflow=[
            WorkflowStep(name="main_query", tool_name="run_sql", args_template={"query": "select 1"})
        ],
    )

    registry.save(capability)

    loaded = registry.load("get_late_shipments")
    assert loaded.name == "get_late_shipments"
    assert registry.list()[0].description == "Rank late shipments."
    assert registry.delete("get_late_shipments") is True
    assert registry.list() == []
