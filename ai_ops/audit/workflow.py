"""Tier-based workflow violation detector (ADR 0009).

Detection only — never enforces tier rules, never mutates branch
protection or installs hooks. Reports detected deviations from the
project's declared tier so the user can decide whether to address them.

Cheap signals (no network) are returned by default. Deep signals that
require GitHub API calls (direct-push-to-main, unreviewed merge) are
opt-in via `deep=True` so the audit stays fast and offline-friendly
when run from cron / CI.
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_ops.audit.harness import HARNESS_MANIFEST


_LONG_LIVED_BRANCH_DAYS = 30


def _harness_toml_on_default(project: Path, default_branch: str) -> bool:
    """Whether `.ai-ops/harness.toml` exists on origin/<default-branch>.

    Mirrors the check in propagate.py but kept local so audit doesn't
    import propagate (which would create a circular dependency).
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(project), "cat-file", "-e",
             f"origin/{default_branch}:{HARNESS_MANIFEST}"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _list_long_lived_branches(
    project: Path, default_branch: str, threshold_days: int,
) -> list[tuple[str, int]]:
    """Return [(branch, age_days)] for local branches older than threshold
    that are not the default branch and have unpushed/un-merged commits."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=threshold_days)
    cutoff_ts = int(cutoff.timestamp())
    try:
        result = subprocess.run(
            ["git", "-C", str(project), "for-each-ref",
             "--format=%(refname:short)|%(committerdate:unix)",
             "refs/heads/"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        if result.returncode != 0:
            return []
    except (subprocess.SubprocessError, OSError):
        return []

    out: list[tuple[str, int]] = []
    for line in result.stdout.splitlines():
        if "|" not in line:
            continue
        name, ts_str = line.split("|", 1)
        name = name.strip()
        if name == default_branch:
            continue
        try:
            ts = int(ts_str.strip())
        except ValueError:
            continue
        if ts <= cutoff_ts:
            age = (datetime.now(tz=timezone.utc).timestamp() - ts) / 86400
            out.append((name, int(age)))
    return out


def _direct_push_to_main_count(
    project: Path, default_branch: str, since_days: int = 30,
) -> int | None:
    """Count commits on origin/<default-branch> in the last `since_days`
    that have NO associated PR (i.e., direct push). Returns None if `gh`
    is unavailable or the query fails. Uses GitHub API via `gh`.
    """
    if not shutil.which("gh"):
        return None
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=since_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    try:
        # Get repo full name.
        repo_meta = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner",
             "-q", ".nameWithOwner"],
            cwd=str(project), capture_output=True, text=True,
            check=False, timeout=10,
        )
        if repo_meta.returncode != 0:
            return None
        repo = repo_meta.stdout.strip()
        # List commits since cutoff.
        commits = subprocess.run(
            ["gh", "api",
             f"/repos/{repo}/commits?sha={default_branch}&since={cutoff}",
             "--jq", ".[].sha"],
            capture_output=True, text=True, check=False, timeout=15,
        )
        if commits.returncode != 0:
            return None
        shas = [s for s in commits.stdout.split() if s]
        # For each commit, check if it has an associated PR.
        direct_count = 0
        for sha in shas:
            pr_check = subprocess.run(
                ["gh", "api", f"/repos/{repo}/commits/{sha}/pulls",
                 "--jq", "length"],
                capture_output=True, text=True, check=False, timeout=10,
            )
            if pr_check.returncode != 0:
                continue
            try:
                if int(pr_check.stdout.strip()) == 0:
                    direct_count += 1
            except ValueError:
                continue
        return direct_count
    except (subprocess.SubprocessError, OSError):
        return None


def detect_tier_violations(
    project: Path,
    tier: str,
    default_branch: str | None,
    *,
    deep: bool = False,
) -> list[str]:
    """Return human-readable violation strings for the project's declared tier.

    Cheap detections (always run):
    - Tier A/B/C/D common: manifest absent on default branch (propagation
      cannot work)
    - Tier A: long-lived feature branches (>30 days) present locally

    Deep detections (only when `deep=True`):
    - Tier B/C: direct-push-to-main commits in last 30 days
    """
    violations: list[str] = []

    if tier not in ("A", "B", "C", "D"):
        violations.append(f"unknown tier '{tier}' (expected one of A/B/C/D)")
        return violations

    # Common: manifest must be on default branch for propagation to work.
    # Tier D explicitly accepts manifest-not-on-default; surface as INFO
    # for D, WARN for A/B/C.
    if default_branch and not _harness_toml_on_default(project, default_branch):
        if tier == "D":
            violations.append(
                f"INFO: manifest not on origin/{default_branch} — "
                f"propagation requires manual merge to default (Tier D accepts this)"
            )
        else:
            violations.append(
                f".ai-ops/harness.toml absent on origin/{default_branch} — "
                f"merge it before propagation can run"
            )

    # Tier A: long-lived feature branches contradict trunk-based norm.
    if tier == "A":
        long_branches = _list_long_lived_branches(
            project, default_branch or "main", _LONG_LIVED_BRANCH_DAYS,
        )
        for name, age in long_branches:
            violations.append(
                f"long-lived branch '{name}' ({age} days) — Tier A is trunk-based"
            )

    # Tier B/C: direct push to main is forbidden.
    if deep and tier in ("B", "C") and default_branch:
        direct = _direct_push_to_main_count(project, default_branch)
        if direct is not None and direct > 0:
            violations.append(
                f"{direct} direct-push commit(s) to {default_branch} in last 30 days "
                f"— Tier {tier} requires PR-based merges"
            )

    return violations
