from collections.abc import Iterable
from typing import Any


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}

    @staticmethod
    def tool_name(tool: Any) -> str:
        return getattr(tool, "name", None) or getattr(tool, "__name__", tool.__class__.__name__)

    def register(self, tool: Any) -> Any:
        self._tools[self.tool_name(tool)] = tool
        return tool

    def register_many(self, tools: Iterable[Any]) -> None:
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Any:
        if name not in self._tools:
            raise KeyError(f"Tool not registered: {name}")
        return self._tools[name]

    def invoke(self, name: str, args: dict[str, Any]) -> Any:
        tool = self.get(name)
        if hasattr(tool, "invoke"):
            return tool.invoke(args)
        return tool(**args)

    def names(self) -> list[str]:
        return sorted(self._tools)
