from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


REQUIRED_FILES = (
    "README.md",
    "AGENTS.md",
    "docs/ai-first-lifecycle.md",
    "docs/fleet-audit.md",
    "docs/project-addition-and-migration.md",
    "docs/project-relocation.md",
    "docs/realignment.md",
    "docs/self-operation.md",
    "docs/decisions/0007-python-canonical-cli.md",
    "docs/decisions/0008-plan-persistence.md",
    "templates/project-brief.md",
    "templates/migration-brief.md",
    "templates/agent-handoff.md",
    "templates/plan.md",
    "templates/artifacts/flake.nix.minimal",
    "templates/artifacts/flake.nix.node",
    "templates/artifacts/flake.nix.python",
    "templates/artifacts/flake.nix.xmake",
    "templates/artifacts/.envrc",
    "templates/artifacts/renovate.json",
    "templates/artifacts/update-flake-lock.yml",
    "pyproject.toml",
    "setup.py",
    ".github/workflows/ci.yml",
    "ai_ops/cli.py",
    "ai_ops/lifecycle/project.py",
    "ai_ops/lifecycle/migration.py",
    "ai_ops/lifecycle/plans.py",
    "ai_ops/audit/fleet.py",
    "ai_ops/bootstrap.py",
)

CLASSIFICATION_TERMS = ("Fact", "Inference", "Risk", "User decision", "AI recommendation")

# Phase 8-D: subcommand & flag claims that README must be honest about.
# Each entry is the argv (without "ai-ops" prefix) we expect to succeed with --help.
# Drift signal: README mentions a subcommand the CLI doesn't actually expose.
README_CLAIMED_SUBCOMMANDS: tuple[tuple[str, ...], ...] = (
    ("new", "--help"),
    ("migrate", "--help"),
    ("bootstrap", "--help"),
    ("update", "--help"),
    ("audit", "--help"),
    ("check", "--help"),
    ("promote-plan", "--help"),
)

PLAN_STALE_DAYS = 30

# Phase 8-D: forbidden patterns from ADR 0002 / 0003 / 0007 etc.
# Detected anywhere in active source; presence = honest-claim drift.
# Each entry: (description, regex, scan paths relative to root).
FORBIDDEN_ACTIVE_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "git --no-verify (silently bypasses hooks; ADR 0003 violation)",
        r"--no-verify",
        ("ai_ops",),
    ),
    (
        "rm -rf without explicit guard (ADR 0003 deletion policy)",
        r"\brm\s+-rf\b",
        ("ai_ops",),
    ),
    (
        "gh repo create --public without confirmation gate (ADR 0002 visibility)",
        r"gh\s+repo\s+create[^|;\n]*--public",
        ("ai_ops",),
    ),
    (
        "silent install without confirmation (ADR 0002 amendment 2026-04-29)",
        r"#\s*silent[\s_-]*install",
        ("ai_ops",),
    ),
)


def _scan_pattern_in_paths(root: Path, pattern: str, scan_paths: tuple[str, ...]) -> list[str]:
    """Return list of `path:line` matches for the regex within scan_paths.

    The audit module itself (`ai_ops/audit/lifecycle.py`) is excluded because it
    documents the forbidden patterns as regex strings; matching them against
    those declarations would self-flag.
    """
    regex = re.compile(pattern)
    matches: list[str] = []
    for rel in scan_paths:
        target = root / rel
        if not target.exists():
            continue
        files = [target] if target.is_file() else target.rglob("*.py")
        for path in files:
            # Self-flag avoidance: this module declares the regex strings.
            if path.relative_to(root) == Path("ai_ops") / "audit" / "lifecycle.py":
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(lines, 1):
                if regex.search(line):
                    matches.append(f"{path.relative_to(root)}:{i}")
    return matches


def _check_readme_claims(root: Path) -> list[str]:
    """Verify each subcommand README claims actually responds to --help. Returns failure list."""
    failures: list[str] = []
    cli_path = root / "ai_ops" / "cli.py"
    if not cli_path.is_file():
        return failures  # nothing to check
    # Force UTF-8 in both directions so Windows runners (cp1252 / cp932 by
    # default) don't blow up when argparse renders help text that happens
    # to contain non-ASCII characters in any subparser, now or later.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for argv in README_CLAIMED_SUBCOMMANDS:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "ai_ops", *argv],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=10,
                cwd=str(root),
                env=env,
            )
        except Exception as exc:
            failures.append(f"{' '.join(argv)}: subprocess failed ({exc})")
            continue
        if result.returncode != 0:
            failures.append(
                f"`ai-ops {' '.join(argv)}` exited {result.returncode} "
                f"(README claims this subcommand exists)"
            )
    return failures


def _check_scorecard(root: Path) -> tuple[bool, str]:
    """Optional OpenSSF Scorecard check.

    Returns (ran, message). `ran=False` if scorecard CLI is unavailable;
    absence is informational because Scorecard is an optional local probe.
    """
    if not shutil.which("scorecard"):
        return False, "scorecard CLI not installed (skip; install via `brew install scorecard` to enable)"
    try:
        # Local-repo mode is enough for ai-ops's self-audit purpose.
        result = subprocess.run(
            ["scorecard", "--local", str(root), "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except Exception as exc:
        return False, f"scorecard invocation failed: {exc}"
    if result.returncode != 0:
        return True, f"scorecard exited {result.returncode}: {result.stderr.strip()[:200]}"
    return True, "scorecard ran (see JSON in stdout if needed)"


def _plan_age(plan: Path, root: Path, now: datetime) -> timedelta:
    """Age of `plan` from git's last-commit time, falling back to mtime.

    Filesystem mtime is reset on `git clone`, so a plan that is genuinely
    stale in the repo's history can look "fresh" right after a CI checkout.
    Prefer `git log -1 --format=%ct` and only fall back to mtime when git
    has no entry for the file (untracked, or non-git working tree).
    """
    try:
        rel = plan.relative_to(root)
        result = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%ct", "--", str(rel)],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            commit_time = datetime.fromtimestamp(int(result.stdout.strip()), tz=timezone.utc)
            return now - commit_time
    except (subprocess.SubprocessError, ValueError, OSError):
        pass
    mtime = datetime.fromtimestamp(plan.stat().st_mtime, tz=timezone.utc)
    return now - mtime


def _check_plan_hygiene(root: Path, now: datetime | None = None) -> list[str]:
    """Return non-fatal warnings for active execution plans."""
    plan_root = root / "docs" / "plans"
    if not plan_root.is_dir():
        return []

    warnings: list[str] = []
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    # `glob("*/plan.md")` is one-level-deep: the documented archive layout
    # `archive/YYYY-MM-DD-<slug>/plan.md` lives two levels down and is naturally
    # excluded. The explicit guard below only catches a misplaced
    # `docs/plans/archive/plan.md` and projects literally slugged "archive".
    for plan in sorted(plan_root.glob("*/plan.md")):
        if plan.parent.name == "archive":
            continue
        rel = plan.relative_to(root)
        try:
            text = plan.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            warnings.append(f"{rel} unreadable ({exc})")
            continue

        if not _has_progress_checkbox(text):
            warnings.append(f"{rel} missing Progress checkbox")

        if _plan_age(plan, root, now_utc) > timedelta(days=PLAN_STALE_DAYS):
            warnings.append(f"{rel} active for >{PLAN_STALE_DAYS} days without update")
    return warnings


def _has_progress_checkbox(text: str) -> bool:
    match = re.search(r"(?ms)^## Progress\s*(.*?)(?=^## |\Z)", text)
    if not match:
        return False
    return bool(re.search(r"(?m)^\s*-\s*\[[ xX]\]", match.group(1)))


def run_lifecycle_audit(root: Path) -> int:
    fail = 0
    passed = 0
    warn = 0
    print("==> ai-ops lifecycle audit")
    for rel in REQUIRED_FILES:
        if (root / rel).is_file():
            print(f"  OK: {rel} exists")
            passed += 1
        else:
            print(f"  FAIL: {rel} missing")
            fail += 1

    classification_files = (
        "templates/project-brief.md",
        "templates/migration-brief.md",
        "docs/ai-first-lifecycle.md",
    )
    if all((root / rel).is_file() for rel in classification_files):
        classification_fail_before = fail
        for rel in classification_files:
            text = (root / rel).read_text(encoding="utf-8")
            for term in CLASSIFICATION_TERMS:
                if term not in text:
                    print(f"  FAIL: {rel} missing classification term: {term}")
                    fail += 1
        if fail == classification_fail_before:
            print("  OK: brief classification terms present")
            passed += 1

    active_docs = (
        "README.md",
        "AGENTS.md",
        "docs/ai-first-lifecycle.md",
        "docs/project-addition-and-migration.md",
    )
    stale_markers = (
        "migration in progress",
        "移行中",
        "Phase 3.5",
        "Phase 4 READY",
        "review-template-2026-04-22-extended",
        "remaining-review",
        "migration/status.md",
        "--execute-approved",
        "scripts/ai-ops.sh",
        "scripts/ai-ops.ps1",
        "scripts/ai-ops.cmd",
        "ai-ops CLI を取得・更新",
    )
    for rel in active_docs:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in stale_markers:
            if marker in text:
                print(f"  FAIL: {rel} contains stale marker: {marker}")
                fail += 1

    forbidden_paths = (
        "START-HERE.md",
        "QUICK-REFERENCE.md",
        "archive",
        "migration",
        "plans",
        "scripts",
        "recipes",
        "hooks",
        "docs/reference",
        "docs/research",
        "docs/project-ledger.md",
    )
    for rel in forbidden_paths:
        if (root / rel).exists():
            print(f"  FAIL: {rel} should not be in the active tree")
            fail += 1

    allowed_template_files = {
        root / "templates" / "project-brief.md",
        root / "templates" / "migration-brief.md",
        root / "templates" / "agent-handoff.md",
        root / "templates" / "plan.md",
        root / "templates" / "artifacts" / "flake.nix.minimal",
        root / "templates" / "artifacts" / "flake.nix.node",
        root / "templates" / "artifacts" / "flake.nix.python",
        root / "templates" / "artifacts" / "flake.nix.xmake",
        root / "templates" / "artifacts" / ".envrc",
        root / "templates" / "artifacts" / "renovate.json",
        root / "templates" / "artifacts" / "update-flake-lock.yml",
    }
    template_root = root / "templates"
    if template_root.exists():
        for path in template_root.rglob("*"):
            if path.is_file() and path not in allowed_template_files:
                print(f"  FAIL: unexpected template file: {path.relative_to(root)}")
                fail += 1

    # Phase 8-D: README claim verification (= "documented subcommands actually exist")
    claim_failures = _check_readme_claims(root)
    if claim_failures:
        for msg in claim_failures:
            print(f"  FAIL: README claim drift — {msg}")
            fail += 1
    else:
        print("  OK: README-claimed subcommands respond to --help")
        passed += 1

    # Phase 9: active execution plans are allowed, but stale or malformed plans
    # should be visible without deleting useful archeology.
    plan_warnings = _check_plan_hygiene(root)
    if plan_warnings:
        for msg in plan_warnings:
            print(f"  WARN: plan hygiene — {msg}")
            warn += 1
    else:
        print("  OK: active execution plans are absent or healthy")
        passed += 1

    # Phase 8-D: ADR forbidden-pattern grep
    for desc, pattern, scan_paths in FORBIDDEN_ACTIVE_PATTERNS:
        hits = _scan_pattern_in_paths(root, pattern, scan_paths)
        if hits:
            print(f"  FAIL: forbidden pattern present — {desc}")
            for h in hits:
                print(f"    at {h}")
            fail += 1
        else:
            passed += 1
    if not any(
        _scan_pattern_in_paths(root, pat, paths)
        for _, pat, paths in FORBIDDEN_ACTIVE_PATTERNS
    ):
        print(f"  OK: no forbidden ADR patterns ({len(FORBIDDEN_ACTIVE_PATTERNS)} checks)")

    # Phase 8-D: optional OpenSSF Scorecard probe
    ran, msg = _check_scorecard(root)
    if ran:
        print(f"  INFO: {msg}")
    else:
        print(f"  INFO: {msg}")

    print("==> Summary")
    print(f"  PASS: {passed}")
    print(f"  WARN: {warn}")
    print(f"  FAIL: {fail}")
    return 1 if fail else 0
