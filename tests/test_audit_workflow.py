"""Tests for ai_ops.audit.workflow (ADR 0009 tier violation detector).

Covers shallow detections only (no `gh` API). Deep detections are
exercised manually since they require a live GitHub repo.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)
    (path / "README.md").write_text("hi\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "init"], check=True)


def test_detect_violations_unknown_tier(tmp_path: Path) -> None:
    """An unknown tier surfaces an explicit violation message."""
    from ai_ops.audit.workflow import detect_tier_violations

    _git_init(tmp_path)
    out = detect_tier_violations(tmp_path, "Z", default_branch="main")
    assert any("unknown tier" in v for v in out)


def test_detect_violations_tier_d_manifest_off_default_is_info(
    tmp_path: Path,
) -> None:
    """Tier D's manifest-not-on-default surfaces as INFO, not WARN."""
    from ai_ops.audit.workflow import detect_tier_violations

    _git_init(tmp_path)
    out = detect_tier_violations(tmp_path, "D", default_branch="main")
    assert any(v.startswith("INFO:") for v in out)
    assert not any(
        "absent on origin/main" in v and not v.startswith("INFO:")
        for v in out
    )


def test_detect_violations_tier_a_manifest_off_default_is_warn(
    tmp_path: Path,
) -> None:
    """Tier A/B/C's manifest-not-on-default surfaces as actionable WARN."""
    from ai_ops.audit.workflow import detect_tier_violations

    _git_init(tmp_path)
    for tier in ("A", "B", "C"):
        out = detect_tier_violations(tmp_path, tier, default_branch="main")
        assert any(
            "absent on origin/main" in v and not v.startswith("INFO:")
            for v in out
        ), f"tier {tier} should warn"


def test_detect_violations_tier_a_long_lived_branch(tmp_path: Path) -> None:
    """A long-lived feature branch in Tier A surfaces as a violation."""
    import os
    import time

    from ai_ops.audit.workflow import detect_tier_violations

    _git_init(tmp_path)
    # Create a feature branch with an old committer date.
    subprocess.run(
        ["git", "-C", str(tmp_path), "checkout", "-q", "-b", "old-feature"],
        check=True,
    )
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "x.txt"], check=True)
    # Backdate commit to 60 days ago.
    old_ts = int(time.time()) - 60 * 86400
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": f"{old_ts} +0000",
        "GIT_COMMITTER_DATE": f"{old_ts} +0000",
    }
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "old"],
        env=env, check=True,
    )

    out = detect_tier_violations(tmp_path, "A", default_branch="main")
    assert any("long-lived branch 'old-feature'" in v for v in out)


def test_detect_violations_tier_b_no_long_lived_check(tmp_path: Path) -> None:
    """Tier B does NOT flag long-lived branches (PR workflow expects them)."""
    import os
    import time

    from ai_ops.audit.workflow import detect_tier_violations

    _git_init(tmp_path)
    subprocess.run(
        ["git", "-C", str(tmp_path), "checkout", "-q", "-b", "feature/long"],
        check=True,
    )
    (tmp_path / "y.txt").write_text("y", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "y.txt"], check=True)
    old_ts = int(time.time()) - 60 * 86400
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": f"{old_ts} +0000",
        "GIT_COMMITTER_DATE": f"{old_ts} +0000",
    }
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "old"],
        env=env, check=True,
    )

    out = detect_tier_violations(tmp_path, "B", default_branch="main")
    assert not any("long-lived branch" in v for v in out)


def test_detect_violations_no_default_branch_passed(tmp_path: Path) -> None:
    """When default_branch=None (gh unavailable), skip default-branch checks
    gracefully — only return tier-format violations."""
    from ai_ops.audit.workflow import detect_tier_violations

    _git_init(tmp_path)
    out = detect_tier_violations(tmp_path, "A", default_branch=None)
    # Long-lived check still runs against fallback "main"; here there are
    # no long-lived branches so out should be empty.
    assert out == []
