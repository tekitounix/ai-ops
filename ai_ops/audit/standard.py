"""ADR drift audit (Phase 8-C, L4 standard drift).

ai-ops の docs/decisions/ (ADR) が改訂された時、各 project の AGENTS.md / brief は
古い ADR 番号を参照したまま放置される。本 module は git log で「last sync 以降の ADR
差分」を抽出、target project に通知 / propose を出す。

設計:
- target project の `.ai-ops/harness.toml::ai_ops_sha` を `last_sync` の ref として使う。
- それが無い場合は --since flag で明示。default fallback は `HEAD~100`.
- ADR file (docs/decisions/*.md) の add / modify を git log -- で抽出、Markdown 要約を出力。
"""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path
from typing import Optional

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


def _git_log_adr_changes(ai_ops_root: Path, since_ref: str) -> str:
    """Return `git log --name-status` text for docs/decisions/ since the given ref.

    Empty string if the ref is unknown or no changes.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(ai_ops_root),
                "log",
                f"{since_ref}..HEAD",
                "--name-status",
                "--pretty=format:%n=== %h %s",
                "--",
                "docs/decisions/",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _git_resolve_ref(repo: Path, ref: str) -> bool:
    """Return True if `ref` resolves in `repo`."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", ref],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _read_last_sync_from_manifest(project_root: Path) -> Optional[str]:
    """Return ai_ops_sha from `.ai-ops/harness.toml`, or None."""
    manifest = project_root / ".ai-ops" / "harness.toml"
    if not manifest.is_file():
        return None
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return None
    sha = data.get("ai_ops_sha")
    return sha if sha else None


@dataclasses.dataclass
class StandardDrift:
    since_ref: str
    resolved_ref: bool  # ref が ai-ops repo で resolve するか
    log_text: str  # git log --name-status output
    new_adrs: list[str]  # 新しく add された ADR file
    modified_adrs: list[str]  # modify された ADR file


def detect_standard_drift(
    ai_ops_root: Path,
    project_root: Optional[Path] = None,
    since_ref: Optional[str] = None,
) -> StandardDrift:
    """Detect docs/decisions/ changes since the given ref.

    Resolution order for `since`:
      1. explicit --since flag (since_ref param)
      2. project's `.ai-ops/harness.toml::ai_ops_sha`
      3. `HEAD~100` fallback

    `project_root` is consulted only for (2). If neither (1) nor (2) is provided,
    we default to (3).
    """
    if since_ref is None and project_root is not None:
        since_ref = _read_last_sync_from_manifest(project_root)
    if since_ref is None:
        since_ref = "HEAD~100"

    resolved = _git_resolve_ref(ai_ops_root, since_ref)
    log_text = _git_log_adr_changes(ai_ops_root, since_ref) if resolved else ""

    new_adrs: list[str] = []
    modified_adrs: list[str] = []
    if log_text:
        for line in log_text.splitlines():
            line = line.strip()
            if not line or line.startswith("==="):
                continue
            # `git log --name-status` shows e.g.
            #   A\tdocs/decisions/0008-foo.md
            #   M\tdocs/decisions/0005-nix-...
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                continue
            status, path = parts
            if not path.startswith("docs/decisions/"):
                continue
            if status == "A":
                new_adrs.append(path)
            elif status in ("M", "MM"):
                modified_adrs.append(path)

    # de-duplicate while preserving order
    seen: set[str] = set()
    new_adrs = [p for p in new_adrs if not (p in seen or seen.add(p))]
    seen.clear()
    modified_adrs = [p for p in modified_adrs if not (p in seen or seen.add(p))]

    return StandardDrift(
        since_ref=since_ref,
        resolved_ref=resolved,
        log_text=log_text,
        new_adrs=new_adrs,
        modified_adrs=modified_adrs,
    )


def run_standard_audit(
    ai_ops_root: Path,
    project_root: Optional[Path] = None,
    since_ref: Optional[str] = None,
) -> int:
    """Print ADR drift report. Returns 0 if clean / 1 if changes detected."""
    drift = detect_standard_drift(
        ai_ops_root, project_root=project_root, since_ref=since_ref
    )
    print("==> Standard (ADR) drift audit (Phase 8-C, L4)")
    print(f"  since_ref: {drift.since_ref}")
    if not drift.resolved_ref:
        print(
            f"  WARN: ref `{drift.since_ref}` does not resolve in ai-ops repo. "
            f"Re-run with --since <commit-or-tag-known-to-ai-ops>."
        )
        return 1

    if not drift.new_adrs and not drift.modified_adrs:
        print("  OK: no ADR changes since the reference")
        return 0

    if drift.new_adrs:
        print(f"  WARN: {len(drift.new_adrs)} new ADR(s) since {drift.since_ref}:")
        for path in drift.new_adrs:
            print(f"    + {path}")
    if drift.modified_adrs:
        print(f"  WARN: {len(drift.modified_adrs)} modified ADR(s):")
        for path in drift.modified_adrs:
            print(f"    M {path}")
    print(
        "  next step: review the diff with `git -C <ai-ops> log "
        f"{drift.since_ref}..HEAD -- docs/decisions/`, "
        "then propagate relevant changes to project AGENTS.md / brief via the AI agent."
    )
    return 1
