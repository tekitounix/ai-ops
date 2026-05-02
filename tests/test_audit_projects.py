"""Tests for ai_ops.audit.projects (Phase 11 projects audit)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ai_ops.audit import projects


# Split literal so this test file does not self-flag in audit security.
_FAKE_AWS_KEY = "A" + "KIA0123456789ABCDEF"


def _git_init(path: Path, with_initial_commit: bool = True) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "test"],
        check=True,
    )
    if with_initial_commit:
        (path / "README.md").write_text("init", encoding="utf-8")
        subprocess.run(["git", "-C", str(path), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(path), "commit", "-q", "-m", "init"], check=True
        )


def _make_under_ghq(home: Path, *segments: str) -> Path:
    p = home / "ghq"
    for seg in segments:
        p = p / seg
    p.mkdir(parents=True, exist_ok=True)
    return p


def _stub_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))


# ─────────────────────────────────────────────────────
# Signal accuracy
# ─────────────────────────────────────────────────────


def test_collect_signals_p0_for_secret_file(tmp_path: Path) -> None:
    p = tmp_path / "proj"
    p.mkdir()
    _git_init(p)
    (p / ".env").write_text("API_KEY=real\n", encoding="utf-8")
    s = projects.collect_signals(p)
    assert s.sec >= 1
    assert s.priority == "P0"


def test_p0_sec_routes_to_realign_when_managed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A managed project with secret-name files must surface a concrete
    sub-flow, not no-op. Realignment owns the `.env` review step."""
    _stub_home(monkeypatch, tmp_path)
    p = _make_under_ghq(tmp_path, "github.com", "owner", "managed-with-env")
    _git_init(p)
    (p / "AGENTS.md").write_text("agents", encoding="utf-8")
    (p / ".env").write_text("API_KEY=real\n", encoding="utf-8")
    from ai_ops.audit.harness import HarnessManifest, _sha256
    (p / ".ai-ops").mkdir()
    m = HarnessManifest(
        ai_ops_sha="",
        harness_files={"AGENTS.md": _sha256(p / "AGENTS.md")},
        last_sync="2026-04-30T00:00:00+00:00",
    )
    (p / ".ai-ops" / "harness.toml").write_text(m.to_toml(), encoding="utf-8")

    s = projects.collect_signals(p)
    assert s.sec >= 1
    assert s.priority == "P0"
    assert s.sub_flow == "realign"


def test_p0_sec_routes_to_migrate_when_unmanaged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unmanaged project with secret-name files routes to migrate.
    Migration is where the harness gets seeded; secret hygiene is part
    of the same flow."""
    _stub_home(monkeypatch, tmp_path)
    p = _make_under_ghq(tmp_path, "github.com", "owner", "unmanaged-with-env")
    _git_init(p)
    (p / ".env").write_text("API_KEY=real\n", encoding="utf-8")

    s = projects.collect_signals(p)
    assert s.sec >= 1
    assert s.priority == "P0"
    assert s.sub_flow == "migrate"


def test_collect_signals_excludes_env_template(tmp_path: Path) -> None:
    """`.env.example`, `.env.template`, etc. are placeholders, not secrets."""
    p = tmp_path / "proj"
    p.mkdir()
    _git_init(p)
    for name in (".env.example", ".env.template", ".env.sample"):
        (p / name).write_text("KEY=__placeholder__\n", encoding="utf-8")
    s = projects.collect_signals(p)
    assert s.sec == 0


def test_collect_signals_p0_for_location_drift(tmp_path: Path) -> None:
    """A project not under ~/ghq/ → DRIFT → P0 → relocate."""
    p = tmp_path / "outside-ghq"
    p.mkdir()
    _git_init(p)
    s = projects.collect_signals(p)
    assert s.loc == "DRIFT"
    assert s.priority == "P0"
    assert s.sub_flow == "relocate"


def test_collect_signals_skips_dependency_dirs_for_secrets(tmp_path: Path) -> None:
    """`.venv/.../.env` and `node_modules/.../.env` should not count toward
    sec — they are vendored / generated, not the project's own secrets.

    Includes the third-party / external / deps / subprojects directories that
    a real audit run caught producing false positives (STM32 + mbedTLS
    test fixtures vendored under `third_party/`)."""
    p = tmp_path / "proj"
    p.mkdir()
    _git_init(p)
    for d in (
        ".venv", "node_modules", "vendor", "dist", "build",
        "third_party", "third-party", "external", "deps", "subprojects",
    ):
        (p / d).mkdir()
        (p / d / ".env").write_text("foo\n", encoding="utf-8")
        (p / d / "test.pem").write_text("-----BEGIN-----\n", encoding="utf-8")
    s = projects.collect_signals(p)
    assert s.sec == 0


def test_collect_signals_skips_git_submodule_paths(tmp_path: Path) -> None:
    """Files under git submodule paths are upstream's responsibility and
    must not contribute to sec / drift counts."""
    parent = tmp_path / "proj"
    parent.mkdir()
    _git_init(parent)
    sub = tmp_path / "remote-sub"
    sub.mkdir()
    _git_init(sub)
    # Add submodule
    subprocess.run(
        ["git", "-C", str(parent), "-c", "protocol.file.allow=always",
         "submodule", "add", str(sub), "vendor-sub"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(parent), "commit", "-q", "-m", "add submodule"],
        check=True,
    )
    # Drop a fake secret-name file inside the submodule (e.g. test fixture)
    (parent / "vendor-sub" / "test.pem").write_text(
        "-----BEGIN CERT-----\n", encoding="utf-8"
    )
    s = projects.collect_signals(parent)
    assert s.sec == 0


def test_collect_signals_marks_ai_ops_repo_as_source_of_truth(tmp_path: Path) -> None:
    """ai-ops itself (AGENTS.md + ai_ops/cli.py + docs/decisions/) is the
    methodology source. It must not be flagged for `migrate` even though
    it lacks `.ai-ops/harness.toml`."""
    p = tmp_path / "ai-ops-clone"
    p.mkdir()
    _git_init(p)
    (p / "AGENTS.md").write_text("# ai-ops\n", encoding="utf-8")
    (p / "ai_ops").mkdir()
    (p / "ai_ops" / "cli.py").write_text("def main(): pass\n", encoding="utf-8")
    (p / "docs").mkdir()
    (p / "docs" / "decisions").mkdir()
    s = projects.collect_signals(p)
    assert s.mgd == "src"  # source-of-truth marker
    assert s.sub_flow == "no-op"  # never recommend migrate against ai-ops itself


# ─────────────────────────────────────────────────────
# Priority + sub-flow routing under ~/ghq/
# ─────────────────────────────────────────────────────


def test_p1_for_unmanaged_stack_project_under_ghq(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stack-bearing project under ~/ghq/, no harness, no flake → P1 / migrate."""
    _stub_home(monkeypatch, tmp_path)
    p = _make_under_ghq(tmp_path, "github.com", "owner", "stacked")
    _git_init(p)
    (p / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    subprocess.run(["git", "-C", str(p), "add", "."], check=True)
    subprocess.run(["git", "-C", str(p), "commit", "-q", "-m", "stack"], check=True)
    s = projects.collect_signals(p)
    assert s.loc == "ok"
    assert s.has_stack is True
    assert s.nix == "missing"
    assert s.mgd == "no"
    assert s.priority == "P1"
    assert s.sub_flow == "migrate"


def test_p2_for_docs_only_project_under_ghq(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Docs-only repo with no flake.nix is still P2 (nix=n/a — no stack)."""
    _stub_home(monkeypatch, tmp_path)
    p = _make_under_ghq(tmp_path, "github.com", "owner", "notes")
    _git_init(p)
    (p / "notes.md").write_text("# notes\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(p), "add", "."], check=True)
    subprocess.run(["git", "-C", str(p), "commit", "-q", "-m", "docs"], check=True)
    s = projects.collect_signals(p)
    assert s.is_docs_only is True
    assert s.nix == "n/a"
    assert s.priority == "P2"


def test_p2_unmanaged_project_recommends_no_op_not_migrate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2 means "no action needed". Validation / fixture / pure-docs repos
    that happen to be unmanaged must NOT get a `migrate` recommendation —
    that would contradict P2 and pollute the projects view with noise."""
    _stub_home(monkeypatch, tmp_path)
    p = _make_under_ghq(tmp_path, "local", "owner", "fixture")
    _git_init(p)
    (p / "notes.md").write_text("# notes\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(p), "add", "."], check=True)
    subprocess.run(["git", "-C", str(p), "commit", "-q", "-m", "docs"], check=True)
    s = projects.collect_signals(p)
    assert s.priority == "P2"
    assert s.sub_flow == "no-op"  # not migrate


def test_p2_for_clean_managed_project_under_ghq(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A managed project (.ai-ops/harness.toml) with matching files and no
    drift → P2 / no-op.

    Manifest pins to a stubbed ai-ops HEAD so detect_drift sees no SHA
    drift AND policy drift detector sees a valid anchor (avoiding the
    `no-anchor` signal). The stub makes the test pass identically on a
    developer machine and in Nix sandboxes (which copy source without
    `.git` so `_ai_ops_head_sha` would otherwise return an empty string).
    """
    _stub_home(monkeypatch, tmp_path)
    p = _make_under_ghq(tmp_path, "github.com", "owner", "clean")
    _git_init(p)
    (p / "AGENTS.md").write_text("agents", encoding="utf-8")
    (p / ".ai-ops").mkdir()
    from ai_ops.audit.harness import HarnessManifest, _sha256
    fixed_sha = "abcdef1234567890abcdef1234567890abcdef12"
    monkeypatch.setattr(
        "ai_ops.audit.harness._ai_ops_head_sha", lambda _: fixed_sha,
    )
    files_hashes = {"AGENTS.md": _sha256(p / "AGENTS.md")}
    m = HarnessManifest(
        ai_ops_sha=fixed_sha,
        harness_files=files_hashes,
        last_sync="2026-04-29T00:00:00+00:00",
    )
    (p / ".ai-ops" / "harness.toml").write_text(m.to_toml(), encoding="utf-8")
    s = projects.collect_signals(p)
    assert s.mgd == "yes"
    assert s.harness_drift is False
    assert s.policy_drift == "ok"
    assert s.priority == "P2"
    assert s.sub_flow == "no-op"


def test_p1_realign_for_managed_with_harness_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A managed project where AGENTS.md was modified after manifest →
    harness drift → P1 / realign."""
    _stub_home(monkeypatch, tmp_path)
    p = _make_under_ghq(tmp_path, "github.com", "owner", "drifted")
    _git_init(p)
    (p / "AGENTS.md").write_text("v1", encoding="utf-8")
    from ai_ops.audit.harness import build_manifest
    m = build_manifest(p, p)
    (p / ".ai-ops").mkdir()
    (p / ".ai-ops" / "harness.toml").write_text(m.to_toml(), encoding="utf-8")
    (p / "AGENTS.md").write_text("v2-drift", encoding="utf-8")
    s = projects.collect_signals(p)
    assert s.harness_drift is True
    assert s.priority == "P1"
    assert s.sub_flow == "realign"


# ─────────────────────────────────────────────────────
# Output formatting
# ─────────────────────────────────────────────────────


def test_run_projects_audit_json_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--json` emits a parseable list of rows with the documented keys."""
    p = tmp_path / "proj"
    p.mkdir()
    _git_init(p)
    projects.run_projects_audit(roots=[p], json_output=True)
    out = capsys.readouterr().out
    rows = json.loads(out)
    assert isinstance(rows, list) and len(rows) == 1
    expected_keys = {
        "project", "path", "loc", "mgd", "nix", "sec", "dirty",
        "last_commit_age_days", "last_commit_human", "todo",
        "agents_md", "has_stack", "is_docs_only", "harness_drift",
        "priority", "sub_flow",
    }
    assert expected_keys <= set(rows[0])


def test_run_projects_audit_text_table_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Default text output prints summary line plus a header row."""
    p = tmp_path / "proj"
    p.mkdir()
    _git_init(p)
    projects.run_projects_audit(roots=[p])
    out = capsys.readouterr().out
    assert "Projects audit:" in out
    assert "P0=" in out and "P1=" in out and "P2=" in out
    assert "sub-flow" in out  # column header


def test_run_projects_audit_priority_filter(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--priority P2` keeps only P2 rows; with one DRIFT (P0) input, output
    is empty rows but command still succeeds with rc=0 (no P0/P1 left)."""
    drift = tmp_path / "outside"
    drift.mkdir()
    _git_init(drift)
    rc = projects.run_projects_audit(
        roots=[drift], json_output=True, priority_filter="P2"
    )
    out = capsys.readouterr().out
    rows = json.loads(out)
    assert rows == []
    assert rc == 0


# ─────────────────────────────────────────────────────
# Exit code (cron / CI)
# ─────────────────────────────────────────────────────


def test_run_projects_audit_exit_code_nonzero_when_p0_present(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    drift = tmp_path / "outside"
    drift.mkdir()
    _git_init(drift)
    rc = projects.run_projects_audit(roots=[drift], json_output=True)
    assert rc == 1


def test_run_projects_audit_exit_code_zero_when_only_p2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_home(monkeypatch, tmp_path)
    p = _make_under_ghq(tmp_path, "github.com", "owner", "notes")
    _git_init(p)
    (p / "notes.md").write_text("# notes\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(p), "add", "."], check=True)
    subprocess.run(["git", "-C", str(p), "commit", "-q", "-m", "docs"], check=True)
    rc = projects.run_projects_audit(roots=[p], json_output=True)
    assert rc == 0


# ─────────────────────────────────────────────────────
# Error tolerance
# ─────────────────────────────────────────────────────


def test_run_projects_audit_continues_after_per_project_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One broken project (corrupted .git, symlink loop, perm denied) must
    not abort an audit run."""
    good = tmp_path / "good"
    good.mkdir()
    _git_init(good)
    bad = tmp_path / "bad"
    bad.mkdir()

    real = projects.collect_signals

    def flaky(path):
        if path == bad:
            raise RuntimeError("simulated corruption")
        return real(path)

    monkeypatch.setattr(projects, "collect_signals", flaky)
    rc = projects.run_projects_audit(roots=[good, bad], json_output=True)
    # rc reflects only successful collections; bad project surfaces via stderr
    assert rc in (0, 1)


def test_run_projects_audit_no_projects_returns_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If `ghq list -p` yields nothing, the audit fails fast (rc=1)."""
    monkeypatch.setattr(projects, "_ghq_list_paths", lambda: [])
    rc = projects.run_projects_audit()
    assert rc == 1
