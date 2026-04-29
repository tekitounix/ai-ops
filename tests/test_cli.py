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


def test_audit_lifecycle_passes_on_real_ai_ops_repo() -> None:
    """End-to-end happy path: ai-ops's own self-audit must pass on its own
    repository. Without this, only failure paths are exercised, and we'd never
    notice if a future change made the success path silently impossible."""
    from ai_ops.audit.lifecycle import run_lifecycle_audit

    repo = Path(__file__).resolve().parents[1]
    assert run_lifecycle_audit(repo) == 0


def test_audit_security_detects_env_in_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("API_TOKEN=fake\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["audit", "security"]) == 1


def test_check_targets_cwd_and_fails_outside_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 1


def test_new_prompt_embeds_agents_md_rules(capsys: pytest.CaptureFixture[str]) -> None:
    main(["new", "sample", "--purpose", "x", "--agent", "prompt-only", "--dry-run"])
    out = capsys.readouterr().out
    assert "Operating rules (from ai-ops AGENTS.md" in out
    assert "ghq" in out
    assert "Propose -> Confirm -> Execute" in out


def test_migrate_prompt_embeds_agents_md_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("legacy\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    main(["migrate", str(source), "--dry-run", "--agent", "prompt-only"])
    out = capsys.readouterr().out
    assert "Operating rules (from ai-ops AGENTS.md" in out
    assert "ghq" in out


def test_new_prompt_embeds_brief_template_and_nix_rubric(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end content sanity: the prompt assembled for `ai-ops new` must
    include (a) AGENTS.md operating rules, (b) the NIX_RUBRIC stage table,
    and (c) the project-brief template's section headers. Without all three
    an AI agent receives an underspecified prompt."""
    main(["new", "demo", "--purpose", "x", "--agent", "prompt-only", "--dry-run"])
    out = capsys.readouterr().out
    # AGENTS.md operating rules
    assert "Propose -> Confirm -> Execute" in out
    # NIX_RUBRIC stage table
    assert "Stage A — hard gates" in out
    assert "Stage B — stack-aware default" in out
    assert "flake.nix.minimal" in out  # Rust/Go fix from a8087a7
    # project-brief.md section headers
    assert "## 1. Summary" in out
    assert "## 4. Repo Placement and Tier" in out
    assert "## 8. Initial Files" in out


def test_migrate_retrofit_nix_narrows_scope_in_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`migrate --retrofit-nix` must include the narrow-scope directive that
    tells the agent to add only flake.nix + .envrc."""
    source = tmp_path / "src"
    source.mkdir()
    (source / "README.md").write_text("existing\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    main(
        [
            "migrate",
            str(source),
            "--retrofit-nix",
            "--dry-run",
            "--agent",
            "prompt-only",
        ]
    )
    out = capsys.readouterr().out
    assert "SCOPE: Nix retrofit only" in out
    assert "flake.nix" in out


def test_migrate_update_harness_narrows_scope_in_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`migrate --update-harness` directive (Phase 8-B) must appear in prompt."""
    source = tmp_path / "src"
    source.mkdir()
    (source / "README.md").write_text("existing\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    main(
        [
            "migrate",
            str(source),
            "--update-harness",
            "--dry-run",
            "--agent",
            "prompt-only",
        ]
    )
    out = capsys.readouterr().out
    assert "SCOPE: Harness drift remediation" in out


def test_promote_plan_dry_run_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "local-plan.md"
    source.write_text("# Local Plan\n\nDo the work.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["promote-plan", "feature", "--source", str(source), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "docs/plans/feature/plan.md" in out
    assert "dry run: no files written" in out
    assert not (tmp_path / "docs" / "plans" / "feature" / "plan.md").exists()


def test_promote_plan_requires_confirmation_before_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "local-plan.md"
    source.write_text("# Local Plan\n\nDo the work.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "promote feature")

    assert main(["promote-plan", "feature", "--source", str(source)]) == 0
    target = tmp_path / "docs" / "plans" / "feature" / "plan.md"
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert "# Local Plan" in text
    assert "## Progress" in text
    assert "- [ ]" in text


def test_promote_plan_rejects_path_traversal_slug(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "local-plan.md"
    source.write_text("# Local Plan\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["promote-plan", "../etc/passwd", "--source", str(source)]) == 2
    assert not (tmp_path / "etc").exists()


def test_promote_plan_rejects_missing_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)

    missing = tmp_path / "does-not-exist.md"
    assert main(["promote-plan", "feature", "--source", str(missing)]) == 1
    out = capsys.readouterr().out
    assert "source plan not found" in out


def test_promote_plan_refuses_to_overwrite_existing_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "local-plan.md"
    source.write_text("# Local Plan\n", encoding="utf-8")
    target = tmp_path / "docs" / "plans" / "feature" / "plan.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Existing\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["promote-plan", "feature", "--source", str(source)]) == 1
    out = capsys.readouterr().out
    assert "target plan already exists" in out
    assert target.read_text(encoding="utf-8") == "# Existing\n"


def test_promote_plan_aborts_when_confirmation_does_not_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "local-plan.md"
    source.write_text("# Local Plan\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")

    assert main(["promote-plan", "feature", "--source", str(source)]) == 1
    out = capsys.readouterr().out
    assert "Aborted" in out
    assert not (tmp_path / "docs" / "plans" / "feature" / "plan.md").exists()
