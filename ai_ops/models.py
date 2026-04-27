from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentResult:
    text: str
    command: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ProjectSpec:
    name: str
    purpose: str
    tier: str
    project_type: str
    nix_level: str
    output: Path | None = None


@dataclass(frozen=True)
class MigrationSpec:
    source: Path
    tier: str
    nix_level: str
    output: Path | None = None
