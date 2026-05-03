"""Projects audit: walk every ghq-tracked project, collect drift signals,
prioritize, and recommend a sub-flow per project.

The CLI provides deterministic collection + table assembly so AI agents
(via the `audit my projects` Quick start prompt) and scheduled jobs
(cron / CI) see identical priority assignments. The CLI itself is
read-only; remediation is per-project under user confirmation through
the linked sub-flow playbooks (relocate / migrate / realign).
"""
from __future__ import annotations

import dataclasses
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ai_ops.audit._canonical import REQUIRED_PLAN_SECTIONS
from ai_ops.audit.harness import HARNESS_MANIFEST, HarnessManifest, detect_drift
from ai_ops.audit.nix import _ghq_list_paths


# ─────────────────────────────────────────────────────
# Signal collection
# ─────────────────────────────────────────────────────

SECRET_NAME_PATTERNS = (
    re.compile(r"^\.env(\..*)?$"),
    re.compile(r"\.(key|pem|p12|pfx)$"),
    re.compile(r"^id_(rsa|dsa|ecdsa|ed25519)$"),
)
ENV_TEMPLATE_SUFFIXES = frozenset({
    "example", "template", "sample", "dist", "default", "tmpl",
})

# `find`-style skip: directories that hold dependencies / build artifacts /
# vendored third-party trees; their content is not part of the project's
# own secret hygiene. A first real-world projects audit on a project with
# STM32 + mbedTLS vendored under `third_party/` produced 193 false-positive
# secret-name hits (TLS test fixtures), all from vendored content.
SKIP_DIR_PARTS = frozenset({
    # VCS / direnv / cache
    ".git", ".direnv", ".pytest_cache", "__pycache__", ".tox", ".eggs",
    # Python virtual envs
    ".venv", "venv",
    # Node
    "node_modules",
    # Build / dependency / vendor trees
    "vendor", "target", "dist", "build", ".cache", ".next", ".gradle",
    "result", "bazel-out",
    # Vendored third-party (Google / Chromium / firmware SDK conventions)
    "third_party", "third-party", "external", "deps", "subprojects",
})

# Stack signals — used to decide whether `nix=missing` is a P1 trigger.
# Mirrors ai_ops.audit.nix._STACK_RULES but flat-lists the file markers
# so we can probe via `git ls-files`.
STACK_MARKERS = frozenset({
    "package.json", "pnpm-lock.yaml", "bun.lockb",
    "pyproject.toml", "uv.lock", "requirements.txt", "Pipfile",
    "Cargo.toml",
    "go.mod",
    "xmake.lua", "CMakeLists.txt",
})

DOCS_ONLY_SUFFIXES = frozenset({".md", ".pdf", ".txt", ".rst", ".png", ".jpg", ".jpeg", ".gif", ".svg"})

# An archive-suspect commit is older than 18 months on a repo that still
# carries source / config (i.e. not docs-only).
STALE_COMMIT_DAYS = 540


@dataclasses.dataclass
class ProjectSignals:
    """Signals collected for a single project during projects audit Phase 1."""

    project: str
    path: Path
    loc: str  # "ok" | "DRIFT"
    mgd: str  # "yes" | "no"
    nix: str  # "present" | "missing" | "n/a"
    sec: int  # secret-name file count
    dirty: int  # uncommitted state lines (porcelain)
    last_commit_age_days: int | None  # None if no commits
    last_commit_human: str  # "1 day ago", "no commits", etc.
    todo: int  # TODO/FIXME/WIP/TBD count in text sources
    agents_md: bool  # AGENTS.md present at root
    has_stack: bool  # any stack marker present
    is_docs_only: bool  # ≥ 85% of tracked files are doc / image suffixes
    harness_drift: bool  # mgd=yes and detect_drift reports any drift (LOCAL working copy)
    remote_anchor_synced: bool | None  # True iff origin/<default>'s harness.toml records ai_ops_sha == current ai-ops HEAD; None if unknown (offline, no remote, fetch failed)
    policy_drift: str  # "ok" | "stale" | "diverged" | "ahead-and-behind" | "no-anchor" | "n/a"
    pending_propagation_prs: int  # open PRs from `ai-ops/*` branches; -1 if `gh` unavailable
    workflow_tier: str  # "A" | "B" | "C" | "D" (per ADR 0009; missing harness.toml → "D")
    tier_violations: list[str]  # human-readable violations from declared tier; empty if clean
    recommended_tier: str | None  # P2 observational suggestion (PR γ); None if not applicable
    has_ai_ops_workflow: bool  # `.github/workflows/ai-ops.yml` exists (ADR 0011)
    has_codeowners_routing: bool  # `.github/CODEOWNERS` references `.ai-ops/` (ADR 0011)
    priority: str  # "P0" | "P1" | "P2"
    sub_flow: str  # "relocate" | "migrate" | "realign" | "no-op"


def _is_secret_name(name: str) -> bool:
    """`.env.example` etc. are templates, not secrets."""
    if name.startswith(".env."):
        suffix = name[len(".env."):].lower()
        if suffix in ENV_TEMPLATE_SUFFIXES:
            return False
    return any(p.search(name) for p in SECRET_NAME_PATTERNS)


def _git_submodule_paths(path: Path) -> set[tuple[str, ...]]:
    """Return submodule paths (relative to the project root) as tuples
    of components, suitable for prefix-matching `Path.relative_to`.

    Submodules are owned by their upstream repo; the consuming project is
    not responsible for their secret hygiene or harness state.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "submodule", "status", "--recursive"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        if result.returncode != 0:
            return set()
        paths: set[tuple[str, ...]] = set()
        for line in result.stdout.splitlines():
            # Format: " <sha> <path> (<branch>)" or "+<sha> <path> ..." etc.
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            sub_rel = parts[1]
            paths.add(tuple(sub_rel.split("/")))
        return paths
    except (subprocess.SubprocessError, OSError):
        return set()


def _count_secret_files(path: Path) -> int:
    submodule_prefixes = _git_submodule_paths(path)
    n = 0
    try:
        for entry in path.rglob("*"):
            try:
                rel = entry.relative_to(path)
            except ValueError:
                continue
            parts = rel.parts
            if any(p in SKIP_DIR_PARTS for p in parts):
                continue
            # Skip git submodules (their secret hygiene is upstream's responsibility).
            if any(parts[: len(prefix)] == prefix for prefix in submodule_prefixes):
                continue
            if not entry.is_file():
                continue
            if _is_secret_name(entry.name):
                n += 1
    except (OSError, RuntimeError):
        pass
    return n


def _git_log_recency(path: Path) -> tuple[int | None, str]:
    """Return (age_days, human_str). age_days is None if there are no commits."""
    try:
        ts_result = subprocess.run(
            ["git", "-C", str(path), "log", "-1", "--format=%ct"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        if ts_result.returncode != 0 or not ts_result.stdout.strip():
            return None, "no commits"
        ts = int(ts_result.stdout.strip())
        commit_time = datetime.fromtimestamp(ts, tz=timezone.utc)
        age_days = (datetime.now(tz=timezone.utc) - commit_time).days
        human_result = subprocess.run(
            ["git", "-C", str(path), "log", "-1", "--format=%ar"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        human = human_result.stdout.strip() or f"{age_days} days ago"
        return age_days, human
    except (subprocess.SubprocessError, ValueError, OSError):
        return None, "no commits"


def _git_dirty_count(path: Path) -> int:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        return len([line for line in result.stdout.splitlines() if line.strip()])
    except (subprocess.SubprocessError, OSError):
        return 0


def _git_ls_files(path: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "ls-files"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        return [line for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.SubprocessError, OSError):
        return []


def _todo_count(path: Path) -> int:
    """Count TODO/FIXME/WIP/TBD across text sources via ripgrep.

    Returns 0 if rg is not installed (projects audit must not depend on rg
    being present; the count is a P2-only signal so degrading to 0 is fine).
    """
    if not shutil.which("rg"):
        return 0
    try:
        result = subprocess.run(
            [
                "rg", "-c",
                "-t", "md", "-t", "py", "-t", "js", "-t", "ts",
                "-t", "rs", "-t", "go",
                "--hidden",
                "-g", "!.git", "-g", "!node_modules", "-g", "!.venv",
                "-g", "!vendor", "-g", "!dist", "-g", "!build",
                "-e", r"\bTODO\b|\bFIXME\b|\bWIP\b|\bTBD\b",
                str(path),
            ],
            capture_output=True, text=True, check=False, timeout=10,
        )
        total = 0
        for line in result.stdout.splitlines():
            try:
                total += int(line.rsplit(":", 1)[1])
            except (IndexError, ValueError):
                continue
        return total
    except (subprocess.SubprocessError, OSError):
        return 0


def _is_docs_only(tracked: list[str]) -> bool:
    if not tracked:
        return False
    n_docs = sum(
        1 for f in tracked
        if Path(f).suffix.lower() in DOCS_ONLY_SUFFIXES
    )
    return n_docs / len(tracked) > 0.85


def _has_stack_markers(tracked: list[str]) -> bool:
    """A stack marker counts only when it's at the project root (top-level).

    A vendored fixture under tests/ does not count as the project owning that
    stack — same convention used by `audit nix`.
    """
    top_names = {f.split("/", 1)[0] for f in tracked}
    return any(m in top_names for m in STACK_MARKERS)


def _under_ghq_root(path: Path) -> bool:
    """True iff `path` is anywhere under `~/ghq/`. Path-based comparison so
    POSIX `/` and Windows `\\` separators both work."""
    ghq_root = Path.home() / "ghq"
    try:
        path.resolve().relative_to(ghq_root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _count_pending_propagation_prs(path: Path) -> int:
    """Count open PRs whose head branch starts with `ai-ops/`.

    Returns -1 when `gh` is unavailable or the call fails — distinguishing
    "no gh" from "0 PRs" so the table can show `-` vs `0` accurately.
    Skip pattern is non-fatal so audit projects works offline.
    """
    if not shutil.which("gh"):
        return -1
    try:
        result = subprocess.run(
            ["gh", "pr", "list",
             "--state", "open",
             "--search", "head:ai-ops/",
             "--json", "number"],
            cwd=str(path),
            capture_output=True, text=True, check=False, timeout=10,
        )
        if result.returncode != 0:
            return -1
        out = result.stdout.strip()
        if out in ("", "[]"):
            return 0
        # Quick count by counting `"number":` occurrences instead of parsing.
        return out.count('"number"')
    except (subprocess.SubprocessError, OSError):
        return -1


def _remote_anchor_synced(
    project: Path,
    ai_ops_root: Path,
) -> bool | None:
    """True iff origin/<default-branch>'s `.ai-ops/harness.toml` carries
    `ai_ops_sha == current ai-ops HEAD`.

    Returns None when the answer can't be determined (`gh` missing, no
    GitHub remote, fetch failure, no manifest on default branch). The
    audit then degrades gracefully — local `harness_drift` still drives
    severity in that case.

    Resolves the "audit shows drift even though propagation PR was just
    merged" UX gap: after the merge, remote default branch has the right
    anchor but the user's local working copy hasn't been pulled. Without
    this signal the audit table would keep flagging propagation work
    that's already done.
    """
    if not shutil.which("gh"):
        return None
    # Get default branch via gh.
    try:
        gh = subprocess.run(
            ["gh", "repo", "view", "--json", "defaultBranchRef",
             "-q", ".defaultBranchRef.name"],
            cwd=str(project), capture_output=True, text=True,
            check=False, timeout=10,
        )
        if gh.returncode != 0:
            return None
        default_branch = gh.stdout.strip()
        if not default_branch:
            return None
    except (subprocess.SubprocessError, OSError):
        return None

    # Fetch default branch (cheap if up to date).
    try:
        fetch = subprocess.run(
            ["git", "-C", str(project), "fetch", "origin", default_branch],
            capture_output=True, text=True, check=False, timeout=15,
        )
        if fetch.returncode != 0:
            return None
    except (subprocess.SubprocessError, OSError):
        return None

    # Read remote manifest content.
    try:
        cat = subprocess.run(
            ["git", "-C", str(project), "cat-file", "-p",
             f"origin/{default_branch}:{HARNESS_MANIFEST}"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        if cat.returncode != 0:
            return None
        try:
            from ai_ops.audit.harness import HarnessManifest
            remote_manifest = HarnessManifest.from_toml(cat.stdout)
        except Exception:
            return None
    except (subprocess.SubprocessError, OSError):
        return None

    head_sha = _ai_ops_head_sha_local(ai_ops_root)
    if not head_sha:
        return None
    return remote_manifest.ai_ops_sha == head_sha


def _ai_ops_head_sha_local(ai_ops_root: Path) -> str:
    """Return ai-ops repo's current HEAD sha. Inline to avoid circular import."""
    try:
        result = subprocess.run(
            ["git", "-C", str(ai_ops_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _is_ai_ops_repo(path: Path) -> bool:
    """ai-ops itself is the source-of-truth repo for the methodology, not a
    consumer that seeds `.ai-ops/harness.toml`. Detect by structural shape
    (AGENTS.md + ai_ops/ Python package + docs/decisions ADR set) so the
    projects audit doesn't recommend `migrate` against ai-ops itself."""
    return (
        (path / "AGENTS.md").is_file()
        and (path / "ai_ops" / "cli.py").is_file()
        and (path / "docs" / "decisions").is_dir()
    )


def _plan_top_level_headings(text: str) -> set[str]:
    """Return the set of `^## <title>` headings stripped of trailing whitespace."""
    return {m.group(1).strip() for m in re.finditer(r"(?m)^##\s+(.+?)\s*$", text)}


def _detect_policy_drift(project_path: Path, ai_ops_root: Path) -> str:
    """Compare project's plan-related files against ai-ops canonical schema.

    Returns one of:
    - "n/a"            — unmanaged project, ai-ops itself, or no plans/templates to check
    - "no-anchor"      — managed project but `harness.toml.ai_ops_sha` missing/empty
    - "ok"             — schemas match
    - "stale"          — project lacks canonical headings (canonical is ahead)
    - "diverged"       — project has non-canonical headings (project is ahead)
    - "ahead-and-behind" — both directions of drift present

    Detection is set-based on top-level (`^## `) headings only. Heading order
    is allowed to differ. Section content is not inspected (deferred to v2).
    AGENTS.md is intentionally not checked — managed projects' AGENTS.md is
    project-specific, not a canonical copy.
    """
    if not (project_path / HARNESS_MANIFEST).is_file():
        return "n/a"
    if _is_ai_ops_repo(project_path):
        return "n/a"

    try:
        manifest_text = (project_path / HARNESS_MANIFEST).read_text(encoding="utf-8")
        manifest = HarnessManifest.from_toml(manifest_text)
    except Exception:
        return "no-anchor"
    if not manifest.ai_ops_sha:
        return "no-anchor"

    canonical_sections = frozenset(REQUIRED_PLAN_SECTIONS)
    ahead = False  # project has headings canonical lacks
    behind = False  # project lacks headings canonical has

    own_template = project_path / "templates" / "plan.md"
    if own_template.is_file():
        try:
            own_set = _plan_top_level_headings(own_template.read_text(encoding="utf-8"))
            if canonical_sections - own_set:
                behind = True
            if own_set - canonical_sections:
                ahead = True
        except (UnicodeDecodeError, OSError):
            pass

    plans_dir = project_path / "docs" / "plans"
    if plans_dir.is_dir():
        # Active plans only — `*/plan.md` is one level deep; archived plans
        # live two levels deep under `archive/<date-slug>/plan.md`.
        for plan in plans_dir.glob("*/plan.md"):
            if plan.parent.name == "archive":
                continue
            try:
                text = plan.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            plan_set = _plan_top_level_headings(text)
            # An active plan only needs canonical sections present (set
            # membership). Extra project-specific sections are allowed and
            # do not flip `ahead` (per-plan customization is normal).
            if canonical_sections - plan_set:
                behind = True

    if ahead and behind:
        return "ahead-and-behind"
    if behind:
        return "stale"
    if ahead:
        return "diverged"
    return "ok"


def _recommend_tier(
    mgd: str,
    workflow_tier: str,
    visibility: str | None,
    contributors: int | None,
    age_days: int | None,
) -> str | None:
    """Suggest a workflow_tier when the project might benefit from re-declaring.

    Conservative ruleset (P2 observational, never priority-bumping):
    - Only managed projects (`mgd == "yes"`) and only when `workflow_tier == "D"`
      (default; explicit D declarations also surface a suggestion since we can't
      tell them apart cheaply, but the suggestion costs nothing to ignore).
    - public visibility → "C" (production / public reviews recommended)
    - private + contributors > 1 → "B" (managed PR-based)
    - private + age > 365d → "D" (already spike-like; no change suggested)
    - private + solo + active → "A" (trunk-based solo)
    Returns None when no signal is reliable.
    """
    if mgd != "yes":
        return None
    if workflow_tier != "D":
        return None
    if visibility == "public":
        return "C"
    if age_days is not None and age_days > 365:
        return None  # already D-like; no actionable suggestion
    if (contributors or 1) > 1:
        return "B"
    return "A"


def _gh_repo_visibility_and_contributors(path: Path) -> tuple[str | None, int | None]:
    """Return (visibility, distinct contributor count) via `gh`. None on any failure."""
    if not shutil.which("gh"):
        return None, None
    try:
        result = subprocess.run(
            ["gh", "repo", "view",
             "--json", "visibility,assignableUsers",
             "-q", '{visibility: .visibility, contributors: (.assignableUsers | length)}'],
            cwd=str(path), capture_output=True, text=True,
            check=False, timeout=8,
        )
    except (subprocess.SubprocessError, OSError):
        return None, None
    if result.returncode != 0:
        return None, None
    import json as _json
    try:
        data = _json.loads(result.stdout)
    except _json.JSONDecodeError:
        return None, None
    visibility = data.get("visibility")
    if isinstance(visibility, str):
        visibility = visibility.lower()
    return visibility, data.get("contributors")


def collect_signals(path: Path) -> ProjectSignals:
    """Read-only signal collection for one project. Never writes."""
    loc = "ok" if _under_ghq_root(path) else "DRIFT"
    # ai-ops takes precedence: even when it has its own `.ai-ops/harness.
    # toml` (introduced for ADR 0009 tier declaration), it remains `src`
    # — the methodology source, not a `propagate-*` target.
    if _is_ai_ops_repo(path):
        mgd = "src"
    elif (path / HARNESS_MANIFEST).is_file():
        mgd = "yes"
    else:
        mgd = "no"
    flake_present = (path / "flake.nix").is_file()

    tracked = _git_ls_files(path)
    has_stack = _has_stack_markers(tracked)
    docs_only = _is_docs_only(tracked)

    if docs_only:
        nix = "n/a"
    elif flake_present:
        nix = "present"
    else:
        nix = "missing"

    sec = _count_secret_files(path)
    age_days, last_human = _git_log_recency(path)
    dirty = _git_dirty_count(path)
    todo = _todo_count(path)
    agents_md = (path / "AGENTS.md").is_file()

    ai_ops_root = Path(__file__).resolve().parents[2]
    harness_drift = False
    if mgd == "yes":
        try:
            drift = detect_drift(path, ai_ops_root)
            harness_drift = bool(
                drift.missing
                or drift.modified
                or drift.extra
                or drift.ai_ops_sha_drift
            )
        except Exception:
            harness_drift = False

    policy_drift = _detect_policy_drift(path, ai_ops_root)

    # Workflow tier: parsed from `.ai-ops/harness.toml` if present;
    # default to "D" otherwise (most permissive, ADR 0009).
    workflow_tier = "D"
    if (path / HARNESS_MANIFEST).is_file():
        try:
            from ai_ops.audit.harness import HarnessManifest
            mfst = HarnessManifest.from_toml(
                (path / HARNESS_MANIFEST).read_text(encoding="utf-8")
            )
            workflow_tier = mfst.workflow_tier
        except Exception:
            workflow_tier = "D"

    # Pending propagation PRs (ai-ops/* branches). Cheap to query and only
    # for managed projects to keep the audit fast for large ghq trees.
    if mgd == "yes":
        pending_prs = _count_pending_propagation_prs(path)
        remote_synced = _remote_anchor_synced(path, ai_ops_root)
    else:
        pending_prs = 0
        remote_synced = None

    # Tier violations: cheap detections only (network deep checks are
    # opt-in via a future flag; not surfaced from the default audit run).
    tier_violations: list[str] = []
    if mgd in ("yes", "src"):
        try:
            from ai_ops.audit.workflow import detect_tier_violations
            # Default branch lookup is cheap when gh is available; pass
            # None when not so the detector uses a sensible fallback.
            default_branch_for_tier: str | None = None
            try:
                gh_meta = subprocess.run(
                    ["gh", "repo", "view", "--json", "defaultBranchRef",
                     "-q", ".defaultBranchRef.name"],
                    cwd=str(path), capture_output=True, text=True,
                    check=False, timeout=5,
                )
                if gh_meta.returncode == 0:
                    default_branch_for_tier = gh_meta.stdout.strip() or None
            except (subprocess.SubprocessError, OSError):
                pass
            tier_violations = detect_tier_violations(
                path, workflow_tier, default_branch_for_tier, deep=False,
            )
        except Exception:
            tier_violations = []

    # GitHub-native artifact presence (ADR 0011). Cheap file checks; no
    # network calls. Surface via JSON / table so user sees which managed
    # projects have which artifacts deployed.
    has_ai_ops_workflow = (path / ".github" / "workflows" / "ai-ops.yml").is_file()
    has_codeowners_routing = False
    co_path = path / ".github" / "CODEOWNERS"
    if co_path.is_file():
        try:
            has_codeowners_routing = ".ai-ops" in co_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            has_codeowners_routing = False

    # Priority assignment.
    # `harness_drift` reflects local working-copy state. After a propagate-*
    # PR is merged, local can still appear drifted until the user pulls —
    # but propagation work for that project is genuinely done. When remote
    # is known to be in sync (`remote_anchor_synced is True`), local
    # harness_drift alone should not escalate priority. When remote state is
    # unknown (None), fall back to treating local drift as P1 worthy.
    propagation_needed = harness_drift and remote_synced is not True
    # Tier violations that aren't INFO-only escalate to P1. INFO entries
    # (Tier D's "manifest not on default" notice) are surfaced but not
    # priority-bumped because the user explicitly accepted that state.
    tier_actionable = any(
        not v.startswith("INFO:") for v in tier_violations
    )
    if loc != "ok" or sec >= 1:
        priority = "P0"
    elif (
        (mgd == "no" and nix == "missing" and has_stack)
        or (mgd == "yes" and propagation_needed)
        or policy_drift in ("stale", "diverged", "ahead-and-behind", "no-anchor")
        or tier_actionable
        or (
            age_days is not None
            and age_days > STALE_COMMIT_DAYS
            and not docs_only
        )
    ):
        priority = "P1"
    else:
        priority = "P2"

    # Sub-flow recommendation.
    #
    # Intent: P2 means "no action needed this cycle". Recommending a
    # destructive sub-flow (migrate / realign) for a P2 row would
    # contradict the priority — especially for validation / fixture repos
    # under ~/ghq/local/... that are intentionally unmanaged. ai-ops
    # itself (mgd=src) is never the target of a sub-flow regardless of
    # priority — it's the methodology source, not a consumer.
    #
    # `sec >= 1` is a P0 trigger but the previous logic returned no-op
    # for it because the no-op fall-through caught managed projects with
    # no other drift signal. Route secret-name P0 explicitly: realign for
    # managed projects (the realign playbook covers `.env` review), or
    # migrate for unmanaged ones (migration sets up the harness in the
    # first place, so secret hygiene is part of that flow).
    if mgd == "src":
        sub_flow = "no-op"
    elif loc != "ok":
        sub_flow = "relocate"
    elif sec >= 1:
        sub_flow = "realign" if mgd == "yes" else "migrate"
    elif priority == "P2":
        sub_flow = "no-op"
    elif mgd == "yes" and (
        (nix == "missing" and has_stack)
        or propagation_needed
        or policy_drift in ("stale", "diverged", "ahead-and-behind", "no-anchor")
    ):
        sub_flow = "realign"
    elif mgd == "no" and (has_stack or not docs_only):
        sub_flow = "migrate"
    else:
        sub_flow = "no-op"

    # Tier 推薦 (PR γ): managed プロジェクトで未宣言 (default D) なら gh から
    # signal を取って P2 観察的に推薦。失敗時は None。
    if mgd == "yes":
        visibility, contributors = _gh_repo_visibility_and_contributors(path)
    else:
        visibility, contributors = None, None
    recommended_tier = _recommend_tier(
        mgd=mgd,
        workflow_tier=workflow_tier,
        visibility=visibility,
        contributors=contributors,
        age_days=age_days,
    )

    return ProjectSignals(
        project=path.name,
        path=path,
        loc=loc,
        mgd=mgd,
        nix=nix,
        sec=sec,
        dirty=dirty,
        last_commit_age_days=age_days,
        last_commit_human=last_human,
        todo=todo,
        agents_md=agents_md,
        has_stack=has_stack,
        is_docs_only=docs_only,
        harness_drift=harness_drift,
        remote_anchor_synced=remote_synced,
        policy_drift=policy_drift,
        pending_propagation_prs=pending_prs,
        workflow_tier=workflow_tier,
        tier_violations=tier_violations,
        recommended_tier=recommended_tier,
        has_ai_ops_workflow=has_ai_ops_workflow,
        has_codeowners_routing=has_codeowners_routing,
        priority=priority,
        sub_flow=sub_flow,
    )


# ─────────────────────────────────────────────────────
# Output formatting
# ─────────────────────────────────────────────────────


def signals_to_dict(s: ProjectSignals) -> dict:
    return {
        "project": s.project,
        "path": str(s.path),
        "loc": s.loc,
        "mgd": s.mgd,
        "nix": s.nix,
        "sec": s.sec,
        "dirty": s.dirty,
        "last_commit_age_days": s.last_commit_age_days,
        "last_commit_human": s.last_commit_human,
        "todo": s.todo,
        "agents_md": s.agents_md,
        "has_stack": s.has_stack,
        "is_docs_only": s.is_docs_only,
        "harness_drift": s.harness_drift,
        "remote_anchor_synced": s.remote_anchor_synced,
        "policy_drift": s.policy_drift,
        "pending_propagation_prs": s.pending_propagation_prs,
        "workflow_tier": s.workflow_tier,
        "tier_violations": list(s.tier_violations),
        "recommended_tier": s.recommended_tier,
        "has_ai_ops_workflow": s.has_ai_ops_workflow,
        "has_codeowners_routing": s.has_codeowners_routing,
        "priority": s.priority,
        "sub_flow": s.sub_flow,
    }


_POLICY_DRIFT_SHORT = {
    "ok": "ok",
    "stale": "stl",
    "diverged": "div",
    "ahead-and-behind": "a&b",
    "no-anchor": "noa",
    "n/a": "n/a",
}


def _shorten_path(path: Path, width: int = 50) -> str:
    home = str(Path.home())
    s = str(path)
    if s.startswith(home):
        s = "~" + s[len(home):]
    if len(s) > width:
        s = s[: width - 3] + "..."
    return s


def _print_table(signals_list: list[ProjectSignals]) -> None:
    cols = (
        ("project", 28),
        ("path", 52),
        ("loc", 5),
        ("mgd", 4),
        ("nix", 7),
        ("sec", 3),
        ("dirty", 5),
        ("last", 14),
        ("todo", 4),
        ("pdr", 3),
        ("prs", 3),
        ("rsy", 3),
        ("tier", 4),
        ("tv", 3),
        ("pri", 3),
        ("sub-flow", 9),
    )
    header = " ".join(f"{name:<{w}}" for name, w in cols)
    print(header)
    print("-" * len(header))
    for s in signals_list:
        proj = (s.project[:25] + "...") if len(s.project) > 28 else s.project
        path_short = _shorten_path(s.path, width=52)
        last = (
            s.last_commit_human[:11] + "..."
            if len(s.last_commit_human) > 14
            else s.last_commit_human
        )
        pdr = _POLICY_DRIFT_SHORT.get(s.policy_drift, s.policy_drift[:3])
        prs = "-" if s.pending_propagation_prs < 0 else str(s.pending_propagation_prs)
        if s.remote_anchor_synced is True:
            rsy = "yes"
        elif s.remote_anchor_synced is False:
            rsy = "no"
        else:
            rsy = "-"
        tier = s.workflow_tier or "D"
        tv = str(len(s.tier_violations))
        row = (
            f"{proj:<28} "
            f"{path_short:<52} "
            f"{s.loc:<5} "
            f"{s.mgd:<4} "
            f"{s.nix:<7} "
            f"{s.sec:>3} "
            f"{s.dirty:>5} "
            f"{last:<14} "
            f"{s.todo:>4} "
            f"{pdr:<3} "
            f"{prs:>3} "
            f"{rsy:<3} "
            f"{tier:<4} "
            f"{tv:>3} "
            f"{s.priority:<3} "
            f"{s.sub_flow:<9}"
        )
        print(row)


# ─────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────


_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def run_projects_audit(
    roots: list[Path] | None = None,
    *,
    json_output: bool = False,
    priority_filter: str = "all",
) -> int:
    """Walk ghq-tracked projects, score each, emit table or JSON.

    Returns 1 if any P0 or P1 finding remains in the (filtered) output, 0
    otherwise — usable from cron / CI as a drift alert.
    """
    paths = roots if roots is not None else _ghq_list_paths()
    if not paths:
        print("No projects found via ghq list -p", file=sys.stderr)
        return 1

    signals_list: list[ProjectSignals] = []
    for p in paths:
        try:
            signals_list.append(collect_signals(p))
        except Exception as exc:
            # One bad project must not abort the audit run.
            print(
                f"  ERROR: {p}: {type(exc).__name__}: {str(exc)[:80]}",
                file=sys.stderr,
            )

    signals_list.sort(key=lambda s: (_PRIORITY_ORDER[s.priority], str(s.path)))

    if priority_filter != "all":
        signals_list = [s for s in signals_list if s.priority == priority_filter]

    if json_output:
        print(json.dumps([signals_to_dict(s) for s in signals_list], indent=2))
    else:
        n_p0 = sum(1 for s in signals_list if s.priority == "P0")
        n_p1 = sum(1 for s in signals_list if s.priority == "P1")
        n_p2 = sum(1 for s in signals_list if s.priority == "P2")
        n_managed = sum(1 for s in signals_list if s.mgd == "yes")
        print(
            f"==> Projects audit: {len(signals_list)} project(s) "
            f"(managed={n_managed}, P0={n_p0}, P1={n_p1}, P2={n_p2})\n"
        )
        _print_table(signals_list)
        print(
            "\nRoute each P0 / P1 to its sub-flow with per-project confirmation "
            "(relocate / migrate / realign). See docs/projects-audit.md."
        )

    has_action = any(s.priority in ("P0", "P1") for s in signals_list)
    return 1 if has_action else 0
