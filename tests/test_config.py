from pathlib import Path

import pytest

from ai_ops.config import load_agent_config


def test_override_agent_wins(tmp_path: Path) -> None:
    config = load_agent_config(tmp_path, override="codex")
    assert config.default == "codex"


def test_builtin_agent_commands_are_non_interactive(tmp_path: Path) -> None:
    config = load_agent_config(tmp_path)
    assert config.commands["claude"] == ("claude", "-p", "--no-session-persistence", "--tools", "")
    assert config.commands["codex"] == (
        "codex",
        "exec",
        "-m",
        "gpt-5.2",
        "-c",
        'model_reasoning_effort="high"',
        "--sandbox",
        "read-only",
        "-",
    )


def test_repo_local_config_overrides_default(tmp_path: Path) -> None:
    (tmp_path / "ai-ops.toml").write_text(
        '[agent]\ndefault = "codex"\n',
        encoding="utf-8",
    )
    config = load_agent_config(tmp_path)
    assert config.default == "codex"


def test_cli_override_beats_repo_local_config(tmp_path: Path) -> None:
    (tmp_path / "ai-ops.toml").write_text(
        '[agent]\ndefault = "codex"\n',
        encoding="utf-8",
    )
    config = load_agent_config(tmp_path, override="prompt-only")
    assert config.default == "prompt-only"


def test_repo_local_can_register_custom_agent(tmp_path: Path) -> None:
    (tmp_path / "ai-ops.toml").write_text(
        '[agents.fake]\ncommand = ["echo", "hi"]\n',
        encoding="utf-8",
    )
    config = load_agent_config(tmp_path)
    assert config.commands["fake"] == ("echo", "hi")


def test_repo_local_overrides_builtin_command(tmp_path: Path) -> None:
    (tmp_path / "ai-ops.toml").write_text(
        '[agents.claude]\ncommand = ["claude", "-p"]\n',
        encoding="utf-8",
    )
    config = load_agent_config(tmp_path)
    assert config.commands["claude"] == ("claude", "-p")


def test_invalid_command_type_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "ai-ops.toml").write_text(
        '[agents.bad]\ncommand = "single string"\n',
        encoding="utf-8",
    )
    config = load_agent_config(tmp_path)
    assert "bad" not in config.commands
