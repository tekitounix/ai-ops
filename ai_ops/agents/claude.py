from __future__ import annotations

from pathlib import Path

from ai_ops.models import AgentResult
from ai_ops.process import run


class ClaudeAgent:
    name = "claude"

    def __init__(self, command: tuple[str, ...] = ("claude", "-p", "--no-session-persistence", "--tools", "")) -> None:
        self.command = command

    def run(self, prompt: str, *, cwd: Path) -> AgentResult:
        result = run(list(self.command), cwd=cwd, input_text=prompt)
        return AgentResult(text=result.stdout, command=self.command)
