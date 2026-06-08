import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agent_tool_compiler.capabilities.registry import CapabilityRegistry
from agent_tool_compiler.mcp.server import serve_mcp

app = typer.Typer(help="ATC: Agent Tool Compiler")
console = Console()


@app.command()
def inspect(project_dir: str = ".atc") -> None:
    registry = CapabilityRegistry(project_dir)
    table = Table(title=f"ATC capabilities in {project_dir}")
    table.add_column("Name")
    table.add_column("Description")
    table.add_column("Params")
    table.add_column("Status")
    for capability in registry.list(active_only=False):
        params = ", ".join(param.name for param in capability.parameters)
        table.add_row(capability.name, capability.description, params, capability.status)
    console.print(table)


@app.command()
def delete(name: str, project_dir: str = ".atc") -> None:
    registry = CapabilityRegistry(project_dir)
    if registry.delete(name):
        console.print(f"Deleted {name}")
    else:
        console.print(f"No capability named {name}")


@app.command("serve-mcp")
def serve_mcp_command(project_dir: str = ".atc") -> None:
    serve_mcp(project_dir)


@app.command("compile-candidate")
def compile_candidate(path: Path, project_dir: str = ".atc") -> None:
    from agent_tool_compiler import ATC

    candidate = json.loads(path.read_text(encoding="utf-8"))
    capability = ATC(project_dir=project_dir).compile(candidate["candidate"])
    console.print(f"Compiled {capability.name}")
