from __future__ import annotations

from pathlib import Path

from ai_ops.models import AgentResult
from ai_ops.process import run


class CodexAgent:
    name = "codex"

    def __init__(
        self,
        command: tuple[str, ...] = (
            "codex",
            "exec",
            "-m",
            "gpt-5.2",
            "-c",
            'model_reasoning_effort="high"',
            "--sandbox",
            "read-only",
            "-",
        ),
    ) -> None:
        self.command = command

    def run(self, prompt: str, *, cwd: Path) -> AgentResult:
        result = run(list(self.command), cwd=cwd, input_text=prompt)
        return AgentResult(text=result.stdout, command=self.command)
