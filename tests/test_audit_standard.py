"""Tests for ai_ops.audit.standard (Phase 8-C, L4 ADR drift)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ai_ops.audit import standard


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _seed_ai_ops_like_repo(path: Path) -> str:
    """Initialize a tiny ai-ops-like repo with one initial ADR. Return initial commit SHA."""
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    _git(path, "config", "user.email", "test@test")
    _git(path, "config", "user.name", "test")
    (path / "docs" / "decisions").mkdir(parents=True)
    (path / "docs" / "decisions" / "0001-initial.md").write_text("# 0001\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "init")
    head = _git(path, "rev-parse", "HEAD")
    return head.stdout.strip()


def test_resolve_ref_known(tmp_path: Path) -> None:
    head = _seed_ai_ops_like_repo(tmp_path)
    drift = standard.detect_standard_drift(tmp_path, since_ref=head)
    assert drift.resolved_ref is True


def test_resolve_ref_unknown(tmp_path: Path) -> None:
    _seed_ai_ops_like_repo(tmp_path)
    drift = standard.detect_standard_drift(tmp_path, since_ref="deadbeef")
    assert drift.resolved_ref is False


def test_no_changes_since_head(tmp_path: Path) -> None:
    head = _seed_ai_ops_like_repo(tmp_path)
    drift = standard.detect_standard_drift(tmp_path, since_ref=head)
    assert drift.new_adrs == []
    assert drift.modified_adrs == []


def test_detects_new_adr_added(tmp_path: Path) -> None:
    head = _seed_ai_ops_like_repo(tmp_path)
    (tmp_path / "docs" / "decisions" / "0002-new.md").write_text("# 0002\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "add 0002")
    drift = standard.detect_standard_drift(tmp_path, since_ref=head)
    assert any("0002-new.md" in p for p in drift.new_adrs)


def test_detects_modified_adr(tmp_path: Path) -> None:
    head = _seed_ai_ops_like_repo(tmp_path)
    (tmp_path / "docs" / "decisions" / "0001-initial.md").write_text(
        "# 0001 amended\n", encoding="utf-8"
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "amend 0001")
    drift = standard.detect_standard_drift(tmp_path, since_ref=head)
    assert any("0001-initial.md" in p for p in drift.modified_adrs)


def test_run_standard_audit_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    head = _seed_ai_ops_like_repo(tmp_path)
    rc = standard.run_standard_audit(tmp_path, since_ref=head)
    assert rc == 0


def test_run_standard_audit_with_changes(tmp_path: Path) -> None:
    head = _seed_ai_ops_like_repo(tmp_path)
    (tmp_path / "docs" / "decisions" / "0003-newer.md").write_text(
        "# 0003\n", encoding="utf-8"
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "add 0003")
    rc = standard.run_standard_audit(tmp_path, since_ref=head)
    assert rc == 1


def test_run_standard_audit_unresolved_ref(tmp_path: Path) -> None:
    _seed_ai_ops_like_repo(tmp_path)
    rc = standard.run_standard_audit(tmp_path, since_ref="bogus-ref-xyz")
    assert rc == 1


def test_manifest_sha_used_when_present(tmp_path: Path) -> None:
    """When --since is omitted but project has .ai-ops/harness.toml, that sha is used."""
    head = _seed_ai_ops_like_repo(tmp_path)
    project = tmp_path / "_project"
    project.mkdir()
    (project / ".ai-ops").mkdir()
    (project / ".ai-ops" / "harness.toml").write_text(
        f'ai_ops_sha = "{head}"\nlast_sync = "2026-04-29T00:00:00+00:00"\n[harness_files]\n',
        encoding="utf-8",
    )

    drift = standard.detect_standard_drift(tmp_path, project_root=project)
    assert drift.since_ref == head
    assert drift.resolved_ref is True
