"""Fleet audit: walk every ghq-tracked project, collect drift signals,
prioritize, and recommend a sub-flow per project.

The CLI provides deterministic collection + table assembly so AI agents
(via the `audit my fleet` Quick start prompt) and scheduled jobs
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

from ai_ops.audit.harness import HARNESS_MANIFEST, detect_drift
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

# `find`-style skip: directories that hold dependencies / build artifacts;
# their content is third-party / generated and not part of the project's
# own secret hygiene.
SKIP_DIR_PARTS = frozenset({
    ".git", ".direnv", ".pytest_cache", "__pycache__", ".tox", ".eggs",
    ".venv", "venv",
    "node_modules",
    "vendor", "target", "dist", "build", ".cache", ".next", ".gradle",
    "result", "bazel-out",
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
class FleetSignals:
    """Signals collected for a single project during fleet audit Phase 1."""

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
    priority: str  # "P0" | "P1" | "P2"
    sub_flow: str  # "relocate" | "migrate" | "realign" | "no-op"


def _is_secret_name(name: str) -> bool:
    """`.env.example` etc. are templates, not secrets."""
    if name.startswith(".env."):
        suffix = name[len(".env."):].lower()
        if suffix in ENV_TEMPLATE_SUFFIXES:
            return False
    return any(p.search(name) for p in SECRET_NAME_PATTERNS)


def _count_secret_files(path: Path) -> int:
    n = 0
    try:
        for entry in path.rglob("*"):
            try:
                rel = entry.relative_to(path)
            except ValueError:
                continue
            if any(part in SKIP_DIR_PARTS for part in rel.parts):
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

    Returns 0 if rg is not installed (fleet audit must not depend on rg
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


def collect_signals(path: Path) -> FleetSignals:
    """Read-only signal collection for one project. Never writes."""
    loc = "ok" if _under_ghq_root(path) else "DRIFT"
    mgd = "yes" if (path / HARNESS_MANIFEST).is_file() else "no"
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

    harness_drift = False
    if mgd == "yes":
        try:
            ai_ops_root = Path(__file__).resolve().parents[2]
            drift = detect_drift(path, ai_ops_root)
            harness_drift = bool(
                drift.missing
                or drift.modified
                or drift.extra
                or drift.ai_ops_sha_drift
            )
        except Exception:
            harness_drift = False

    # Priority assignment
    if loc != "ok" or sec >= 1:
        priority = "P0"
    elif (
        (nix == "missing" and has_stack)
        or (mgd == "yes" and harness_drift)
        or (
            age_days is not None
            and age_days > STALE_COMMIT_DAYS
            and not docs_only
        )
    ):
        priority = "P1"
    else:
        priority = "P2"

    # Sub-flow recommendation
    if loc != "ok":
        sub_flow = "relocate"
    elif mgd == "no" and (has_stack or not docs_only):
        sub_flow = "migrate"
    elif mgd == "yes" and (
        (nix == "missing" and has_stack) or harness_drift
    ):
        sub_flow = "realign"
    else:
        sub_flow = "no-op"

    return FleetSignals(
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
        priority=priority,
        sub_flow=sub_flow,
    )


# ─────────────────────────────────────────────────────
# Output formatting
# ─────────────────────────────────────────────────────


def signals_to_dict(s: FleetSignals) -> dict:
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
        "priority": s.priority,
        "sub_flow": s.sub_flow,
    }


def _shorten_path(path: Path, width: int = 50) -> str:
    home = str(Path.home())
    s = str(path)
    if s.startswith(home):
        s = "~" + s[len(home):]
    if len(s) > width:
        s = s[: width - 3] + "..."
    return s


def _print_table(signals_list: list[FleetSignals]) -> None:
    cols = (
        ("project", 24),
        ("path", 50),
        ("loc", 5),
        ("mgd", 3),
        ("nix", 7),
        ("sec", 3),
        ("dirty", 5),
        ("last", 14),
        ("todo", 4),
        ("pri", 3),
        ("sub-flow", 9),
    )
    header = " ".join(f"{name:<{w}}" for name, w in cols)
    print(header)
    print("-" * len(header))
    for s in signals_list:
        proj = (s.project[:21] + "...") if len(s.project) > 24 else s.project
        path_short = _shorten_path(s.path)
        last = (
            s.last_commit_human[:11] + "..."
            if len(s.last_commit_human) > 14
            else s.last_commit_human
        )
        row = (
            f"{proj:<24} "
            f"{path_short:<50} "
            f"{s.loc:<5} "
            f"{s.mgd:<3} "
            f"{s.nix:<7} "
            f"{s.sec:>3} "
            f"{s.dirty:>5} "
            f"{last:<14} "
            f"{s.todo:>4} "
            f"{s.priority:<3} "
            f"{s.sub_flow:<9}"
        )
        print(row)


# ─────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────


_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def run_fleet_audit(
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

    signals_list: list[FleetSignals] = []
    for p in paths:
        try:
            signals_list.append(collect_signals(p))
        except Exception as exc:
            # One bad project must not abort a fleet survey.
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
            f"==> Fleet audit: {len(signals_list)} project(s) "
            f"(managed={n_managed}, P0={n_p0}, P1={n_p1}, P2={n_p2})\n"
        )
        _print_table(signals_list)
        print(
            "\nRoute each P0 / P1 to its sub-flow with per-project confirmation "
            "(relocate / migrate / realign). See docs/fleet-audit.md."
        )

    has_action = any(s.priority in ("P0", "P1") for s in signals_list)
    return 1 if has_action else 0
