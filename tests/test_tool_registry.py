from agent_tool_compiler.tools.registry import ToolRegistry


class FakeTool:
    name = "double"

    def invoke(self, args):
        return args["value"] * 2


def test_tool_registry_register_and_invoke():
    registry = ToolRegistry()
    registry.register(FakeTool())

    assert registry.get("double").name == "double"
    assert registry.invoke("double", {"value": 4}) == 8
