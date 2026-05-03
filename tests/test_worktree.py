"""Tests for ai_ops.worktree (ADR 0010)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


def _git_init(path: Path) -> None:
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(path)], check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "t@t"], check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "t"], check=True,
    )
    (path / "README.md").write_text("hi\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "init"], check=True,
    )


def test_compute_worktree_path_uses_sibling_pattern(tmp_path: Path) -> None:
    """ADR 0010: `<repo-parent>/<repo-name>.<slug>/`."""
    from ai_ops.worktree import compute_worktree_path

    repo = tmp_path / "myrepo"
    out = compute_worktree_path(repo, "feature-x")
    assert out == tmp_path / "myrepo.feature-x"


def test_compute_branch_name_uses_type_prefix() -> None:
    from ai_ops.worktree import compute_branch_name

    assert compute_branch_name("feature-x") == "feat/feature-x"
    assert compute_branch_name("bug-y", "fix") == "fix/bug-y"
    assert compute_branch_name("docs-z", "docs") == "docs/docs-z"


def test_compute_branch_name_rejects_unknown_type() -> None:
    from ai_ops.worktree import compute_branch_name

    with pytest.raises(ValueError):
        compute_branch_name("x", "spike")


def test_create_worktree_dry_run_makes_no_changes(tmp_path: Path) -> None:
    """`dry_run=True` returns the planned paths but writes nothing."""
    from ai_ops.worktree import WorktreeSpec, create_worktree_with_plan

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    wt_path, plan_md, branch = create_worktree_with_plan(
        WorktreeSpec(slug="thing"), repo, dry_run=True,
    )
    assert wt_path == tmp_path / "repo.thing"
    assert plan_md == repo / "docs" / "plans" / "thing" / "plan.md"
    assert branch == "feat/thing"
    # Nothing written.
    assert not wt_path.exists()
    assert not plan_md.exists()
    # No new branch.
    branches = subprocess.run(
        ["git", "-C", str(repo), "branch", "--list"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "feat/thing" not in branches


def test_create_worktree_creates_branch_and_seeds_plan(tmp_path: Path) -> None:
    """Real run: branch is created, worktree exists, plan file seeded."""
    from ai_ops.worktree import WorktreeSpec, create_worktree_with_plan

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    wt_path, plan_md, branch = create_worktree_with_plan(
        WorktreeSpec(slug="thing"), repo, dry_run=False,
    )
    assert wt_path.is_dir()
    plan_in_wt = wt_path / "docs" / "plans" / "thing" / "plan.md"
    assert plan_in_wt.is_file()
    text = plan_in_wt.read_text(encoding="utf-8")
    # Title was substituted.
    assert "<Short, action-oriented plan title>" not in text
    assert "Thing" in text  # title-cased slug
    # Schema fields present.
    assert "Branch: " in text
    assert "Worktree: " in text


def test_create_worktree_refuses_when_path_exists(tmp_path: Path) -> None:
    from ai_ops.worktree import WorktreeSpec, create_worktree_with_plan

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (tmp_path / "repo.thing").mkdir()  # pre-existing

    with pytest.raises(FileExistsError):
        create_worktree_with_plan(
            WorktreeSpec(slug="thing"), repo, dry_run=False,
        )


def test_create_worktree_refuses_when_branch_exists(tmp_path: Path) -> None:
    from ai_ops.worktree import WorktreeSpec, create_worktree_with_plan

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    subprocess.run(
        ["git", "-C", str(repo), "branch", "feat/thing"], check=True,
    )

    with pytest.raises(FileExistsError):
        create_worktree_with_plan(
            WorktreeSpec(slug="thing"), repo, dry_run=False,
        )


def test_find_cleanable_requires_both_signals(tmp_path: Path) -> None:
    """A worktree is cleanable only when (a) plan archived AND (b) PR merged."""
    from ai_ops.worktree import (
        WorktreeSpec, create_worktree_with_plan, find_cleanable_worktrees,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    create_worktree_with_plan(
        WorktreeSpec(slug="done"), repo, dry_run=False,
    )

    # Initially: plan not archived yet, branch not merged → not cleanable.
    with patch("ai_ops.worktree._branch_is_merged_pr", return_value=True):
        out = find_cleanable_worktrees(repo)
    assert out == []  # plan still in active dir

    # Archive the plan (in main repo, not worktree).
    plan_dir = repo / "docs" / "plans" / "done"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "plan.md").write_text("seed\n", encoding="utf-8")
    archive_dir = repo / "docs" / "plans" / "archive" / "2026-01-01-done"
    archive_dir.mkdir(parents=True)
    (archive_dir / "plan.md").write_text("seed\n", encoding="utf-8")
    plan_dir.rmdir() if not (plan_dir / "plan.md").exists() else None
    # Move plan: simplest is to remove active and keep archive.
    (plan_dir / "plan.md").unlink()
    plan_dir.rmdir()

    # Now plan archived + branch merged → cleanable.
    with patch("ai_ops.worktree._branch_is_merged_pr", return_value=True):
        out = find_cleanable_worktrees(repo)
    assert len(out) == 1
    assert out[0][1] == "done"

    # Plan archived but branch not merged (or unknown) → not cleanable.
    with patch("ai_ops.worktree._branch_is_merged_pr", return_value=False):
        out = find_cleanable_worktrees(repo)
    assert out == []
    with patch("ai_ops.worktree._branch_is_merged_pr", return_value=None):
        out = find_cleanable_worktrees(repo)
    assert out == []


def test_cleanup_worktree_removes_worktree_and_branch(tmp_path: Path) -> None:
    """`cleanup_worktree` removes the worktree directory and deletes the branch."""
    from ai_ops.worktree import (
        WorktreeInfo, cleanup_worktree, create_worktree_with_plan, WorktreeSpec,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    wt_path, _, branch = create_worktree_with_plan(
        WorktreeSpec(slug="x"), repo, dry_run=False,
    )
    assert wt_path.exists()

    info = WorktreeInfo(path=wt_path, branch=branch, head_sha="")
    ok, _ = cleanup_worktree(info, repo, dry_run=False)
    assert ok
    assert not wt_path.exists()
    branches = subprocess.run(
        ["git", "-C", str(repo), "branch", "--list", branch],
        capture_output=True, text=True, check=True,
    ).stdout
    assert branch not in branches


def test_read_tier_returns_value_when_manifest_present(tmp_path: Path) -> None:
    from ai_ops.worktree import _read_tier

    repo = tmp_path / "r"
    (repo / ".ai-ops").mkdir(parents=True)
    (repo / ".ai-ops" / "harness.toml").write_text(
        'ai_ops_sha = "abc"\nworkflow_tier = "B"\n', encoding="utf-8",
    )
    assert _read_tier(repo) == "B"


def test_read_tier_returns_none_without_manifest(tmp_path: Path) -> None:
    from ai_ops.worktree import _read_tier

    repo = tmp_path / "r"
    repo.mkdir()
    assert _read_tier(repo) is None


def test_auto_archive_skipped_for_tier_b(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tier B/C プロジェクトでは自動 archive を回避し PR 経路を案内する。"""
    from ai_ops.worktree import auto_archive_plan

    repo = tmp_path / "r"
    (repo / ".ai-ops").mkdir(parents=True)
    (repo / ".ai-ops" / "harness.toml").write_text(
        'workflow_tier = "B"\n', encoding="utf-8",
    )
    (repo / "docs" / "plans" / "x").mkdir(parents=True)
    (repo / "docs" / "plans" / "x" / "plan.md").write_text("plan", encoding="utf-8")

    ok, msg = auto_archive_plan("x", repo, dry_run=True)
    assert ok is False
    assert "Tier B" in msg
    assert "PR" in msg


def test_auto_archive_dry_run_skips_git_for_tier_a(tmp_path: Path) -> None:
    """Tier A / unmanaged は実際に git mv するが、dry-run なら touch しない。"""
    from ai_ops.worktree import auto_archive_plan

    repo = tmp_path / "r"
    (repo / "docs" / "plans" / "x").mkdir(parents=True)
    (repo / "docs" / "plans" / "x" / "plan.md").write_text("plan", encoding="utf-8")

    ok, msg = auto_archive_plan("x", repo, dry_run=True)
    assert ok is True
    assert "[dry-run]" in msg
    # active plan は dry-run では動かない
    assert (repo / "docs" / "plans" / "x" / "plan.md").exists()


def test_list_worktrees_returns_main_plus_created(tmp_path: Path) -> None:
    """After creating one worktree, `list_worktrees` returns 2 entries."""
    from ai_ops.worktree import (
        WorktreeSpec, create_worktree_with_plan, list_worktrees,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    create_worktree_with_plan(
        WorktreeSpec(slug="x"), repo, dry_run=False,
    )
    out = list_worktrees(repo)
    assert len(out) == 2
    paths = {wt.path for wt in out}
    assert tmp_path / "repo" in paths
    assert tmp_path / "repo.x" in paths
