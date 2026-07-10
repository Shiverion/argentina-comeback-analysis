from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    """Canonical filesystem layout for immutable inputs and derived outputs."""

    root: Path

    @property
    def config_file(self) -> Path:
        return self.root / "config" / "sources.json"

    @property
    def reference_dir(self) -> Path:
        return self.root / "data" / "reference"

    @property
    def raw_dir(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.root / "data" / "processed"

    @property
    def manifests_dir(self) -> Path:
        return self.root / "data" / "manifests"

    @property
    def quarantine_dir(self) -> Path:
        return self.root / "data" / "quarantine"

    @property
    def results_dir(self) -> Path:
        return self.root / "results"

    def ensure_directories(self) -> None:
        for directory in (
            self.raw_dir,
            self.processed_dir,
            self.manifests_dir,
            self.quarantine_dir,
            self.results_dir,
            self.raw_dir / "manual",
            self.raw_dir / "fifa",
            self.raw_dir / "focal",
            self.raw_dir / "fjelstul",
            self.raw_dir / "jgravier",
            self.raw_dir / "statsbomb",
        ):
            directory.mkdir(parents=True, exist_ok=True)
