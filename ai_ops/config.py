from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AgentConfig:
    default: str = "prompt-only"
    commands: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _user_config_path() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "ai-ops" / "config.toml"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ai-ops" / "config.toml"


def _load_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_agent_config(root: Path, *, override: str | None = None) -> AgentConfig:
    data: dict = {}
    for path in (_user_config_path(), root / "ai-ops.toml"):
        loaded = _load_toml(path)
        data = _merge(data, loaded)

    default = override or data.get("agent", {}).get("default") or "prompt-only"
    agents = data.get("agents", {})
    commands: dict[str, tuple[str, ...]] = {}
    for name, value in agents.items():
        command = value.get("command") if isinstance(value, dict) else None
        if isinstance(command, list) and all(isinstance(part, str) for part in command):
            commands[name] = tuple(command)

    commands.setdefault("claude", ("claude", "-p", "--no-session-persistence", "--tools", ""))
    commands.setdefault(
        "codex",
        (
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
    )
    return AgentConfig(default=default, commands=commands)


def _merge(base: dict, incoming: dict) -> dict:
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged
