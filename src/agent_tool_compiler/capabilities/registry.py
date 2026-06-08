import json
from pathlib import Path

from agent_tool_compiler.capabilities.models import Capability


class CapabilityRegistry:
    def __init__(self, project_dir: str | Path = ".atc") -> None:
        self.project_dir = Path(project_dir)
        self.capabilities_dir = self.project_dir / "capabilities"
        self.registry_path = self.project_dir / "registry.json"
        self.capabilities_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_registry()

    def _ensure_registry(self) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self.registry_path.write_text(json.dumps({"capabilities": []}, indent=2), encoding="utf-8")

    def save(self, capability: Capability) -> Capability:
        path = self.capabilities_dir / f"{capability.name}.json"
        path.write_text(capability.model_dump_json(indent=2), encoding="utf-8")
        registry = self._read_registry()
        entries = [item for item in registry["capabilities"] if item["name"] != capability.name]
        entries.append(
            {
                "name": capability.name,
                "description": capability.description,
                "status": capability.status,
                "path": str(path),
            }
        )
        registry["capabilities"] = sorted(entries, key=lambda item: item["name"])
        self.registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        return capability

    def load(self, name: str) -> Capability:
        return Capability.model_validate_json(
            (self.capabilities_dir / f"{name}.json").read_text(encoding="utf-8")
        )

    def list(self, active_only: bool = True) -> list[Capability]:
        capabilities = []
        for path in sorted(self.capabilities_dir.glob("*.json")):
            capability = Capability.model_validate_json(path.read_text(encoding="utf-8"))
            if not active_only or capability.status == "active":
                capabilities.append(capability)
        return capabilities

    def delete(self, name: str) -> bool:
        path = self.capabilities_dir / f"{name}.json"
        existed = path.exists()
        if existed:
            path.unlink()
        registry = self._read_registry()
        registry["capabilities"] = [
            item for item in registry["capabilities"] if item["name"] != name
        ]
        self.registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        return existed

    def _read_registry(self) -> dict:
        self._ensure_registry()
        return json.loads(self.registry_path.read_text(encoding="utf-8"))
