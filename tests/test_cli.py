import pytest
import sys
from pathlib import Path

from ai_ops.cli import main


def test_help_runs() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_new_requires_name() -> None:
    assert main(["new", "--purpose", "x"]) == 2


def test_new_prompt_only_runs() -> None:
    assert main(["new", "sample", "--purpose", "x", "--agent", "prompt-only", "--dry-run"]) == 0


def test_execute_approved_is_not_part_of_cli() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["new", "sample", "--purpose", "x", "--execute-approved", "run"])
    assert exc.value.code == 2


def _write_minimal_root(root: Path) -> None:
    (root / "AGENTS.md").write_text("# test\n", encoding="utf-8")
    brief_dir = root / "templates"
    brief_dir.mkdir(parents=True)
    for name in ("project-brief.md", "migration-brief.md"):
        (brief_dir / name).write_text(
            "Fact\nInference\nRisk\nUser decision\nAI recommendation\n",
            encoding="utf-8",
        )


def test_configured_subprocess_agent_receives_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _write_minimal_root(tmp_path)
    fake_agent = tmp_path / "fake_agent.py"
    fake_agent.write_text(
        "import sys\n"
        "prompt = sys.stdin.read()\n"
        "print('FAKE_AGENT_OK')\n"
        "print('HAS_PROJECT=' + str('sample' in prompt))\n",
        encoding="utf-8",
    )
    (tmp_path / "ai-ops.toml").write_text(
        "[agent]\n"
        'default = "fake"\n'
        "[agents.fake]\n"
        f"command = ['{sys.executable}', '{fake_agent}']\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert main(["new", "sample", "--purpose", "x"]) == 0
    out = capsys.readouterr().out
    assert "FAKE_AGENT_OK" in out
    assert "HAS_PROJECT=True" in out


def test_migration_discovery_reports_secret_names_not_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _write_minimal_root(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("sample project\n", encoding="utf-8")
    (source / ".env").write_text("API_TOKEN=placeholder-value\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["migrate", str(source), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "secret_looking_names: .env" in out
    assert "placeholder-value" not in out


def test_security_audit_rejects_secret_named_files(tmp_path: Path) -> None:
    from ai_ops.audit.security import run_security_audit

    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
    (tmp_path / ".env").write_text("API_TOKEN=placeholder-value\n", encoding="utf-8")

    assert run_security_audit(tmp_path) == 1


def test_audit_lifecycle_targets_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["audit", "lifecycle"]) == 1


def test_audit_security_detects_env_in_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("API_TOKEN=fake\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["audit", "security"]) == 1


def test_check_targets_cwd_and_fails_outside_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 1
