"""Per-project setup helpers (ADR 0011).

Three thin helpers that distribute ai-ops's templated GitHub-native
artifacts to a managed project:

- setup-ci-workflow: copies `.github/workflows/ai-ops.yml` (caller of
  ai-ops's reusable workflow) into the project
- setup-codeowners: creates / updates `.github/CODEOWNERS` with
  ai-ops routing entries
- setup-ruleset: applies a tier ruleset via `gh api repos/.../rulesets`

The first two follow the worktree-based PR pattern (branch + worktree
+ commit + push + gh pr create). The third (ruleset) operates via the
GitHub REST API directly since it's repository configuration, not a
file change.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from ai_ops.paths import package_root


VALID_TIERS = ("A", "B", "C")  # D = no ruleset


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _gh(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True,
        check=False, timeout=30, **kwargs,
    )


def _gh_repo_metadata(project: Path) -> tuple[str, str] | None:
    """Returns (default_branch, repo_full_name) or None."""
    if not _gh_available():
        return None
    result = _gh([
        "repo", "view",
        "--json", "defaultBranchRef,nameWithOwner",
        "-q", ".defaultBranchRef.name + \"\\t\" + .nameWithOwner",
    ], cwd=str(project))
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    if "\t" not in out:
        return None
    branch, repo = out.split("\t", 1)
    return branch.strip(), repo.strip()


def _project_owner(repo_full_name: str) -> str:
    return repo_full_name.split("/", 1)[0]


def _ensure_gh() -> bool:
    if not _gh_available():
        print("Error: gh CLI is required (tier-1 ai-ops dependency)",
              file=sys.stderr)
        return False
    return True


# ─────────────────────────────────────────────────────
# Common worktree-based PR helper
# ─────────────────────────────────────────────────────


def _open_setup_pr(
    project: Path,
    branch: str,
    files: dict[str, str],  # relpath → content
    commit_title: str,
    commit_body: str,
    pr_title: str,
    pr_body: str,
    *,
    dry_run: bool = False,
    worktree_root: Path | None = None,
) -> tuple[bool, str]:
    """Branch + worktree + write files + commit + push + open PR.

    Identical pattern to propagate_*; abstracted here so setup-* helpers
    don't reimplement it. Returns (success, message).
    """
    meta = _gh_repo_metadata(project)
    if meta is None:
        return False, "not a GitHub repo or `gh` unavailable"
    default_branch, repo_full_name = meta

    if dry_run:
        msg = (
            f"[dry-run] would create branch {branch} in worktree, write "
            f"{len(files)} file(s), open PR titled '{pr_title}'"
        )
        return True, msg

    # Existence check (skip if open PR already exists for this branch).
    existing = _gh([
        "pr", "list",
        "--repo", repo_full_name,
        "--head", branch,
        "--state", "open",
        "--json", "number",
    ])
    if existing.returncode == 0 and existing.stdout.strip() not in ("", "[]"):
        return True, f"PR for branch {branch} already exists — skipped"

    root = worktree_root or (Path.home() / ".cache" / "ai-ops" / "worktrees")
    worktree_path = root / f"{project.name}-{branch.replace('/', '-')}"

    try:
        root.mkdir(parents=True, exist_ok=True)
        if worktree_path.exists():
            return False, f"worktree path {worktree_path} already exists — remove and retry"

        # Fetch + worktree add.
        fetch = subprocess.run(
            ["git", "-C", str(project), "fetch", "origin", default_branch],
            capture_output=True, text=True, check=False, timeout=15,
        )
        if fetch.returncode != 0:
            return False, f"git fetch failed: {fetch.stderr.strip()[:80]}"

        wt = subprocess.run(
            ["git", "-C", str(project), "worktree", "add",
             "-b", branch, str(worktree_path),
             f"origin/{default_branch}"],
            capture_output=True, text=True, check=False, timeout=30,
        )
        if wt.returncode != 0:
            return False, f"git worktree add failed: {wt.stderr.strip()}"

        # Write files.
        for rel, content in files.items():
            p = worktree_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")

        # Commit + push.
        for rel in files:
            subprocess.run(
                ["git", "-C", str(worktree_path), "add", rel],
                check=False,
            )
        commit_msg = f"{commit_title}\n\n{commit_body}"
        commit = subprocess.run(
            ["git", "-C", str(worktree_path), "commit", "-m", commit_msg],
            capture_output=True, text=True, check=False, timeout=15,
        )
        if commit.returncode != 0:
            # Empty commit (no diff) — file already in place. Treat as no-op.
            if "nothing to commit" in commit.stdout + commit.stderr:
                return True, "files already match; no PR needed"
            return False, f"git commit failed: {commit.stderr.strip()}"

        push = subprocess.run(
            ["git", "-C", str(worktree_path), "push", "-u", "origin", branch],
            capture_output=True, text=True, check=False, timeout=30,
        )
        if push.returncode != 0:
            return False, f"git push failed: {push.stderr.strip()}"

        pr = _gh([
            "pr", "create",
            "--repo", repo_full_name,
            "--base", default_branch,
            "--head", branch,
            "--title", pr_title,
            "--body", pr_body,
        ], cwd=str(worktree_path))
        if pr.returncode != 0:
            return False, f"gh pr create failed: {pr.stderr.strip()}"

        return True, f"PR opened: {pr.stdout.strip()}"

    finally:
        # Cleanup.
        if worktree_path.exists():
            subprocess.run(
                ["git", "-C", str(project), "worktree", "remove", "--force",
                 str(worktree_path)],
                capture_output=True, text=True, check=False, timeout=15,
            )
        subprocess.run(
            ["git", "-C", str(project), "branch", "-D", branch],
            capture_output=True, text=True, check=False, timeout=10,
        )


# ─────────────────────────────────────────────────────
# setup-ci-workflow
# ─────────────────────────────────────────────────────


def run_setup_ci_workflow(
    *,
    project: Path,
    tier: str = "D",
    ai_ops_ref: str = "main",
    dry_run: bool = False,
) -> int:
    if not _ensure_gh():
        return 1
    template_path = package_root() / "templates" / "artifacts" / ".github" / "workflows" / "ai-ops.yml"
    if not template_path.is_file():
        print(f"Error: template missing: {template_path}", file=sys.stderr)
        return 1
    content = template_path.read_text(encoding="utf-8")
    # Substitute tier, ai_ops_ref, and `@<ref>` pin in `uses:` lines.
    # PR η: `@v1` had been hard-coded but ai-ops has no `v1` tag, so the
    # reusable workflow load failed (startup_failure). The template now
    # uses `@main` and we substitute it to whatever the user passes via
    # `--ai-ops-ref`.
    content = content.replace("tier: 'D'", f"tier: '{tier}'")
    content = content.replace("ai_ops_ref: 'main'", f"ai_ops_ref: '{ai_ops_ref}'")
    content = content.replace(
        "managed-project-check.yml@main",
        f"managed-project-check.yml@{ai_ops_ref}",
    )
    content = content.replace(
        "managed-project-review.yml@main",
        f"managed-project-review.yml@{ai_ops_ref}",
    )

    files = {".github/workflows/ai-ops.yml": content}
    branch = "ai-ops/setup-ci-workflow"
    ok, msg = _open_setup_pr(
        project, branch, files,
        commit_title="chore(ci): add ai-ops drift-check workflow",
        commit_body=(
            "Auto-generated by `ai-ops setup-ci-workflow`. Adds the\n"
            "GitHub Actions workflow that calls ai-ops's reusable\n"
            f"managed-project-check workflow at tier {tier} (ADR 0011).\n"
        ),
        pr_title="chore(ci): add ai-ops drift-check workflow",
        pr_body=(
            f"Adds `.github/workflows/ai-ops.yml` calling ai-ops's "
            f"reusable workflow at tier `{tier}` (ADR 0011). "
            f"On PR + daily schedule it runs `ai-ops audit harness "
            f"--strict`. Tier B+ should also enable a ruleset (see "
            f"`ai-ops setup-ruleset --tier {tier}`)."
        ),
        dry_run=dry_run,
    )
    print(("OK" if ok else "FAIL") + ": " + msg)
    return 0 if ok else 1


# ─────────────────────────────────────────────────────
# setup-codeowners
# ─────────────────────────────────────────────────────


def run_setup_codeowners(
    *,
    project: Path,
    owner: str | None = None,
    dry_run: bool = False,
) -> int:
    if not _ensure_gh():
        return 1
    meta = _gh_repo_metadata(project)
    if meta is None:
        print("Error: not a GitHub repo or `gh` unavailable", file=sys.stderr)
        return 1
    if owner is None:
        owner = _project_owner(meta[1])

    template_path = package_root() / "templates" / "artifacts" / "CODEOWNERS.template"
    if not template_path.is_file():
        print(f"Error: template missing: {template_path}", file=sys.stderr)
        return 1
    content = template_path.read_text(encoding="utf-8").replace("<owner>", owner)

    files = {".github/CODEOWNERS": content}
    branch = "ai-ops/setup-codeowners"
    ok, msg = _open_setup_pr(
        project, branch, files,
        commit_title="chore(codeowners): route ai-ops changes to project owner",
        commit_body=(
            "Auto-generated by `ai-ops setup-codeowners`. Adds CODEOWNERS\n"
            "entries so propagate-* PRs auto-request the owner's review\n"
            "(ADR 0011).\n"
        ),
        pr_title="chore(codeowners): route ai-ops changes to project owner",
        pr_body=(
            f"Adds `.github/CODEOWNERS` routing `.ai-ops/` and "
            f"`.github/workflows/ai-ops*.yml` to @{owner}. "
            f"Per ADR 0011, this ensures every ai-ops propagation PR "
            f"is automatically queued for owner review."
        ),
        dry_run=dry_run,
    )
    print(("OK" if ok else "FAIL") + ": " + msg)
    return 0 if ok else 1


# ─────────────────────────────────────────────────────
# setup-ruleset
# ─────────────────────────────────────────────────────


def run_setup_ruleset(
    *,
    project: Path,
    tier: str,
    dry_run: bool = False,
) -> int:
    if not _ensure_gh():
        return 1
    if tier not in VALID_TIERS:
        print(f"Error: tier must be one of {VALID_TIERS}, got {tier!r}",
              file=sys.stderr)
        return 1
    meta = _gh_repo_metadata(project)
    if meta is None:
        print("Error: not a GitHub repo or `gh` unavailable", file=sys.stderr)
        return 1
    default_branch, repo = meta

    ruleset_path = package_root() / "templates" / "artifacts" / "rulesets" / f"tier-{tier.lower()}.json"
    if not ruleset_path.is_file():
        print(f"Error: ruleset template missing: {ruleset_path}", file=sys.stderr)
        return 1
    ruleset_json = ruleset_path.read_text(encoding="utf-8")
    ruleset_data = json.loads(ruleset_json)
    name = ruleset_data["name"]

    if dry_run:
        print(f"[dry-run] would upsert ruleset '{name}' on {repo} default branch")
        return 0

    # Check existing rulesets for same name (upsert).
    list_result = _gh([
        "api", f"repos/{repo}/rulesets",
        "--jq", f".[] | select(.name == \"{name}\") | .id",
    ])
    if list_result.returncode == 0 and list_result.stdout.strip():
        existing_id = list_result.stdout.strip().splitlines()[0]
        # Update via PUT.
        update = _gh([
            "api", f"repos/{repo}/rulesets/{existing_id}",
            "-X", "PUT",
            "--input", "-",
        ], input=ruleset_json)
        if update.returncode != 0:
            print(f"FAIL: ruleset PUT failed: {update.stderr.strip()}",
                  file=sys.stderr)
            return 1
        print(f"OK: updated existing ruleset '{name}' (#{existing_id}) on {repo}")
        return 0

    # Create.
    create = _gh([
        "api", f"repos/{repo}/rulesets",
        "-X", "POST",
        "--input", "-",
    ], input=ruleset_json)
    if create.returncode != 0:
        print(f"FAIL: ruleset POST failed: {create.stderr.strip()}",
              file=sys.stderr)
        return 1
    try:
        new_data = json.loads(create.stdout)
        new_id = new_data.get("id", "?")
    except json.JSONDecodeError:
        new_id = "?"
    print(f"OK: created ruleset '{name}' (#{new_id}) on {repo}")
    return 0


# ─────────────────────────────────────────────────────
# setup-ecosystem (PR ε, ADR 0011 closure)
# ─────────────────────────────────────────────────────


ECOSYSTEM_LABEL = "ecosystem"
DRIFT_LABEL = "ai-ops:drift"


def run_setup_ecosystem(
    *,
    project_name: str,
    ai_ops_repo: str = "tekitounix/ai-ops",
    owner: str | None = None,
    dry_run: bool = False,
) -> int:
    """Create an Ecosystem dashboard parent issue for `project_name` in
    `ai_ops_repo` if one does not yet exist (ADR 0011 §Move 1).

    Without this, `report-drift` (run by ecosystem-watch.yml) will WARN
    forever and never open sub-issues. PR ε closes this loop.
    """
    if not _ensure_gh():
        return 1

    title = f"Ecosystem: {project_name}"

    # Look up existing parent issue first (label + title match).
    existing = _gh([
        "issue", "list",
        "--repo", ai_ops_repo,
        "--label", ECOSYSTEM_LABEL,
        "--state", "open",
        "--search", f"in:title {project_name}",
        "--json", "number,title",
    ])
    if existing.returncode == 0 and existing.stdout.strip():
        try:
            items = json.loads(existing.stdout)
        except json.JSONDecodeError:
            items = []
        for item in items:
            if title in item.get("title", ""):
                print(f"OK: parent issue already exists: #{item['number']} ({title})")
                return 0

    body_lines = [
        f"# Ecosystem dashboard: {project_name}",
        "",
        "This is the parent issue tracking ai-ops drift signals for "
        f"`{project_name}`. Sub-issues are opened / updated / closed "
        "automatically by `ai-ops report-drift` (driven by the "
        "scheduled `ecosystem-watch.yml` workflow).",
        "",
        f"- Label: `{ECOSYSTEM_LABEL}`",
        "- Sub-issue lifecycle: opened on new drift, body updated on "
        "state change, closed when drift resolves.",
    ]
    if owner:
        body_lines.extend(["", f"Owner: @{owner}"])
    body = "\n".join(body_lines)

    if dry_run:
        print(f"[dry-run] would create parent issue '{title}' on {ai_ops_repo}")
        return 0

    # Ensure label exists (idempotent: --force).
    _gh([
        "label", "create", ECOSYSTEM_LABEL,
        "--repo", ai_ops_repo,
        "--description", "ai-ops Ecosystem dashboard parent / sub issue",
        "--color", "0E8A16",
        "--force",
    ])

    create_args = [
        "issue", "create",
        "--repo", ai_ops_repo,
        "--title", title,
        "--label", ECOSYSTEM_LABEL,
        "--body", body,
    ]
    if owner:
        create_args.extend(["--assignee", owner])
    create = _gh(create_args)
    if create.returncode != 0:
        print(f"FAIL: gh issue create failed: {create.stderr.strip()}",
              file=sys.stderr)
        return 1
    print(f"OK: created parent issue for '{project_name}' on {ai_ops_repo}")
    print(create.stdout.strip())
    return 0
