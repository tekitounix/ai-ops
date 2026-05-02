"""Tests for ai_ops.propagate (anchor-sync only).

These tests focus on the target-listing logic and the worktree-cleanup
guarantee. The actual `gh` and `git` invocations are not exercised end-to-
end here; instead we use the existing local-git fixtures and verify the
filtering and skip-reason behaviour.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


def _git_init_committed(path: Path, name: str = "test") -> None:
    """Initialise a git repo with a single committed file."""
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)
    (path / f"{name}.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "init"], check=True)


def _make_managed_project(
    tmp_path: Path,
    name: str,
    *,
    ai_ops_sha: str,
    track_manifest: bool = True,
) -> Path:
    """Create a minimal managed project with .ai-ops/harness.toml."""
    project = tmp_path / name
    project.mkdir()
    _git_init_committed(project)
    (project / ".ai-ops").mkdir()
    (project / "AGENTS.md").write_text("placeholder\n", encoding="utf-8")
    (project / "CLAUDE.md").write_text("placeholder\n", encoding="utf-8")

    # Build a manifest whose harness_files match the actual file hashes so
    # detect_drift only flags ai_ops_sha drift (not modified/missing/extra).
    from ai_ops.audit.harness import HarnessManifest, _sha256
    files_hashes = {
        "AGENTS.md": _sha256(project / "AGENTS.md"),
        "CLAUDE.md": _sha256(project / "CLAUDE.md"),
    }
    manifest = HarnessManifest(
        ai_ops_sha=ai_ops_sha,
        last_sync="2026-04-29T00:00:00+00:00",
        harness_files=files_hashes,
    )
    (project / ".ai-ops" / "harness.toml").write_text(
        manifest.to_toml(), encoding="utf-8",
    )

    subprocess.run(
        ["git", "-C", str(project), "add", "AGENTS.md", "CLAUDE.md"],
        check=True,
    )
    if track_manifest:
        subprocess.run(
            ["git", "-C", str(project), "add", ".ai-ops/harness.toml"],
            check=True,
        )
    subprocess.run(
        ["git", "-C", str(project), "commit", "-q", "-m", "add harness"],
        check=True,
    )
    return project


def test_target_list_skips_unmanaged_project(tmp_path: Path) -> None:
    """Project without `.ai-ops/harness.toml` is skipped with a clear reason."""
    from ai_ops.propagate import list_anchor_sync_targets

    project = tmp_path / "unmanaged"
    project.mkdir()
    _git_init_committed(project)

    ai_ops_root = Path(__file__).resolve().parent.parent

    targets, skips = list_anchor_sync_targets(ai_ops_root, [project])

    assert targets == []
    assert any(
        "no .ai-ops/harness.toml" in s.reason and s.project_path == project
        for s in skips
    )


def test_target_list_skips_when_manifest_untracked(tmp_path: Path) -> None:
    """`.ai-ops/harness.toml` present but untracked is skipped (PR impossible)."""
    from ai_ops.propagate import list_anchor_sync_targets

    project = _make_managed_project(
        tmp_path, "untracked-mfst",
        ai_ops_sha="0000000000000000000000000000000000000000",
        track_manifest=False,
    )

    ai_ops_root = Path(__file__).resolve().parent.parent

    targets, skips = list_anchor_sync_targets(ai_ops_root, [project])

    assert targets == []
    assert any(
        "untracked" in s.reason and s.project_path == project
        for s in skips
    )


def test_target_list_skips_when_files_have_drift(tmp_path: Path) -> None:
    """A project with file content drift is skipped (anchor-sync alone unsafe).

    If `[harness_files]` hashes don't match disk, anchor-sync would lie
    about the synced state. Defer to the harness-files-sync plan.
    """
    from ai_ops.propagate import list_anchor_sync_targets

    ai_ops_root = Path(__file__).resolve().parent.parent
    project = _make_managed_project(
        tmp_path, "files-drifted",
        ai_ops_sha="0000000000000000000000000000000000000000",
    )
    # Modify AGENTS.md after manifest commit so detect_drift reports it.
    (project / "AGENTS.md").write_text("modified\n", encoding="utf-8")

    targets, skips = list_anchor_sync_targets(ai_ops_root, [project])

    assert targets == []
    assert any(
        "file drift present" in s.reason and s.project_path == project
        for s in skips
    )


def test_target_list_skips_when_no_gh_metadata(tmp_path: Path) -> None:
    """A project without GitHub metadata (no `gh` or non-GitHub remote) is
    skipped explicitly, never silently."""
    from ai_ops.propagate import list_anchor_sync_targets

    ai_ops_root = Path(__file__).resolve().parent.parent
    project = _make_managed_project(
        tmp_path, "no-gh",
        ai_ops_sha="0000000000000000000000000000000000000000",
    )

    # Simulate `gh repo view` returning None (e.g., no remote configured).
    with patch("ai_ops.propagate._gh_repo_metadata", return_value=None):
        targets, skips = list_anchor_sync_targets(ai_ops_root, [project])

    assert targets == []
    assert any(
        "GitHub" in s.reason and s.project_path == project for s in skips
    )


def test_target_list_includes_drifted_managed_project(tmp_path: Path) -> None:
    """A managed project with only ai_ops_sha drift is a valid target."""
    from ai_ops.propagate import list_anchor_sync_targets

    ai_ops_root = Path(__file__).resolve().parent.parent
    project = _make_managed_project(
        tmp_path, "drifted",
        ai_ops_sha="0000000000000000000000000000000000000000",
    )

    with patch(
        "ai_ops.propagate._gh_repo_metadata",
        return_value=("main", "owner/drifted"),
    ):
        targets, skips = list_anchor_sync_targets(ai_ops_root, [project])

    assert len(targets) == 1
    target = targets[0]
    assert target.project_path == project
    assert target.current_sha == "0000000000000000000000000000000000000000"
    # new_sha should be the actual ai-ops HEAD (40-char hex)
    assert len(target.new_sha) == 40
    assert target.default_branch == "main"
    assert target.repo_full_name == "owner/drifted"


def test_anchor_sync_one_dry_run_has_no_side_effects(tmp_path: Path) -> None:
    """`anchor_sync_one(target, dry_run=True)` writes nothing and makes no
    network calls."""
    from ai_ops.propagate import AnchorSyncTarget, anchor_sync_one

    project = _make_managed_project(
        tmp_path, "dryrun",
        ai_ops_sha="0000000000000000000000000000000000000000",
    )
    target = AnchorSyncTarget(
        project_path=project,
        current_sha="0000000000000000000000000000000000000000",
        new_sha="2d2a7bfb043ee994075827c3cfc014fa42848429",
        default_branch="main",
        repo_full_name="owner/dryrun",
    )

    # Capture state before.
    before = (project / ".ai-ops" / "harness.toml").read_text(encoding="utf-8")
    git_status_before = subprocess.run(
        ["git", "-C", str(project), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout

    ok, msg = anchor_sync_one(target, dry_run=True)

    assert ok is True
    assert "would create branch" in msg
    # File unchanged.
    after = (project / ".ai-ops" / "harness.toml").read_text(encoding="utf-8")
    assert before == after
    # Git state unchanged.
    git_status_after = subprocess.run(
        ["git", "-C", str(project), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert git_status_before == git_status_after


def test_cleanup_worktree_removes_branch_and_directory(tmp_path: Path) -> None:
    """`_cleanup_worktree` removes worktree dir AND local branch.

    Guarantees the user is never left with leftover worktrees or branches
    after a propagate-anchor run, regardless of where it succeeded or
    failed mid-flight.
    """
    from ai_ops.propagate import _cleanup_worktree

    project = _make_managed_project(
        tmp_path, "wt-cleanup",
        ai_ops_sha="0000000000000000000000000000000000000000",
    )
    worktree_path = tmp_path / "wt-out"
    branch = "ai-ops/anchor-sync-test"

    # Create a worktree manually so cleanup has something to remove.
    subprocess.run(
        ["git", "-C", str(project), "worktree", "add", "-b", branch,
         str(worktree_path), "HEAD"],
        check=True,
    )
    assert worktree_path.exists()
    branches_before = subprocess.run(
        ["git", "-C", str(project), "branch", "--list", branch],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert branch in branches_before

    _cleanup_worktree(project, worktree_path, branch)

    assert not worktree_path.exists()
    branches_after = subprocess.run(
        ["git", "-C", str(project), "branch", "--list", branch],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert branches_after == ""


def test_run_propagate_anchor_requires_argument() -> None:
    """`--all` or `--project` is required; without either, return non-zero."""
    from ai_ops.propagate import run_propagate_anchor

    ai_ops_root = Path(__file__).resolve().parent.parent
    rc = run_propagate_anchor(ai_ops_root=ai_ops_root)
    assert rc != 0


def test_run_propagate_anchor_dry_run_lists_targets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end dry-run: surfaces targets and skip reasons, no side effects."""
    from ai_ops.propagate import run_propagate_anchor

    ai_ops_root = Path(__file__).resolve().parent.parent
    project = _make_managed_project(
        tmp_path, "dryrun-e2e",
        ai_ops_sha="0000000000000000000000000000000000000000",
    )

    with patch(
        "ai_ops.propagate._gh_repo_metadata",
        return_value=("main", "owner/dryrun-e2e"),
    ):
        # `gh` shutil.which check inside run_propagate_anchor still requires
        # gh in PATH; skip if not available.
        if not shutil.which("gh"):
            pytest.skip("gh CLI not available in test environment")
        rc = run_propagate_anchor(
            ai_ops_root=ai_ops_root,
            project=project,
            dry_run=True,
        )

    assert rc == 0
    captured = capsys.readouterr()
    assert "owner/dryrun-e2e" in captured.out
    assert "would create branch" in captured.out
