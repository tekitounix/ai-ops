"""Anchor-sync propagation: open PRs that bump `ai_ops_sha` in managed projects.

Scope is intentionally minimal — this module touches `.ai-ops/harness.toml`'s
`ai_ops_sha` and `last_sync` fields only. User-authored content (AGENTS.md,
plans, source) is never modified. Each PR is opened on a separate branch via
`gh pr create`, never merged automatically. Worktree-based isolation ensures
the user's working directory and current branch are never touched.

This is the first of several increment plans split out of the original
`automated-propagation` plan after self-audit revealed too many open design
questions for a single-shot implementation.
"""
from __future__ import annotations

import dataclasses
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from ai_ops.audit.harness import (
    HARNESS_MANIFEST,
    HarnessManifest,
    _ai_ops_head_sha,
    _now_iso,
    detect_drift,
)
from ai_ops.audit.nix import _ghq_list_paths
from ai_ops.audit.projects import _is_ai_ops_repo


# ─────────────────────────────────────────────────────
# Target collection
# ─────────────────────────────────────────────────────


@dataclasses.dataclass
class AnchorSyncTarget:
    """A managed project eligible for anchor-sync propagation."""

    project_path: Path
    current_sha: str
    new_sha: str
    default_branch: str
    repo_full_name: str  # e.g. "tekitounix/umipal"


@dataclasses.dataclass
class SkipReason:
    """Why a project was skipped (surfaced to user, never silent)."""

    project_path: Path
    reason: str


def _harness_toml_is_tracked(project: Path) -> bool:
    """Returns True if `.ai-ops/harness.toml` is tracked in git (not untracked).

    Checks against the current HEAD/index. Use `_harness_toml_on_branch` to
    verify presence on a specific remote branch (which is what matters for
    PR base selection).
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(project), "ls-files", "--error-unmatch", HARNESS_MANIFEST],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _harness_toml_on_branch(project: Path, ref: str) -> bool:
    """Returns True if `.ai-ops/harness.toml` exists on the given ref.

    Critical for anchor-sync: the PR's base branch must contain the manifest,
    otherwise the worktree branched from base won't have the file to update.
    Real-world bug surfaced this: a project committed `.ai-ops/harness.toml`
    only on a feature branch, never merged to default — anchor-sync attempted
    to branch from `origin/master` and crashed because the file was absent.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(project), "cat-file", "-e",
             f"{ref}:{HARNESS_MANIFEST}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _gh_repo_metadata(project: Path) -> tuple[str, str] | None:
    """Returns (default_branch, repo_full_name) or None if not a GitHub repo
    or `gh` is unavailable."""
    if not shutil.which("gh"):
        return None
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "defaultBranchRef,nameWithOwner", "-q",
             ".defaultBranchRef.name + \"\\t\" + .nameWithOwner"],
            cwd=str(project),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        out = result.stdout.strip()
        if "\t" not in out:
            return None
        branch, repo_full_name = out.split("\t", 1)
        return branch.strip(), repo_full_name.strip()
    except (subprocess.SubprocessError, OSError):
        return None


def list_anchor_sync_targets(
    ai_ops_root: Path,
    project_paths: list[Path] | None = None,
) -> tuple[list[AnchorSyncTarget], list[SkipReason]]:
    """Walk managed projects and return (targets, skip_reasons).

    A project becomes a Target iff:
    - `.ai-ops/harness.toml` exists AND is git-tracked
    - `ai_ops_sha_drift` is True
    - No `missing` / `modified` / `extra` harness files (those need a
      separate sync plan, not anchor-only)
    - GitHub-hosted (`gh repo view` returns metadata)
    - Not ai-ops itself
    """
    head_sha = _ai_ops_head_sha(ai_ops_root)
    if not head_sha:
        return [], []

    if project_paths is None:
        project_paths = _ghq_list_paths()

    targets: list[AnchorSyncTarget] = []
    skips: list[SkipReason] = []

    for project in project_paths:
        if _is_ai_ops_repo(project):
            skips.append(SkipReason(project, "ai-ops itself (mgd=src)"))
            continue
        manifest_path = project / HARNESS_MANIFEST
        if not manifest_path.is_file():
            skips.append(SkipReason(project, "no .ai-ops/harness.toml"))
            continue
        if not _harness_toml_is_tracked(project):
            skips.append(SkipReason(
                project,
                ".ai-ops/harness.toml is untracked — commit it first",
            ))
            continue

        try:
            drift = detect_drift(project, ai_ops_root)
        except Exception as exc:
            skips.append(SkipReason(project, f"detect_drift failed: {exc}"))
            continue

        if drift.missing or drift.modified or drift.extra:
            details = []
            if drift.missing:
                details.append(f"missing={len(drift.missing)}")
            if drift.modified:
                details.append(f"modified={len(drift.modified)}")
            if drift.extra:
                details.append(f"extra={len(drift.extra)}")
            skips.append(SkipReason(
                project,
                f"file drift present ({', '.join(details)}) — needs harness-files-sync plan",
            ))
            continue

        if not drift.ai_ops_sha_drift:
            # Already in sync — nothing to do, not surfaced as skip.
            continue

        gh_meta = _gh_repo_metadata(project)
        if gh_meta is None:
            skips.append(SkipReason(
                project,
                "not a GitHub repo or `gh` unavailable",
            ))
            continue

        default_branch, repo_full_name = gh_meta

        # Fetch the default branch so we can verify the manifest is present
        # there. Without this, a manifest committed only on a feature branch
        # (never merged to default) would crash anchor_sync_one when the
        # worktree branched from origin/<default> finds no harness.toml.
        fetch = subprocess.run(
            ["git", "-C", str(project), "fetch", "origin", default_branch],
            capture_output=True, text=True, check=False, timeout=15,
        )
        if fetch.returncode != 0:
            skips.append(SkipReason(
                project,
                f"git fetch origin {default_branch} failed: "
                f"{fetch.stderr.strip()[:80]}",
            ))
            continue

        if not _harness_toml_on_branch(project, f"origin/{default_branch}"):
            skips.append(SkipReason(
                project,
                f".ai-ops/harness.toml absent on origin/{default_branch} — "
                f"merge it to {default_branch} first",
            ))
            continue

        try:
            manifest = HarnessManifest.from_toml(
                manifest_path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            skips.append(SkipReason(project, f"manifest parse failed: {exc}"))
            continue

        targets.append(AnchorSyncTarget(
            project_path=project,
            current_sha=manifest.ai_ops_sha,
            new_sha=head_sha,
            default_branch=default_branch,
            repo_full_name=repo_full_name,
        ))

    return targets, skips


# ─────────────────────────────────────────────────────
# Per-target execution
# ─────────────────────────────────────────────────────


def _worktree_dir(target: AnchorSyncTarget) -> Path:
    """Where the isolated worktree lives during propagation.

    Uses ~/.cache/ai-ops/worktrees/<repo-name>-anchor-sync-<short-sha>/
    so the user's working directory is never touched.
    """
    short = target.new_sha[:7]
    return (
        Path.home()
        / ".cache" / "ai-ops" / "worktrees"
        / f"{target.project_path.name}-anchor-sync-{short}"
    )


def _branch_name(target: AnchorSyncTarget) -> str:
    return f"ai-ops/anchor-sync-{target.new_sha[:7]}"


def _pr_already_exists(target: AnchorSyncTarget) -> bool:
    """True if a PR with the same head branch is already open or closed.

    Avoids re-opening identical PRs after a previous propagation cycle.
    """
    branch = _branch_name(target)
    try:
        result = subprocess.run(
            ["gh", "pr", "list",
             "--repo", target.repo_full_name,
             "--head", branch,
             "--state", "all",
             "--json", "number"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode != 0:
            return False
        return result.stdout.strip() not in ("", "[]")
    except (subprocess.SubprocessError, OSError):
        return False


def _pr_body(target: AnchorSyncTarget) -> str:
    short_old = target.current_sha[:7] if target.current_sha else "(empty)"
    short_new = target.new_sha[:7]
    return f"""Auto-generated by `ai-ops propagate-anchor`.

This PR bumps `.ai-ops/harness.toml`'s `ai_ops_sha` from `{short_old}` to
`{short_new}` so subsequent `ai-ops audit harness` and `ai-ops audit standard`
runs use the latest ai-ops repository as their reference baseline.

**No file content changes** — only the manifest's `ai_ops_sha` and `last_sync`
fields are updated. Harness file hashes in `[harness_files]` are left as-is.
If `ai-ops audit harness --strict` reports drift after merging this PR, that
indicates real file content drift (handled by a separate sync plan, not this
anchor-only propagation).

Source: https://github.com/tekitounix/ai-ops/commit/{target.new_sha}
"""


def _write_updated_manifest(
    manifest_path: Path,
    new_sha: str,
) -> None:
    """Update only `ai_ops_sha` and `last_sync`, preserve `[harness_files]`."""
    text = manifest_path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    manifest = HarnessManifest(
        ai_ops_sha=new_sha,
        last_sync=_now_iso(),
        harness_files=dict(data.get("harness_files", {})),
    )
    manifest_path.write_text(manifest.to_toml(), encoding="utf-8")


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _cleanup_worktree(project: Path, worktree_path: Path, branch: str) -> None:
    """Best-effort removal of worktree and local branch. Never raises."""
    if worktree_path.exists():
        try:
            subprocess.run(
                ["git", "-C", str(project), "worktree", "remove", "--force",
                 str(worktree_path)],
                capture_output=True, text=True, check=False, timeout=15,
            )
        except (subprocess.SubprocessError, OSError):
            pass
    # Branch may have been deleted by `worktree remove`; --force handles both.
    try:
        subprocess.run(
            ["git", "-C", str(project), "branch", "-D", branch],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        pass


def anchor_sync_one(
    target: AnchorSyncTarget,
    *,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Execute anchor sync for a single target. Returns (success, message).

    Uses git worktree to ensure the user's working directory and current
    branch are never touched. Cleans up worktree and local branch on both
    success and failure (try/finally guarantee).
    """
    branch = _branch_name(target)
    worktree_path = _worktree_dir(target)

    if dry_run:
        msg = (
            f"[dry-run] would create branch {branch} in worktree {worktree_path}\n"
            f"           and open PR titled 'chore(harness): bump ai_ops_sha to "
            f"{target.new_sha[:7]}'"
        )
        return True, msg

    if _pr_already_exists(target):
        return True, f"PR for branch {branch} already exists — skipped"

    try:
        # Create worktree from default branch's remote tip.
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        if worktree_path.exists():
            return False, (
                f"worktree path {worktree_path} already exists — "
                f"remove manually with `git worktree remove --force` and retry"
            )

        # Fetch the remote default branch first to ensure we branch from latest.
        fetch = _run_git(["fetch", "origin", target.default_branch],
                         target.project_path)
        if fetch.returncode != 0:
            return False, f"git fetch failed: {fetch.stderr.strip()}"

        wt_result = _run_git(
            ["worktree", "add", "-b", branch, str(worktree_path),
             f"origin/{target.default_branch}"],
            target.project_path,
        )
        if wt_result.returncode != 0:
            return False, f"git worktree add failed: {wt_result.stderr.strip()}"

        # Apply manifest update inside worktree.
        _write_updated_manifest(worktree_path / HARNESS_MANIFEST, target.new_sha)

        # Commit.
        commit_msg = (
            f"chore(harness): bump ai_ops_sha to {target.new_sha[:7]}\n\n"
            f"Auto-generated by `ai-ops propagate-anchor`. Updates the\n"
            f"manifest's `ai_ops_sha` and `last_sync` only — no file content\n"
            f"changes. Source: https://github.com/tekitounix/ai-ops/commit/"
            f"{target.new_sha}"
        )
        add = _run_git(["add", HARNESS_MANIFEST], worktree_path)
        if add.returncode != 0:
            return False, f"git add failed: {add.stderr.strip()}"
        commit = _run_git(["commit", "-m", commit_msg], worktree_path)
        if commit.returncode != 0:
            return False, f"git commit failed: {commit.stderr.strip()}"

        # Push.
        push = _run_git(["push", "-u", "origin", branch], worktree_path)
        if push.returncode != 0:
            return False, f"git push failed: {push.stderr.strip()}"

        # Open PR.
        pr_title = f"chore(harness): bump ai_ops_sha to {target.new_sha[:7]}"
        pr = subprocess.run(
            ["gh", "pr", "create",
             "--repo", target.repo_full_name,
             "--base", target.default_branch,
             "--head", branch,
             "--title", pr_title,
             "--body", _pr_body(target)],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if pr.returncode != 0:
            return False, f"gh pr create failed: {pr.stderr.strip()}"

        pr_url = pr.stdout.strip()
        return True, f"PR opened: {pr_url}"

    finally:
        _cleanup_worktree(target.project_path, worktree_path, branch)


# ─────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────


def _confirm(prompt: str) -> bool:
    """Read a y/N answer from stdin. Default is No."""
    try:
        ans = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return ans in ("y", "yes")


# ─────────────────────────────────────────────────────
# init-harness propagation: commit untracked .ai-ops/harness.toml
# ─────────────────────────────────────────────────────


@dataclasses.dataclass
class InitHarnessTarget:
    """A managed project where `.ai-ops/harness.toml` exists on disk but
    is not yet tracked in git on the default branch."""

    project_path: Path
    default_branch: str
    repo_full_name: str
    manifest_text: str  # captured from user's working copy at scan time


def _harness_toml_untracked(project: Path) -> bool:
    """True iff `.ai-ops/harness.toml` exists on disk but is not in git index
    (neither staged nor previously committed on the current branch)."""
    if not (project / HARNESS_MANIFEST).is_file():
        return False
    return not _harness_toml_is_tracked(project)


def list_init_targets(
    ai_ops_root: Path,
    project_paths: list[Path] | None = None,
) -> tuple[list[InitHarnessTarget], list[SkipReason]]:
    """Find managed projects whose `.ai-ops/harness.toml` is untracked on
    disk and absent on the default branch — exactly the gap propagate-init
    fills."""
    if project_paths is None:
        project_paths = _ghq_list_paths()

    targets: list[InitHarnessTarget] = []
    skips: list[SkipReason] = []

    for project in project_paths:
        if _is_ai_ops_repo(project):
            continue
        manifest_path = project / HARNESS_MANIFEST
        if not manifest_path.is_file():
            # Not a candidate (no manifest at all). Don't surface as skip
            # because it's not in scope (init only handles existing-but-
            # untracked).
            continue
        if _harness_toml_is_tracked(project):
            # Already tracked somewhere — anchor-sync's job, not init's.
            continue

        # Validate it's a parseable HarnessManifest before considering for PR.
        try:
            manifest_text = manifest_path.read_text(encoding="utf-8")
            HarnessManifest.from_toml(manifest_text)
        except Exception as exc:
            skips.append(SkipReason(
                project,
                f".ai-ops/harness.toml present but invalid: {exc}",
            ))
            continue

        gh_meta = _gh_repo_metadata(project)
        if gh_meta is None:
            skips.append(SkipReason(
                project, "not a GitHub repo or `gh` unavailable",
            ))
            continue
        default_branch, repo_full_name = gh_meta

        # Fetch so we can verify absence on default branch (init is the
        # opposite check from anchor-sync).
        fetch = subprocess.run(
            ["git", "-C", str(project), "fetch", "origin", default_branch],
            capture_output=True, text=True, check=False, timeout=15,
        )
        if fetch.returncode != 0:
            skips.append(SkipReason(
                project,
                f"git fetch origin {default_branch} failed: "
                f"{fetch.stderr.strip()[:80]}",
            ))
            continue

        if _harness_toml_on_branch(project, f"origin/{default_branch}"):
            # Already on default branch — anchor-sync's territory or just no-op.
            continue

        targets.append(InitHarnessTarget(
            project_path=project,
            default_branch=default_branch,
            repo_full_name=repo_full_name,
            manifest_text=manifest_text,
        ))

    return targets, skips


def _init_branch_name(target: InitHarnessTarget, ai_ops_sha: str) -> str:
    return f"ai-ops/init-harness-{ai_ops_sha[:7]}"


def _init_pr_body(target: InitHarnessTarget) -> str:
    return """Auto-generated by `ai-ops propagate-init`.

This PR adds `.ai-ops/harness.toml` to the repository so subsequent
`ai-ops audit harness` and `ai-ops audit projects` runs can track this
project as a managed ai-ops consumer.

The manifest content was captured from the local working copy at the
time of propagation. No other files are added or modified by this PR.

Once merged, future ai-ops improvements will surface as `ai-ops/anchor-
sync-<sha>` PRs from `ai-ops propagate-anchor`.
"""


def init_one(
    target: InitHarnessTarget,
    *,
    ai_ops_sha: str,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Add the untracked `.ai-ops/harness.toml` via worktree + PR."""
    branch = _init_branch_name(target, ai_ops_sha)
    worktree_path = (
        Path.home() / ".cache" / "ai-ops" / "worktrees"
        / f"{target.project_path.name}-init-harness-{ai_ops_sha[:7]}"
    )

    if dry_run:
        return True, (
            f"[dry-run] would create branch {branch}, add .ai-ops/harness.toml, "
            f"and open PR titled 'chore(harness): init ai-ops harness manifest'"
        )

    # Check for existing PR with same head.
    try:
        existing = subprocess.run(
            ["gh", "pr", "list",
             "--repo", target.repo_full_name,
             "--head", branch,
             "--state", "all",
             "--json", "number"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        if existing.returncode == 0 and existing.stdout.strip() not in ("", "[]"):
            return True, f"PR for branch {branch} already exists — skipped"
    except (subprocess.SubprocessError, OSError):
        pass

    try:
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        if worktree_path.exists():
            return False, (
                f"worktree path {worktree_path} already exists — "
                f"remove manually with `git worktree remove --force` and retry"
            )

        wt_result = _run_git(
            ["worktree", "add", "-b", branch, str(worktree_path),
             f"origin/{target.default_branch}"],
            target.project_path,
        )
        if wt_result.returncode != 0:
            return False, f"git worktree add failed: {wt_result.stderr.strip()}"

        # Create .ai-ops/ and write manifest with ai_ops_sha bumped to
        # current HEAD. Without the bump, the freshly merged manifest would
        # immediately appear stale (since the captured manifest_text records
        # whatever ai_ops_sha the user happened to be on when init scanned),
        # forcing a follow-up anchor-sync PR. By bumping here, the init PR
        # itself brings the project up to date.
        (worktree_path / ".ai-ops").mkdir(exist_ok=True)
        try:
            captured = HarnessManifest.from_toml(target.manifest_text)
        except Exception as exc:
            return False, f"captured manifest invalid: {exc}"
        bumped = HarnessManifest(
            ai_ops_sha=ai_ops_sha,
            last_sync=_now_iso(),
            harness_files=captured.harness_files,
        )
        (worktree_path / HARNESS_MANIFEST).write_text(
            bumped.to_toml(), encoding="utf-8",
        )

        commit_msg = (
            "chore(harness): init ai-ops harness manifest\n\n"
            "Auto-generated by `ai-ops propagate-init`. Adds the manifest\n"
            "with ai_ops_sha set to the current ai-ops HEAD\n"
            f"({ai_ops_sha}) so the project starts in sync. The\n"
            "`[harness_files]` hashes are captured from the local working\n"
            "copy as-is — file content drift, if any, is reported separately\n"
            "by `ai-ops audit harness`."
        )
        add = _run_git(["add", HARNESS_MANIFEST], worktree_path)
        if add.returncode != 0:
            return False, f"git add failed: {add.stderr.strip()}"
        commit = _run_git(["commit", "-m", commit_msg], worktree_path)
        if commit.returncode != 0:
            return False, f"git commit failed: {commit.stderr.strip()}"

        push = _run_git(["push", "-u", "origin", branch], worktree_path)
        if push.returncode != 0:
            return False, f"git push failed: {push.stderr.strip()}"

        pr_title = "chore(harness): init ai-ops harness manifest"
        pr = subprocess.run(
            ["gh", "pr", "create",
             "--repo", target.repo_full_name,
             "--base", target.default_branch,
             "--head", branch,
             "--title", pr_title,
             "--body", _init_pr_body(target)],
            cwd=str(worktree_path),
            capture_output=True, text=True, check=False, timeout=30,
        )
        if pr.returncode != 0:
            return False, f"gh pr create failed: {pr.stderr.strip()}"

        return True, f"PR opened: {pr.stdout.strip()}"

    finally:
        _cleanup_worktree(target.project_path, worktree_path, branch)


def run_propagate_init(
    *,
    ai_ops_root: Path,
    project: Path | None = None,
    all_projects: bool = False,
    dry_run: bool = False,
) -> int:
    """Entry point for `ai-ops propagate-init`."""
    if not project and not all_projects:
        print("Error: specify --project <path> or --all", file=sys.stderr)
        return 2

    if not shutil.which("gh"):
        print("Error: `gh` CLI is required (tier-1 ai-ops dependency)",
              file=sys.stderr)
        return 1

    head_sha = _ai_ops_head_sha(ai_ops_root)
    if not head_sha:
        print("Error: could not determine ai-ops HEAD sha", file=sys.stderr)
        return 1

    project_paths = [project.resolve()] if project else None
    targets, skips = list_init_targets(ai_ops_root, project_paths)

    if skips:
        print("Skipped projects:")
        for s in skips:
            print(f"  - {s.project_path.name}: {s.reason}")
        print()

    if not targets:
        print("No init-harness targets found.")
        return 0

    print(f"Init-harness targets ({len(targets)}):")
    for t in targets:
        print(f"  - {t.repo_full_name} (branch={t.default_branch})")
    print()

    fail_count = 0
    for t in targets:
        if dry_run:
            ok, msg = init_one(t, ai_ops_sha=head_sha, dry_run=True)
            print(f"[{t.repo_full_name}] {msg}")
            if not ok:
                fail_count += 1
            continue

        if not _confirm(f"Initialise harness in {t.repo_full_name}? [y/N]: "):
            print(f"[{t.repo_full_name}] skipped by user")
            continue

        ok, msg = init_one(t, ai_ops_sha=head_sha, dry_run=False)
        prefix = "OK" if ok else "FAIL"
        print(f"[{t.repo_full_name}] {prefix}: {msg}")
        if not ok:
            fail_count += 1

    return 1 if fail_count else 0


def run_propagate_anchor(
    *,
    ai_ops_root: Path,
    project: Path | None = None,
    all_projects: bool = False,
    dry_run: bool = False,
) -> int:
    """Entry point for `ai-ops propagate-anchor`.

    Per-project confirmation (Y/n) is required for each target unless
    `dry_run` is set. AGENTS.md Operation Model treats project-specific
    harness overwrite as requiring per-project confirmation explicitly.
    """
    if not project and not all_projects:
        print(
            "Error: specify --project <path> or --all",
            file=sys.stderr,
        )
        return 2

    if not shutil.which("gh"):
        print("Error: `gh` CLI is required (tier-1 ai-ops dependency)",
              file=sys.stderr)
        return 1

    project_paths = [project.resolve()] if project else None
    targets, skips = list_anchor_sync_targets(ai_ops_root, project_paths)

    if skips:
        print("Skipped projects:")
        for s in skips:
            print(f"  - {s.project_path.name}: {s.reason}")
        print()

    if not targets:
        print("No anchor-sync targets found.")
        return 0

    print(f"Anchor-sync targets ({len(targets)}):")
    for t in targets:
        old = t.current_sha[:7] if t.current_sha else "(empty)"
        print(f"  - {t.repo_full_name}: {old} → {t.new_sha[:7]} "
              f"(branch={t.default_branch})")
    print()

    fail_count = 0
    for t in targets:
        if dry_run:
            ok, msg = anchor_sync_one(t, dry_run=True)
            print(f"[{t.repo_full_name}] {msg}")
            if not ok:
                fail_count += 1
            continue

        if not _confirm(f"Propagate to {t.repo_full_name}? [y/N]: "):
            print(f"[{t.repo_full_name}] skipped by user")
            continue

        ok, msg = anchor_sync_one(t, dry_run=False)
        prefix = "OK" if ok else "FAIL"
        print(f"[{t.repo_full_name}] {prefix}: {msg}")
        if not ok:
            fail_count += 1

    return 1 if fail_count else 0
