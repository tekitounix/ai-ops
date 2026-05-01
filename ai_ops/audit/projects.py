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
    harness_drift: bool  # mgd=yes and detect_drift reports any drift
    policy_drift: str  # "ok" | "stale" | "diverged" | "ahead-and-behind" | "no-anchor" | "n/a"
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


def collect_signals(path: Path) -> ProjectSignals:
    """Read-only signal collection for one project. Never writes."""
    loc = "ok" if _under_ghq_root(path) else "DRIFT"
    if (path / HARNESS_MANIFEST).is_file():
        mgd = "yes"
    elif _is_ai_ops_repo(path):
        # ai-ops itself is the methodology source — it does not seed a
        # harness manifest because it *is* the harness.
        mgd = "src"
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

    # Priority assignment
    if loc != "ok" or sec >= 1:
        priority = "P0"
    elif (
        (mgd == "no" and nix == "missing" and has_stack)
        or (mgd == "yes" and harness_drift)
        or policy_drift in ("stale", "diverged", "ahead-and-behind", "no-anchor")
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
        or harness_drift
        or policy_drift in ("stale", "diverged", "ahead-and-behind", "no-anchor")
    ):
        sub_flow = "realign"
    elif mgd == "no" and (has_stack or not docs_only):
        sub_flow = "migrate"
    else:
        sub_flow = "no-op"

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
        policy_drift=policy_drift,
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
        "policy_drift": s.policy_drift,
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
