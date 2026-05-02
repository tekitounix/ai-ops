"""Worktree-based parallel work helpers (ADR 0010).

Defaults to the sibling layout (`<repo-parent>/<repo-name>.<slug>/`) and
the 1:1:1 binding between plan slug, branch name, and worktree path. The
helpers are intentionally narrow: they create or remove worktrees and
the bound plan, but never modify project files inside the worktree
beyond the initial plan skeleton.

Cleanup requires both signals: the branch's PR is merged AND the plan
is archived. Either signal alone leaves the worktree in place — Safety
takes precedence over convenience.
"""
from __future__ import annotations

import dataclasses
import shutil
import subprocess
import sys
from pathlib import Path

from ai_ops.lifecycle.plans import validate_slug
from ai_ops.paths import package_root, repo_root


VALID_BRANCH_TYPES: tuple[str, ...] = (
    "feat", "fix", "chore", "docs", "refactor",
)
DEFAULT_BRANCH_TYPE = "feat"
PRACTICAL_WORKTREE_LIMIT = 5  # ADR 0010 — INFO threshold


@dataclasses.dataclass
class WorktreeSpec:
    slug: str
    branch_type: str = DEFAULT_BRANCH_TYPE
    base_branch: str = "main"


@dataclasses.dataclass
class WorktreeInfo:
    """One row of `git worktree list`."""

    path: Path
    branch: str
    head_sha: str

    @property
    def is_main(self) -> bool:
        # Heuristic: the main worktree's path equals the repo root, but we
        # accept any worktree on the base branch as "main-equivalent" for
        # cleanup safety.
        return self.branch in ("refs/heads/main", "main", "refs/heads/master", "master")


def compute_branch_name(slug: str, branch_type: str = DEFAULT_BRANCH_TYPE) -> str:
    if branch_type not in VALID_BRANCH_TYPES:
        raise ValueError(
            f"branch_type must be one of {VALID_BRANCH_TYPES}, got {branch_type!r}"
        )
    return f"{branch_type}/{slug}"


def compute_worktree_path(repo_root_path: Path, slug: str) -> Path:
    """Sibling pattern: `<repo-parent>/<repo-name>.<slug>/`."""
    return repo_root_path.parent / f"{repo_root_path.name}.{slug}"


def list_worktrees(repo_root_path: Path) -> list[WorktreeInfo]:
    """Parse `git worktree list --porcelain` into structured rows."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root_path), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        if result.returncode != 0:
            return []
    except (subprocess.SubprocessError, OSError):
        return []

    out: list[WorktreeInfo] = []
    current: dict = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            if current:
                out.append(_to_worktree_info(current))
                current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = Path(line[len("worktree "):].strip())
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):].strip()
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):].strip()
    if current:
        out.append(_to_worktree_info(current))
    return out


def _to_worktree_info(raw: dict) -> WorktreeInfo:
    return WorktreeInfo(
        path=raw.get("path", Path()),
        branch=raw.get("branch", ""),
        head_sha=raw.get("head", ""),
    )


def _plan_dir_for_slug(repo_root_path: Path, slug: str) -> Path:
    return repo_root_path / "docs" / "plans" / slug


def _is_plan_archived(repo_root_path: Path, slug: str) -> bool:
    """True iff `docs/plans/<slug>/` is gone but at least one matching
    `docs/plans/archive/*-<slug>/` exists."""
    active = _plan_dir_for_slug(repo_root_path, slug)
    if active.is_dir():
        return False
    archive_root = repo_root_path / "docs" / "plans" / "archive"
    if not archive_root.is_dir():
        return False
    for entry in archive_root.iterdir():
        if entry.is_dir() and entry.name.endswith(f"-{slug}"):
            return True
    return False


def _branch_is_merged_pr(repo_root_path: Path, branch: str) -> bool | None:
    """Check whether `gh pr list --head <branch> --state merged` returns
    a non-empty result. Returns None when `gh` is unavailable or the
    query fails (treat as "unknown" for cleanup safety)."""
    if not shutil.which("gh"):
        return None
    # Strip refs/heads/ prefix if present.
    if branch.startswith("refs/heads/"):
        branch = branch[len("refs/heads/"):]
    try:
        result = subprocess.run(
            ["gh", "pr", "list",
             "--head", branch,
             "--state", "merged",
             "--json", "number"],
            cwd=str(repo_root_path),
            capture_output=True, text=True, check=False, timeout=10,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() not in ("", "[]")
    except (subprocess.SubprocessError, OSError):
        return None


def find_cleanable_worktrees(
    repo_root_path: Path,
) -> list[tuple[WorktreeInfo, str]]:
    """Return [(worktree, slug)] for worktrees whose branch's PR is
    merged AND whose plan is archived.

    Either signal alone is insufficient — both must be True. Worktrees
    where the gh check failed (None) are excluded for safety.
    """
    out: list[tuple[WorktreeInfo, str]] = []
    for wt in list_worktrees(repo_root_path):
        if wt.is_main:
            continue
        # Branch must look like `<type>/<slug>` for binding.
        branch = wt.branch.replace("refs/heads/", "", 1)
        if "/" not in branch:
            continue
        branch_type, _, slug = branch.partition("/")
        if branch_type not in VALID_BRANCH_TYPES:
            continue
        if not _is_plan_archived(repo_root_path, slug):
            continue
        merged = _branch_is_merged_pr(repo_root_path, branch)
        if merged is not True:
            continue
        out.append((wt, slug))
    return out


def create_worktree_with_plan(
    spec: WorktreeSpec,
    repo_root_path: Path,
    *,
    dry_run: bool = False,
) -> tuple[Path, Path, str]:
    """Create branch + worktree + plan skeleton. Returns (worktree_path,
    plan_md_path, branch_name)."""
    err = validate_slug(spec.slug)
    if err:
        raise ValueError(err)

    branch = compute_branch_name(spec.slug, spec.branch_type)
    worktree_path = compute_worktree_path(repo_root_path, spec.slug)
    plan_dir = _plan_dir_for_slug(repo_root_path, spec.slug)
    plan_md = plan_dir / "plan.md"

    if dry_run:
        return worktree_path, plan_md, branch

    if worktree_path.exists():
        raise FileExistsError(f"worktree path already exists: {worktree_path}")
    # Check that the branch doesn't already exist (avoid silent re-checkout).
    branch_check = subprocess.run(
        ["git", "-C", str(repo_root_path), "rev-parse", "--verify",
         f"refs/heads/{branch}"],
        capture_output=True, text=True, check=False, timeout=5,
    )
    if branch_check.returncode == 0:
        raise FileExistsError(f"branch already exists: {branch}")

    # Create the worktree (this also creates the branch).
    result = subprocess.run(
        ["git", "-C", str(repo_root_path), "worktree", "add",
         "-b", branch, str(worktree_path), spec.base_branch],
        capture_output=True, text=True, check=False, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git worktree add failed: {result.stderr.strip()}"
        )

    # Seed the plan file in the worktree (so the first commit on this
    # branch creates the plan), only if it doesn't already exist.
    plan_dir_in_wt = worktree_path / "docs" / "plans" / spec.slug
    plan_md_in_wt = plan_dir_in_wt / "plan.md"
    if not plan_md_in_wt.exists():
        plan_dir_in_wt.mkdir(parents=True, exist_ok=True)
        template = (package_root() / "templates" / "plan.md").read_text(
            encoding="utf-8"
        )
        # Lightweight title substitution: replace the placeholder title.
        title = spec.slug.replace("-", " ").replace("_", " ").title()
        seeded = template.replace(
            "<Short, action-oriented plan title>", title, 1,
        )
        plan_md_in_wt.write_text(seeded, encoding="utf-8")

    return worktree_path, plan_md, branch


def cleanup_worktree(
    info: WorktreeInfo, repo_root_path: Path, *, dry_run: bool = False,
) -> tuple[bool, str]:
    """Remove a worktree and delete its branch. Best-effort; does not
    raise on partial failure."""
    if dry_run:
        return True, f"[dry-run] would remove worktree {info.path} and branch {info.branch}"

    branch = info.branch.replace("refs/heads/", "", 1)
    # `git worktree remove` first.
    rm = subprocess.run(
        ["git", "-C", str(repo_root_path), "worktree", "remove", "--force",
         str(info.path)],
        capture_output=True, text=True, check=False, timeout=15,
    )
    if rm.returncode != 0:
        return False, f"git worktree remove failed: {rm.stderr.strip()}"

    # Then delete the local branch.
    subprocess.run(
        ["git", "-C", str(repo_root_path), "branch", "-D", branch],
        capture_output=True, text=True, check=False, timeout=10,
    )
    return True, f"removed worktree {info.path} and branch {branch}"


# ─────────────────────────────────────────────────────
# CLI entry points
# ─────────────────────────────────────────────────────


def run_worktree_new(
    *,
    slug: str,
    branch_type: str,
    base_branch: str,
    dry_run: bool,
    cwd: Path | None = None,
) -> int:
    root = cwd or repo_root() or Path.cwd().resolve()
    if not (root / ".git").exists():
        print(f"Error: not a git repository: {root}", file=sys.stderr)
        return 1
    spec = WorktreeSpec(slug=slug, branch_type=branch_type, base_branch=base_branch)
    try:
        wt_path, plan_md, branch = create_worktree_with_plan(
            spec, root, dry_run=dry_run,
        )
    except (ValueError, FileExistsError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if dry_run:
        print(f"[dry-run] would create:")
        print(f"  branch:   {branch} (from {base_branch})")
        print(f"  worktree: {wt_path}")
        print(f"  plan:     {plan_md} (in worktree, seeded from template)")
        return 0
    print(f"Created worktree:")
    print(f"  branch:   {branch}")
    print(f"  worktree: {wt_path}")
    print(f"  plan:     docs/plans/{slug}/plan.md (seeded in worktree)")
    print()
    print(f"Next: cd {wt_path} && start working")
    return 0


def run_worktree_cleanup(
    *,
    auto: bool,
    dry_run: bool,
    cwd: Path | None = None,
) -> int:
    root = cwd or repo_root() or Path.cwd().resolve()
    if not (root / ".git").exists():
        print(f"Error: not a git repository: {root}", file=sys.stderr)
        return 1

    candidates = find_cleanable_worktrees(root)
    if not candidates:
        print("No cleanable worktrees found (need merged PR + archived plan).")
        return 0

    print(f"Cleanable worktrees ({len(candidates)}):")
    for wt, slug in candidates:
        print(f"  - {wt.path} (branch {wt.branch}, slug={slug})")
    print()

    fail = 0
    for wt, slug in candidates:
        if dry_run:
            ok, msg = cleanup_worktree(wt, root, dry_run=True)
            print(f"[{slug}] {msg}")
            continue
        if not auto:
            try:
                ans = input(f"Remove worktree for slug={slug}? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                ans = ""
            if ans not in ("y", "yes"):
                print(f"[{slug}] skipped by user")
                continue
        ok, msg = cleanup_worktree(wt, root, dry_run=False)
        prefix = "OK" if ok else "FAIL"
        print(f"[{slug}] {prefix}: {msg}")
        if not ok:
            fail += 1

    return 1 if fail else 0
