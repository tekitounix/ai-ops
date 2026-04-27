from __future__ import annotations

from pathlib import Path

from ai_ops.models import AgentResult


class PromptOnlyAgent:
    name = "prompt-only"

    def run(self, prompt: str, *, cwd: Path) -> AgentResult:
        return AgentResult(text=prompt, command=None)
