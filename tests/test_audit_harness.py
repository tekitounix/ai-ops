"""Tests for ai_ops.audit.harness (Phase 8-B, L3 harness drift)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ai_ops.audit import harness


def _git_init_minimal(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@test"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "test"], check=True)
    (path / "README.md").write_text("init", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "init"], check=True)


def test_build_manifest_empty_project(tmp_path: Path) -> None:
    """Empty project (no harness files) → manifest with empty harness_files."""
    _git_init_minimal(tmp_path)
    m = harness.build_manifest(tmp_path, tmp_path)
    assert m.harness_files == {}
    # ai_ops_sha may be empty string if git rev-parse fails on tmp_path's parent etc;
    # not asserting non-empty to keep test portable.


def test_build_manifest_picks_up_existing_files(tmp_path: Path) -> None:
    """Manifest hashes only files that actually exist."""
    (tmp_path / "AGENTS.md").write_text("agents", encoding="utf-8")
    (tmp_path / "flake.nix").write_text("flake", encoding="utf-8")
    m = harness.build_manifest(tmp_path, tmp_path)
    assert "AGENTS.md" in m.harness_files
    assert "flake.nix" in m.harness_files
    # CLAUDE.md does not exist → not in manifest
    assert "CLAUDE.md" not in m.harness_files


def test_manifest_toml_roundtrip(tmp_path: Path) -> None:
    m = harness.HarnessManifest(
        ai_ops_sha="abc123",
        harness_files={"AGENTS.md": "deadbeef", "flake.nix": "cafef00d"},
        last_sync="2026-04-29T00:00:00+00:00",
    )
    toml_text = m.to_toml()
    m2 = harness.HarnessManifest.from_toml(toml_text)
    assert m == m2


def test_manifest_workflow_tier_default_is_d() -> None:
    """A manifest with no workflow_tier field reads as Tier D (ADR 0009)."""
    text = (
        'ai_ops_sha = "x"\n'
        'last_sync = "y"\n\n'
        '[harness_files]\n'
        '"AGENTS.md" = "h"\n'
    )
    m = harness.HarnessManifest.from_toml(text)
    assert m.workflow_tier == "D"


def test_manifest_workflow_tier_roundtrip_explicit() -> None:
    """Non-default tier must roundtrip via to_toml/from_toml."""
    m = harness.HarnessManifest(
        ai_ops_sha="x", last_sync="y",
        harness_files={"AGENTS.md": "h"}, workflow_tier="B",
    )
    text = m.to_toml()
    assert 'workflow_tier = "B"' in text
    m2 = harness.HarnessManifest.from_toml(text)
    assert m2.workflow_tier == "B"
    assert m == m2


def test_manifest_workflow_tier_default_omitted_in_toml() -> None:
    """Tier D (default) is intentionally not emitted to keep generated
    manifests minimal for projects that haven't declared a tier."""
    m = harness.HarnessManifest(
        ai_ops_sha="x", last_sync="y",
        harness_files={}, workflow_tier="D",
    )
    text = m.to_toml()
    assert "workflow_tier" not in text


def test_manifest_workflow_tier_invalid_falls_back_to_d() -> None:
    """An unknown tier value defaults to D (defensive)."""
    text = (
        'ai_ops_sha = "x"\n'
        'last_sync = "y"\n'
        'workflow_tier = "Z"\n\n'
        '[harness_files]\n'
    )
    m = harness.HarnessManifest.from_toml(text)
    assert m.workflow_tier == "D"


def test_detect_drift_no_manifest_with_files(tmp_path: Path) -> None:
    """No `.ai-ops/harness.toml` but harness file present → all reported as `extra`."""
    (tmp_path / "AGENTS.md").write_text("agents", encoding="utf-8")
    drift = harness.detect_drift(tmp_path, tmp_path)
    assert drift.manifest_present is False
    assert "AGENTS.md" in drift.extra
    assert drift.missing == []
    assert drift.modified == []


def test_detect_drift_clean(tmp_path: Path) -> None:
    """Manifest matches actual files exactly → no drift."""
    (tmp_path / "AGENTS.md").write_text("agents", encoding="utf-8")
    m = harness.build_manifest(tmp_path, tmp_path)
    (tmp_path / ".ai-ops").mkdir()
    (tmp_path / ".ai-ops" / "harness.toml").write_text(m.to_toml(), encoding="utf-8")

    drift = harness.detect_drift(tmp_path, tmp_path)
    assert drift.manifest_present is True
    assert drift.missing == []
    assert drift.extra == []
    assert drift.modified == []


def test_detect_drift_missing_file(tmp_path: Path) -> None:
    """Manifest claims a file that no longer exists → reported as `missing`."""
    (tmp_path / "AGENTS.md").write_text("agents", encoding="utf-8")
    m = harness.build_manifest(tmp_path, tmp_path)
    (tmp_path / ".ai-ops").mkdir()
    (tmp_path / ".ai-ops" / "harness.toml").write_text(m.to_toml(), encoding="utf-8")
    (tmp_path / "AGENTS.md").unlink()

    drift = harness.detect_drift(tmp_path, tmp_path)
    assert drift.manifest_present is True
    assert "AGENTS.md" in drift.missing


def test_detect_drift_modified_file(tmp_path: Path) -> None:
    """File hash differs from manifest → reported as `modified`."""
    (tmp_path / "AGENTS.md").write_text("agents v1", encoding="utf-8")
    m = harness.build_manifest(tmp_path, tmp_path)
    (tmp_path / ".ai-ops").mkdir()
    (tmp_path / ".ai-ops" / "harness.toml").write_text(m.to_toml(), encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("agents v2", encoding="utf-8")

    drift = harness.detect_drift(tmp_path, tmp_path)
    assert "AGENTS.md" in drift.modified


def test_run_harness_audit_clean_returns_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "AGENTS.md").write_text("agents", encoding="utf-8")
    m = harness.build_manifest(tmp_path, tmp_path)
    (tmp_path / ".ai-ops").mkdir()
    (tmp_path / ".ai-ops" / "harness.toml").write_text(m.to_toml(), encoding="utf-8")
    rc = harness.run_harness_audit(tmp_path, tmp_path)
    assert rc == 0


def test_run_harness_audit_no_manifest_default_is_warn_only(tmp_path: Path) -> None:
    """Default: a project with harness files but no manifest is untracked,
    not broken — return 0 + WARN so the audit can run across all ghq
    projects without flagging every still-pre-adoption repo as failure."""
    (tmp_path / "AGENTS.md").write_text("agents", encoding="utf-8")
    rc = harness.run_harness_audit(tmp_path, tmp_path)
    assert rc == 0


def test_run_harness_audit_no_manifest_strict_returns_one(tmp_path: Path) -> None:
    """`--strict` enforces manifest presence — used in per-repo gates rather
    than the cross-project audit."""
    (tmp_path / "AGENTS.md").write_text("agents", encoding="utf-8")
    rc = harness.run_harness_audit(tmp_path, tmp_path, strict=True)
    assert rc == 1


def test_run_harness_audit_with_manifest_drift_returns_one(tmp_path: Path) -> None:
    """Once a manifest is present, drift is always a failure — strictness
    only applies to the manifest-absence case."""
    (tmp_path / "AGENTS.md").write_text("v1", encoding="utf-8")
    m = harness.build_manifest(tmp_path, tmp_path)
    (tmp_path / ".ai-ops").mkdir()
    (tmp_path / ".ai-ops" / "harness.toml").write_text(m.to_toml(), encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("v2", encoding="utf-8")  # cause drift
    rc = harness.run_harness_audit(tmp_path, tmp_path)
    assert rc == 1


def test_run_harness_audit_pre_adoption_returns_zero(tmp_path: Path) -> None:
    """No manifest AND no harness files (= pre-adoption / fresh project) → OK."""
    rc = harness.run_harness_audit(tmp_path, tmp_path)
    assert rc == 0
