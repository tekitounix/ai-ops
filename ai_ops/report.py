"""Sub-issue lifecycle management for the Ecosystem dashboard (ADR 0011).

`ai-ops report-drift` is invoked by `.github/workflows/ecosystem-watch.yml`
to translate `audit projects --json` output into Issue / sub-issue state
in the ai-ops repo. The flow:

    audit projects → drift list → per-project parent issue → sub-issues
                                                              per category

Sub-issue API is GraphQL-only; REST has no equivalent at writing.
Operations:
- Find parent issue by label `ecosystem` + project name in title
- Open new sub-issue when a drift category appears
- Update body on subsequent runs (state changes)
- Close sub-issue when drift signal disappears

Cheap design: parent issues are NOT auto-created here (manual setup
per project). Sub-issues only fire when their parent exists; missing
parents are surfaced as a warning.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ECOSYSTEM_LABEL = "ecosystem"
DRIFT_LABEL = "ai-ops:drift"


@dataclass
class DriftCategory:
    """A specific drift kind detected for a project."""

    project: str  # ghq project name (matches parent issue title)
    category: str  # e.g. "harness-drift", "policy-stale", "tier-violation"
    severity: str  # "P0" | "P1" | "P2"
    summary: str  # one-line human description
    details: str  # multi-line markdown body


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _gh(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True,
        check=False, timeout=30, **kwargs,
    )


def _find_parent_issue(repo: str, project: str) -> int | None:
    """Find the open parent issue for a project (label `ecosystem` and
    title containing the project name). Returns issue number or None."""
    result = _gh([
        "issue", "list",
        "--repo", repo,
        "--label", ECOSYSTEM_LABEL,
        "--state", "open",
        "--search", f"in:title {project}",
        "--json", "number,title",
    ])
    if result.returncode != 0:
        return None
    try:
        items = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return None
    for item in items:
        if project in item.get("title", ""):
            return int(item["number"])
    return None


def _find_drift_subissue(repo: str, project: str, category: str) -> int | None:
    """Find an open sub-issue for a specific (project, category)."""
    title_marker = f"[{project}] {category}"
    result = _gh([
        "issue", "list",
        "--repo", repo,
        "--label", DRIFT_LABEL,
        "--state", "open",
        "--search", f"in:title \"{title_marker}\"",
        "--json", "number,title",
    ])
    if result.returncode != 0:
        return None
    try:
        items = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return None
    for item in items:
        if title_marker in item.get("title", ""):
            return int(item["number"])
    return None


def _create_sub_issue_via_graphql(
    repo: str, parent_number: int, title: str, body: str,
) -> int | None:
    """Create an issue and link it as a sub-issue of `parent_number`.

    Uses GitHub GraphQL since REST does not yet expose sub-issue link.
    Returns the new issue number, or None on failure.
    """
    # Step 1: get parent's node ID.
    parent_q = _gh([
        "api", "graphql",
        "-f", f"query=query{{repository(owner:\"{repo.split('/')[0]}\","
              f"name:\"{repo.split('/')[1]}\"){{issue(number:{parent_number}){{id}}}}}}",
    ])
    if parent_q.returncode != 0:
        return None
    try:
        parent_id = json.loads(parent_q.stdout)["data"]["repository"]["issue"]["id"]
    except (KeyError, json.JSONDecodeError):
        return None

    # Step 2: create the new issue via REST (gh issue create).
    create = _gh([
        "issue", "create",
        "--repo", repo,
        "--title", title,
        "--body", body,
        "--label", DRIFT_LABEL,
    ])
    if create.returncode != 0:
        return None
    # gh issue create prints URL on success; extract number.
    url = create.stdout.strip().splitlines()[-1] if create.stdout.strip() else ""
    try:
        new_number = int(url.rsplit("/", 1)[-1])
    except (ValueError, IndexError):
        return None

    # Step 3: get new issue's node ID and link as sub-issue.
    new_q = _gh([
        "api", "graphql",
        "-f", f"query=query{{repository(owner:\"{repo.split('/')[0]}\","
              f"name:\"{repo.split('/')[1]}\"){{issue(number:{new_number}){{id}}}}}}",
    ])
    if new_q.returncode != 0:
        return new_number  # fallback: issue exists but unlinked
    try:
        new_id = json.loads(new_q.stdout)["data"]["repository"]["issue"]["id"]
    except (KeyError, json.JSONDecodeError):
        return new_number

    # addSubIssue mutation. Note: this is a GA feature as of 2026 GA wave.
    mutation = (
        f"mutation{{addSubIssue(input:{{issueId:\"{parent_id}\","
        f"subIssueId:\"{new_id}\"}}){{subIssue{{number}}}}}}"
    )
    _gh(["api", "graphql", "-f", f"query={mutation}"])  # ignore errors
    return new_number


def _update_issue_body(repo: str, number: int, body: str) -> bool:
    result = _gh([
        "issue", "edit", str(number),
        "--repo", repo,
        "--body", body,
    ])
    return result.returncode == 0


def _close_issue(repo: str, number: int, reason: str = "drift resolved") -> bool:
    result = _gh([
        "issue", "close", str(number),
        "--repo", repo,
        "--comment", f"Auto-closed by ai-ops report-drift: {reason}",
    ])
    return result.returncode == 0


def _signals_to_drift_categories(signals: list[dict]) -> list[DriftCategory]:
    """Translate audit projects JSON entries into drift categories."""
    out: list[DriftCategory] = []
    for s in signals:
        proj = s["project"]
        if s.get("mgd") not in ("yes",):
            continue  # only managed projects feed the dashboard
        if s.get("policy_drift") in ("stale", "diverged", "ahead-and-behind", "no-anchor"):
            out.append(DriftCategory(
                project=proj, category="policy-drift", severity=s["priority"],
                summary=f"policy_drift={s['policy_drift']}",
                details=(
                    f"Project's plan/template schema is out of sync with the\n"
                    f"current ai-ops canonical (`policy_drift={s['policy_drift']}`).\n\n"
                    f"To resolve, run `ai-ops propagate-files --project {proj}` "
                    f"or sync via the next realignment session.\n"
                ),
            ))
        if s.get("harness_drift") and s.get("remote_anchor_synced") is not True:
            out.append(DriftCategory(
                project=proj, category="harness-drift", severity=s["priority"],
                summary="ai_ops_sha or harness file hashes drifted",
                details=(
                    f"Harness drift detected (`harness_drift=True`, "
                    f"`remote_anchor_synced={s.get('remote_anchor_synced')}`).\n\n"
                    f"To resolve, the next `propagate-anchor --project {proj}` "
                    f"or `propagate-files --project {proj}` PR should fix it.\n"
                ),
            ))
        if s.get("tier_violations"):
            non_info = [v for v in s["tier_violations"] if not v.startswith("INFO:")]
            if non_info:
                out.append(DriftCategory(
                    project=proj, category="tier-violation", severity=s["priority"],
                    summary=f"{len(non_info)} tier violation(s)",
                    details=(
                        f"Workflow tier violations detected for tier "
                        f"`{s.get('workflow_tier', 'D')}`:\n\n"
                        + "\n".join(f"- {v}" for v in non_info) + "\n"
                    ),
                ))
    return out


def run_report_drift(
    *,
    ai_ops_repo: str,
    audit_json_path: Path | None = None,
    dry_run: bool = False,
) -> int:
    """Translate audit projects output into sub-issue lifecycle ops.

    `ai_ops_repo` is the repo (e.g. "tekitounix/ai-ops") whose Issues
    receive the parent / sub-issue traffic.

    When `audit_json_path` is None, runs `ai-ops audit projects --json`
    inline. Otherwise reads the JSON from the path.
    """
    if not _gh_available():
        print("Error: gh CLI is required", file=sys.stderr)
        return 1

    if audit_json_path is not None:
        data = json.loads(audit_json_path.read_text(encoding="utf-8"))
    else:
        from ai_ops.audit.projects import run_projects_audit
        # We need the JSON output but can't easily capture the print here;
        # simplest is to invoke as subprocess.
        result = subprocess.run(
            [sys.executable, "-m", "ai_ops", "audit", "projects", "--json"],
            capture_output=True, text=True, check=False, timeout=120,
        )
        if result.returncode not in (0, 1):
            print(f"Error: audit projects failed: {result.stderr}", file=sys.stderr)
            return 1
        data = json.loads(result.stdout)

    drifts = _signals_to_drift_categories(data)
    print(f"Detected {len(drifts)} active drift category instances "
          f"across managed projects.")

    # Group by project so we can find parents once.
    by_project: dict[str, list[DriftCategory]] = {}
    for d in drifts:
        by_project.setdefault(d.project, []).append(d)

    fail = 0
    for proj, cats in by_project.items():
        parent = _find_parent_issue(ai_ops_repo, proj)
        if parent is None:
            print(
                f"  WARN: no parent issue found for project '{proj}' "
                f"(create one in {ai_ops_repo} with label `{ECOSYSTEM_LABEL}`)"
            )
            continue
        for cat in cats:
            existing = _find_drift_subissue(ai_ops_repo, proj, cat.category)
            title = f"[{proj}] {cat.category} — {cat.summary}"
            body = cat.details
            if dry_run:
                action = "update" if existing else "create"
                print(f"  [dry-run] {action} sub-issue: {title}")
                continue
            if existing is None:
                new_num = _create_sub_issue_via_graphql(
                    ai_ops_repo, parent, title, body,
                )
                if new_num is None:
                    print(f"  FAIL: could not create sub-issue for {proj}/{cat.category}")
                    fail += 1
                else:
                    print(f"  OK: created #{new_num} for {proj}/{cat.category}")
            else:
                if _update_issue_body(ai_ops_repo, existing, body):
                    print(f"  OK: updated #{existing} for {proj}/{cat.category}")
                else:
                    print(f"  FAIL: could not update #{existing}")
                    fail += 1

    # Close sub-issues whose drift category is no longer in the audit.
    active_keys = {(d.project, d.category) for d in drifts}
    # Find all open drift sub-issues and close those not in active_keys.
    list_all = _gh([
        "issue", "list",
        "--repo", ai_ops_repo,
        "--label", DRIFT_LABEL,
        "--state", "open",
        "--limit", "100",
        "--json", "number,title",
    ])
    if list_all.returncode == 0:
        try:
            opens = json.loads(list_all.stdout or "[]")
        except json.JSONDecodeError:
            opens = []
        for item in opens:
            title = item.get("title", "")
            # parse "[project] category — ..."
            if not title.startswith("["):
                continue
            try:
                proj_part, rest = title[1:].split("]", 1)
                category_part = rest.strip().split(" — ", 1)[0].strip()
            except (ValueError, IndexError):
                continue
            if (proj_part, category_part) in active_keys:
                continue
            if dry_run:
                print(f"  [dry-run] close #{item['number']}: drift resolved")
            else:
                if _close_issue(ai_ops_repo, item["number"]):
                    print(f"  OK: closed #{item['number']} (drift resolved)")
                else:
                    fail += 1

    return 1 if fail else 0
