from pathlib import Path

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
