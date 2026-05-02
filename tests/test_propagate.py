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


def _add_self_origin(project: Path) -> str:
    """Add a bare-clone of `project` as `origin`, fetch, and return the
    detected default branch name. Lets tests exercise the
    `_harness_toml_on_branch` check without a real remote."""
    bare = project.parent / f"{project.name}-bare.git"
    subprocess.run(
        ["git", "clone", "--bare", "-q", str(project), str(bare)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(project), "remote", "add", "origin", str(bare)],
        check=True,
    )
    branch = subprocess.run(
        ["git", "-C", str(project), "branch", "--show-current"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(project), "fetch", "-q", "origin"],
        check=True,
    )
    return branch


def test_target_list_includes_drifted_managed_project(tmp_path: Path) -> None:
    """A managed project with only ai_ops_sha drift is a valid target."""
    from ai_ops.propagate import list_anchor_sync_targets

    ai_ops_root = Path(__file__).resolve().parent.parent
    project = _make_managed_project(
        tmp_path, "drifted",
        ai_ops_sha="0000000000000000000000000000000000000000",
    )
    default_branch = _add_self_origin(project)

    with patch(
        "ai_ops.propagate._gh_repo_metadata",
        return_value=(default_branch, "owner/drifted"),
    ):
        targets, skips = list_anchor_sync_targets(ai_ops_root, [project])

    assert len(targets) == 1
    target = targets[0]
    assert target.project_path == project
    assert target.current_sha == "0000000000000000000000000000000000000000"
    # new_sha should be the actual ai-ops HEAD (40-char hex)
    assert len(target.new_sha) == 40
    assert target.default_branch == default_branch
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


def test_target_list_skips_when_manifest_only_on_feature_branch(
    tmp_path: Path,
) -> None:
    """If `.ai-ops/harness.toml` is committed only on a feature branch and
    not on the default branch, anchor-sync must skip — branching from default
    would find no manifest to update.

    Regression: real-world run on paasukusai/mi_share crashed because the
    file was on `repo-restructure` branch only, never merged to `master`.
    The earlier check (`ls-files --error-unmatch`) ran against current HEAD
    and incorrectly returned True.
    """
    from ai_ops.propagate import list_anchor_sync_targets

    ai_ops_root = Path(__file__).resolve().parent.parent

    # Set up a project with manifest on a feature branch only.
    project = tmp_path / "feat-only"
    project.mkdir()
    _git_init_committed(project, name="readme")
    # Default branch is set by `git init` (could be main or master); take it
    # from the current branch name after init.
    default_branch_result = subprocess.run(
        ["git", "-C", str(project), "branch", "--show-current"],
        capture_output=True, text=True, check=True,
    )
    default_branch = default_branch_result.stdout.strip()

    # Switch to a feature branch and commit harness.toml there.
    subprocess.run(
        ["git", "-C", str(project), "checkout", "-q", "-b", "feature"],
        check=True,
    )
    (project / ".ai-ops").mkdir()
    (project / "AGENTS.md").write_text("agents\n", encoding="utf-8")
    from ai_ops.audit.harness import HarnessManifest, _sha256
    files_hashes = {"AGENTS.md": _sha256(project / "AGENTS.md")}
    manifest = HarnessManifest(
        ai_ops_sha="0000000000000000000000000000000000000000",
        last_sync="2026-04-29T00:00:00+00:00",
        harness_files=files_hashes,
    )
    (project / ".ai-ops" / "harness.toml").write_text(
        manifest.to_toml(), encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(project), "add", "AGENTS.md", ".ai-ops/harness.toml"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(project), "commit", "-q", "-m", "feat harness"],
        check=True,
    )

    # Add an "origin" remote pointing to itself, then create origin/<default_branch>
    # as a copy of the default branch (which doesn't have harness.toml).
    bare = tmp_path / "feat-only-bare.git"
    subprocess.run(
        ["git", "clone", "--bare", "-q", str(project), str(bare)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(project), "remote", "add", "origin", str(bare)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(project), "fetch", "-q", "origin"],
        check=True,
    )

    with patch(
        "ai_ops.propagate._gh_repo_metadata",
        return_value=(default_branch, "owner/feat-only"),
    ):
        targets, skips = list_anchor_sync_targets(ai_ops_root, [project])

    assert targets == []
    assert any(
        f"absent on origin/{default_branch}" in s.reason
        and s.project_path == project
        for s in skips
    ), f"expected skip with 'absent on origin/{default_branch}' but got: {skips}"


def _make_untracked_manifest_project(
    tmp_path: Path,
    name: str,
) -> Path:
    """Create a project with a valid `.ai-ops/harness.toml` on disk that
    is NOT tracked in git (the exact gap propagate-init handles)."""
    project = tmp_path / name
    project.mkdir()
    _git_init_committed(project, name="readme")  # initial commit for default branch

    (project / ".ai-ops").mkdir()
    (project / "AGENTS.md").write_text("agents\n", encoding="utf-8")
    from ai_ops.audit.harness import HarnessManifest, _sha256
    files_hashes = {"AGENTS.md": _sha256(project / "AGENTS.md")}
    manifest = HarnessManifest(
        ai_ops_sha="0000000000000000000000000000000000000000",
        last_sync="2026-04-29T00:00:00+00:00",
        harness_files=files_hashes,
    )
    (project / ".ai-ops" / "harness.toml").write_text(
        manifest.to_toml(), encoding="utf-8",
    )
    # Note: harness.toml is NOT git add'd — that's the whole point.
    return project


def test_init_target_includes_untracked_manifest(tmp_path: Path) -> None:
    """Project with `.ai-ops/harness.toml` on disk but untracked → init target."""
    from ai_ops.propagate import list_init_targets

    ai_ops_root = Path(__file__).resolve().parent.parent
    project = _make_untracked_manifest_project(tmp_path, "init-candidate")
    default_branch = _add_self_origin(project)

    with patch(
        "ai_ops.propagate._gh_repo_metadata",
        return_value=(default_branch, "owner/init-candidate"),
    ):
        targets, skips = list_init_targets(ai_ops_root, [project])

    assert len(targets) == 1
    assert targets[0].project_path == project
    assert targets[0].repo_full_name == "owner/init-candidate"
    assert "ai_ops_sha = \"0000" in targets[0].manifest_text


def test_init_target_skips_tracked_manifest(tmp_path: Path) -> None:
    """Project with manifest already tracked → not an init target (anchor's job)."""
    from ai_ops.propagate import list_init_targets

    ai_ops_root = Path(__file__).resolve().parent.parent
    project = _make_managed_project(
        tmp_path, "tracked",
        ai_ops_sha="0000000000000000000000000000000000000000",
    )
    default_branch = _add_self_origin(project)

    with patch(
        "ai_ops.propagate._gh_repo_metadata",
        return_value=(default_branch, "owner/tracked"),
    ):
        targets, skips = list_init_targets(ai_ops_root, [project])

    assert targets == []  # already tracked → not init's job
    # No skip surfaced either (it's silently out of init's scope, not an issue).


def test_init_target_skips_invalid_manifest(tmp_path: Path) -> None:
    """`.ai-ops/harness.toml` that doesn't parse → skipped with reason."""
    from ai_ops.propagate import list_init_targets

    ai_ops_root = Path(__file__).resolve().parent.parent
    project = tmp_path / "invalid-mfst"
    project.mkdir()
    _git_init_committed(project, name="readme")
    (project / ".ai-ops").mkdir()
    (project / ".ai-ops" / "harness.toml").write_text(
        "not = valid toml [[[\n", encoding="utf-8",
    )
    default_branch = _add_self_origin(project)

    with patch(
        "ai_ops.propagate._gh_repo_metadata",
        return_value=(default_branch, "owner/invalid-mfst"),
    ):
        targets, skips = list_init_targets(ai_ops_root, [project])

    assert targets == []
    assert any(
        "invalid" in s.reason and s.project_path == project
        for s in skips
    )


def test_init_one_bumps_ai_ops_sha_to_passed_head(tmp_path: Path) -> None:
    """init_one must replace the captured ai_ops_sha with the current HEAD
    sha passed in, so the merged manifest doesn't appear stale immediately.

    Without this, the init PR would freeze whatever sha the user happened
    to be synced to, forcing a redundant anchor-sync PR right after merge.
    """
    from ai_ops.propagate import (
        InitHarnessTarget, _write_updated_manifest, init_one,
    )
    from ai_ops.audit.harness import HarnessManifest

    project = _make_untracked_manifest_project(tmp_path, "bump-test")
    default_branch = _add_self_origin(project)

    captured_text = (
        'ai_ops_sha = "0000000000000000000000000000000000000000"\n'
        'last_sync = "2026-01-01T00:00:00+00:00"\n\n'
        '[harness_files]\n'
        '"AGENTS.md" = "deadbeef"\n'
    )
    target = InitHarnessTarget(
        project_path=project,
        default_branch=default_branch,
        repo_full_name="owner/bump-test",
        manifest_text=captured_text,
    )

    # Mock gh pr list (no existing) and gh pr create (success) so we can
    # observe the actual file written into the worktree before cleanup.
    fresh_sha = "abcdef1234567890abcdef1234567890abcdef12"

    captured_written: dict[str, str] = {}
    real_write = _write_updated_manifest  # not used here, demonstrates pattern

    # Patch gh and capture the manifest written into the worktree by
    # intercepting the worktree path before cleanup deletes it.
    real_subprocess_run = subprocess.run
    pr_list_called = []

    def mock_subprocess_run(args, **kwargs):
        # Let real git commands run, but intercept gh.
        if args and args[0] == "gh":
            if args[1] == "pr" and args[2] == "list":
                pr_list_called.append(True)
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="[]", stderr="",
                )
            if args[1] == "pr" and args[2] == "create":
                # Read the manifest from the worktree (which is the cwd).
                cwd = kwargs.get("cwd")
                if cwd:
                    manifest_path = Path(cwd) / ".ai-ops" / "harness.toml"
                    if manifest_path.exists():
                        captured_written["text"] = manifest_path.read_text(
                            encoding="utf-8"
                        )
                return subprocess.CompletedProcess(
                    args=args, returncode=0,
                    stdout="https://github.com/owner/bump-test/pull/1",
                    stderr="",
                )
        return real_subprocess_run(args, **kwargs)

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        ok, msg = init_one(target, ai_ops_sha=fresh_sha, dry_run=False)

    assert ok, f"init_one failed: {msg}"
    assert "text" in captured_written, "manifest was not written before PR"

    written = HarnessManifest.from_toml(captured_written["text"])
    assert written.ai_ops_sha == fresh_sha, (
        f"expected ai_ops_sha={fresh_sha}, got {written.ai_ops_sha}"
    )
    # harness_files should be preserved from captured manifest as-is.
    assert written.harness_files == {"AGENTS.md": "deadbeef"}
    # last_sync should be updated to a recent ISO timestamp (not the 2026-01-01
    # value from captured_text).
    assert "2026-01-01" not in written.last_sync


def test_init_one_dry_run_has_no_side_effects(tmp_path: Path) -> None:
    """`init_one(dry_run=True)` writes nothing and makes no git calls."""
    from ai_ops.propagate import InitHarnessTarget, init_one

    project = _make_untracked_manifest_project(tmp_path, "dryrun-init")
    target = InitHarnessTarget(
        project_path=project,
        default_branch="main",
        repo_full_name="owner/dryrun-init",
        manifest_text="ai_ops_sha = \"0000\"\n",
    )

    git_status_before = subprocess.run(
        ["git", "-C", str(project), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout

    ok, msg = init_one(target, ai_ops_sha="abcdef0123456789", dry_run=True)

    assert ok is True
    assert "would create branch" in msg
    git_status_after = subprocess.run(
        ["git", "-C", str(project), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert git_status_before == git_status_after


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
    default_branch = _add_self_origin(project)

    with patch(
        "ai_ops.propagate._gh_repo_metadata",
        return_value=(default_branch, "owner/dryrun-e2e"),
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
