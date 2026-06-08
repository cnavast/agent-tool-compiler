from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from agent_tool_compiler.capabilities.executor import WorkflowExecutor
from agent_tool_compiler.capabilities.registry import CapabilityRegistry
from agent_tool_compiler.tools.registry import ToolRegistry


def _demo_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    try:
        from examples.langgraph_data_agent.tools import describe_table, list_tables, run_sql

        registry.register_many([list_tables, describe_table, run_sql])
    except Exception:
        pass
    return registry


def serve_mcp(project_dir: str | Path = ".atc") -> None:
    capability_registry = CapabilityRegistry(project_dir)
    tool_registry = _demo_tool_registry()
    executor = WorkflowExecutor(tool_registry)
    server = FastMCP("agent-tool-compiler")

    for capability in capability_registry.list():

        def make_runner(cap=capability):
            def runner(**kwargs: Any) -> Any:
                return executor.execute(cap, kwargs)

            runner.__name__ = cap.name
            runner.__doc__ = cap.description
            return runner

        server.tool(name=capability.name, description=capability.description)(make_runner())

    server.run()
