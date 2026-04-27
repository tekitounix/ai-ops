from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ai_ops.models import AgentResult


class Agent(Protocol):
    name: str

    def run(self, prompt: str, *, cwd: Path) -> AgentResult:
        ...
