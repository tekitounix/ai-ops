import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_ops.audit.nix import evaluate_project, run_nix_audit
from ai_ops.audit.security import run_security_audit


# Split literals so that ai-ops audit security can scan this test file without
# self-flagging. The runtime values still match the regex once concatenated.
_FAKE_AWS_KEY = "A" + "KIA0123456789ABCDEF"
_FAKE_PRIVATE_HEADER = "-----" + "BEGIN RSA PRIVATE KEY-----"


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


def test_lifecycle_audit_recognizes_renovate_artifact(tmp_path: Path) -> None:
    """Phase 8-A: renovate.json artifact must be in REQUIRED_FILES + allowed_template_files."""
    from ai_ops.audit.lifecycle import REQUIRED_FILES
    assert "templates/artifacts/renovate.json" in REQUIRED_FILES
    assert "templates/artifacts/update-flake-lock.yml" in REQUIRED_FILES
    assert "templates/plan.md" in REQUIRED_FILES
    assert "docs/decisions/0008-plan-persistence.md" in REQUIRED_FILES
    assert "docs/realignment.md" in REQUIRED_FILES


def test_lifecycle_audit_warns_on_plan_hygiene(tmp_path: Path) -> None:
    """mtime-based fallback path: untracked plan with old mtime is flagged."""
    from ai_ops.audit.lifecycle import _check_plan_hygiene

    plan = tmp_path / "docs" / "plans" / "feature" / "plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("# Feature\n\n## Progress\n\nNo checkbox yet.\n", encoding="utf-8")

    now = datetime(2026, 4, 29, tzinfo=timezone.utc)
    old = now - timedelta(days=31)
    os.utime(plan, (old.timestamp(), old.timestamp()))

    warnings = _check_plan_hygiene(tmp_path, now=now)
    assert any("missing Progress checkbox" in warning for warning in warnings)
    assert any("active for >30 days" in warning for warning in warnings)


def test_plan_age_prefers_git_log_over_mtime(tmp_path: Path) -> None:
    """When the plan is tracked in git, _plan_age uses commit time, not mtime.

    This protects against the CI / fresh-clone case where mtime is reset to
    the checkout time and a genuinely stale plan would otherwise look fresh.
    """
    from ai_ops.audit.lifecycle import _plan_age

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@test"], check=True
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "test"], check=True
    )
    plan = tmp_path / "docs" / "plans" / "feature" / "plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("# Feature\n", encoding="utf-8")

    # Commit the plan as if it had been committed long ago.
    far_past = "2020-01-01T00:00:00Z"
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": far_past,
        "GIT_COMMITTER_DATE": far_past,
    }
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "old plan"],
        check=True,
        env=env,
    )

    # Force mtime to "now" so mtime alone would say the plan is fresh.
    now = datetime(2026, 4, 29, tzinfo=timezone.utc)
    os.utime(plan, (now.timestamp(), now.timestamp()))

    age = _plan_age(plan, tmp_path, now)
    # Commit was 2020 → age should be > 5 years; far above the 30-day threshold.
    assert age > timedelta(days=365 * 5), f"expected git-log-derived age, got {age}"


def test_lifecycle_audit_forbidden_pattern_grep(tmp_path: Path) -> None:
    """Phase 8-D: every forbidden pattern in FORBIDDEN_ACTIVE_PATTERNS must
    actually fire when its target string is present in active code. This
    catches regex regressions where a pattern could be silently broken."""
    from ai_ops.audit.lifecycle import (
        FORBIDDEN_ACTIVE_PATTERNS,
        _scan_pattern_in_paths,
    )

    # Realistic offending lines for each forbidden pattern.
    forbidden_examples: dict[str, str] = {
        r"--no-verify": 'subprocess.run(["git", "commit", "--no-verify"])',
        r"\brm\s+-rf\b": 'os.system("rm -rf /tmp/x")',
        r"gh\s+repo\s+create[^|;\n]*--public": (
            'os.system("gh repo create some-repo --public")'
        ),
        r"#\s*silent[\s_-]*install": "# silent install: skip user prompt",
    }

    (tmp_path / "ai_ops").mkdir()

    for desc, pattern, scan_paths in FORBIDDEN_ACTIVE_PATTERNS:
        line = forbidden_examples.get(pattern)
        assert line is not None, f"add an example for pattern: {pattern!r} ({desc})"
        offender = tmp_path / "ai_ops" / "offender.py"
        offender.write_text(line + "\n", encoding="utf-8")
        hits = _scan_pattern_in_paths(tmp_path, pattern, scan_paths)
        assert hits, f"pattern {pattern!r} ({desc}) failed to detect: {line!r}"
        offender.unlink()


def test_lifecycle_audit_scorecard_skips_when_missing(tmp_path: Path) -> None:
    """Phase 8-D: Scorecard CLI 不在時は INFO にして audit を fail させない。"""
    from ai_ops.audit.lifecycle import _check_scorecard

    # ai-ops 自身の root を渡しても scorecard CLI が無いなら ran=False で skip する
    ran, msg = _check_scorecard(tmp_path)
    # CI 環境次第で True/False どちらもあり得るが、msg が必ず非空であること
    assert isinstance(ran, bool)
    assert isinstance(msg, str) and len(msg) > 0


def test_lifecycle_audit_readme_claim_verification(tmp_path: Path) -> None:
    """Phase 8-D: README claim 検証は実 ai-ops repo 上では PASS する想定。"""
    from ai_ops.audit.lifecycle import _check_readme_claims

    # Use the real ai-ops repo root for this end-to-end claim check.
    repo = Path(__file__).resolve().parents[1]
    failures = _check_readme_claims(repo)
    assert failures == [], f"README claim verification failed: {failures}"


def test_run_nix_report_continues_after_per_project_error(
    tmp_path: Path, monkeypatch
) -> None:
    """One bad project (corrupted .git, symlink loop, etc.) must not abort
    the fleet survey. evaluate_project raises → row reported as ERROR, loop
    continues."""
    from ai_ops.audit import nix as nix_mod

    good = tmp_path / "good"
    good.mkdir()
    bad = tmp_path / "bad"
    bad.mkdir()

    real_evaluate = nix_mod.evaluate_project

    def flaky_evaluate(path):
        if path == bad:
            raise RuntimeError("simulated corruption")
        return real_evaluate(path)

    monkeypatch.setattr(nix_mod, "evaluate_project", flaky_evaluate)
    rc = nix_mod.run_nix_report(roots=[good, bad])
    assert rc == 0  # report still completes; the bad project shows as ERROR


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
    (tmp_path / "config.txt").write_text(_FAKE_AWS_KEY + "\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_detects_private_key_header(tmp_path: Path) -> None:
    (tmp_path / "key.txt").write_text(
        _FAKE_PRIVATE_HEADER + "\n",
        encoding="utf-8",
    )
    assert run_security_audit(tmp_path) == 1


def test_security_audit_skips_only_tests_fixtures_directory(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "tests" / "fixtures"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "fake.txt").write_text(_FAKE_AWS_KEY + "\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 0


def test_security_audit_flags_value_in_tests_top_level(tmp_path: Path) -> None:
    # 旧挙動 (tests/ 全体 skip) は廃止。tests/ 直下や tests/<not-fixtures>/ は scan する。
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "leaked.txt").write_text(_FAKE_AWS_KEY + "\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_still_flags_secret_named_files_under_tests_dir(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / ".env").write_text("placeholder\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_skips_binary_files_without_crashing(tmp_path: Path) -> None:
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02\xff\xfe")
    assert run_security_audit(tmp_path) == 0
