import subprocess
from pathlib import Path

from ai_ops.audit.nix import evaluate_project, run_nix_audit
from ai_ops.audit.security import run_security_audit


def _git_init(path: Path, file_count: int = 6) -> None:
    """Initialize a minimal git repo in path with `file_count` tracked files committed.

    file_count >= 5 にしておくと Stage C の `tiny_project` signal (= -2) が起動しない。
    """
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "test"],
        check=True,
    )
    for i in range(file_count):
        (path / f"_filler{i}.txt").write_text(f"{i}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "init"],
        check=True,
    )


def _git_add_and_commit(path: Path, files: list[str]) -> None:
    for f in files:
        subprocess.run(["git", "-C", str(path), "add", f], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "stack"],
        check=True,
    )


def test_nix_audit_passes_with_correct_flake(tmp_path: Path) -> None:
    """Existing flake with devShells passes (loose match for non-ai-ops repos)."""
    (tmp_path / "flake.nix").write_text(
        "{ outputs = { ... }: { devShells = {}; }; }",
        encoding="utf-8",
    )
    (tmp_path / "flake.lock").write_text("{}\n", encoding="utf-8")
    assert run_nix_audit(tmp_path) == 0


def test_nix_audit_fails_when_stack_present_but_flake_missing(tmp_path: Path) -> None:
    """stack signal (package.json) なのに flake.nix 無し → recommended=devshell, gap=missing-flake → FAIL."""
    (tmp_path / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    assert run_nix_audit(tmp_path) == 1


def test_nix_audit_passes_when_no_stack_signal(tmp_path: Path) -> None:
    """No stack signal AND no flake → minimal recommendation (no fail in non-ai-ops cwd)."""
    # empty dir — Stage A (no archive / scratch / docs-only / fork), Stage B unknown=minimal,
    # Stage C score=0. recommended=minimal (not devshell/apps/full) → no FAIL.
    assert run_nix_audit(tmp_path) == 0


# ─────────────────────────────────────────────────────
# Stage A/B/C rubric tests (self-review #4 follow-up)
# ─────────────────────────────────────────────────────


def test_evaluate_project_existing_flake(tmp_path: Path) -> None:
    """Stage A — existing flake → preserve."""
    (tmp_path / "flake.nix").write_text(
        "{ outputs = { ... }: { devShells = {}; }; }",
        encoding="utf-8",
    )
    r = evaluate_project(tmp_path)
    assert r["stage_a_exit"] == "existing-flake"
    assert r["recommended_level"] == "preserve"
    assert r["gap"] == "ok"


def test_evaluate_project_docs_only(tmp_path: Path) -> None:
    """Stage A — all tracked files are markdown → docs-only → none."""
    (tmp_path / "README.md").write_text("docs", encoding="utf-8")
    (tmp_path / "NOTES.md").write_text("notes", encoding="utf-8")
    r = evaluate_project(tmp_path)
    assert r["stage_a_exit"] == "docs-only"
    assert r["recommended_level"] == "none"


def test_evaluate_project_node_stack(tmp_path: Path) -> None:
    """Stage B — package.json → flake.nix.node template, devshell level."""
    _git_init(tmp_path)
    (tmp_path / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    _git_add_and_commit(tmp_path, ["package.json"])
    r = evaluate_project(tmp_path)
    assert r["stage_a_exit"] is None
    assert r["stack_hint"] == "node"
    assert r["recommended_template"] == "flake.nix.node"
    assert r["recommended_level"] in ("devshell", "apps")


def test_evaluate_project_python_stack(tmp_path: Path) -> None:
    """Stage B — pyproject.toml → flake.nix.python template."""
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\n',
        encoding="utf-8",
    )
    _git_add_and_commit(tmp_path, ["pyproject.toml"])
    r = evaluate_project(tmp_path)
    assert r["stack_hint"] == "python"
    assert r["recommended_template"] == "flake.nix.python"


def test_evaluate_project_xmake_stack(tmp_path: Path) -> None:
    """Stage B — xmake.lua → flake.nix.xmake template (組込み)."""
    _git_init(tmp_path)
    (tmp_path / "xmake.lua").write_text("target('x')\n", encoding="utf-8")
    _git_add_and_commit(tmp_path, ["xmake.lua"])
    r = evaluate_project(tmp_path)
    assert r["stack_hint"] == "xmake"
    assert r["recommended_template"] == "flake.nix.xmake"


def test_evaluate_project_rust_falls_back_to_minimal(tmp_path: Path) -> None:
    """Stage B — Cargo.toml → flake.nix.minimal (NOT flake.nix.python; self-review #1 fix)."""
    _git_init(tmp_path)
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    _git_add_and_commit(tmp_path, ["Cargo.toml"])
    r = evaluate_project(tmp_path)
    assert r["stack_hint"] == "rust"
    assert r["recommended_template"] == "flake.nix.minimal"


def test_evaluate_project_go_falls_back_to_minimal(tmp_path: Path) -> None:
    """Stage B — go.mod → flake.nix.minimal (NOT flake.nix.python; self-review #1 fix)."""
    _git_init(tmp_path)
    (tmp_path / "go.mod").write_text("module x\ngo 1.21\n", encoding="utf-8")
    _git_add_and_commit(tmp_path, ["go.mod"])
    r = evaluate_project(tmp_path)
    assert r["stack_hint"] == "go"
    assert r["recommended_template"] == "flake.nix.minimal"


def test_evaluate_project_score_promotes_to_apps(tmp_path: Path) -> None:
    """Stage C — many pros signals (CI + tests + LICENSE + CONTRIBUTING + dist + AGENTS.md)
    → score ≥ 6 → promote devshell to apps."""
    _git_init(tmp_path)
    (tmp_path / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
    (tmp_path / "CONTRIBUTING.md").write_text("contrib", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("agents", encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "x.js").write_text("", encoding="utf-8")
    _git_add_and_commit(
        tmp_path,
        ["package.json", "LICENSE", "CONTRIBUTING.md", "AGENTS.md"],
    )
    r = evaluate_project(tmp_path)
    assert r["score"] >= 6
    assert r["recommended_level"] == "apps"


def test_evaluate_project_tiny_demote_to_none(tmp_path: Path) -> None:
    """Stage C — tiny project (< 5 file) AND no signals → score < 0 → demote to none."""
    # _git_init w/ file_count=1 で tracked_count = 1 → tiny_project (-2)
    _git_init(tmp_path, file_count=1)
    (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")
    r = evaluate_project(tmp_path)
    # tiny_project (-2) のみが響き、pros signal は無いため score < 0
    assert r["score"] < 0
    assert r["recommended_level"] == "none"


def test_security_audit_clean_repo_passes(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("clean\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 0


def test_security_audit_detects_env_dotfile(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("placeholder\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_detects_pem_file(tmp_path: Path) -> None:
    (tmp_path / "deploy.pem").write_text("placeholder\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_detects_secrets_dir(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "value.txt").write_text("placeholder\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_detects_aws_access_key_pattern(tmp_path: Path) -> None:
    (tmp_path / "config.txt").write_text("AKIA0123456789ABCDEF\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_detects_private_key_header(tmp_path: Path) -> None:
    (tmp_path / "key.txt").write_text(
        "-----BEGIN RSA PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    assert run_security_audit(tmp_path) == 1


def test_security_audit_skips_test_fixtures_under_tests_dir(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "fixture.txt").write_text("AKIA0123456789ABCDEF\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 0


def test_security_audit_still_flags_secret_named_files_under_tests_dir(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / ".env").write_text("placeholder\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_skips_binary_files_without_crashing(tmp_path: Path) -> None:
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02\xff\xfe")
    assert run_security_audit(tmp_path) == 0
