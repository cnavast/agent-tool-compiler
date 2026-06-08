from pathlib import Path

from pydantic import BaseModel


class ATCConfig(BaseModel):
    project_dir: Path = Path(".atc")

    @property
    def capabilities_dir(self) -> Path:
        return self.project_dir / "capabilities"

    @property
    def registry_path(self) -> Path:
        return self.project_dir / "registry.json"
