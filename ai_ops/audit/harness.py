"""Harness drift detection (Phase 8-B, L3).

ai-ops の harness (AGENTS.md / flake.nix / brief 等) は AI agent が project-specific に
変形する artifact のため、cookiecutter / copier 流の決定論的 template モデルに収まらない。
本 module は cruft 流の "ファイル存在 + hash 比較" による drift detector を提供。

設計:
- target project に `.ai-ops/harness.toml` を残す (`ai_ops_sha`, `harness_files: {path: sha256}`,
  `last_sync`)
- `ai-ops audit harness <path>` で current state と manifest を比較、drift 検出
- 改善 propose は AI agent が `migrate --update-harness` で実施 (本 module は detector のみ)
"""

from __future__ import annotations

import dataclasses
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


HARNESS_MANIFEST = ".ai-ops/harness.toml"

# ai-ops 配布の harness file (target project に置かれるべき file)。
# Phase 8-B 初版: minimal set。AI agent は project-specific に追加 / 削除可。
DEFAULT_HARNESS_FILES: tuple[str, ...] = (
    "AGENTS.md",
    "CLAUDE.md",
    "flake.nix",
    ".envrc",
    "renovate.json",
)


VALID_WORKFLOW_TIERS: tuple[str, ...] = ("A", "B", "C", "D")


@dataclasses.dataclass
class HarnessManifest:
    ai_ops_sha: str
    harness_files: dict[str, str]  # relative path → sha256
    last_sync: str  # ISO 8601 UTC
    workflow_tier: str = "D"  # A/B/C/D per ADR 0009; missing → D (most permissive)

    def to_toml(self) -> str:
        lines = [
            f'ai_ops_sha = "{self.ai_ops_sha}"',
            f'last_sync = "{self.last_sync}"',
        ]
        # Only emit workflow_tier when not the default, to keep generated
        # manifests minimal for projects that haven't declared a tier.
        if self.workflow_tier != "D":
            lines.append(f'workflow_tier = "{self.workflow_tier}"')
        lines.extend(["", "[harness_files]"])
        for path in sorted(self.harness_files):
            lines.append(f'"{path}" = "{self.harness_files[path]}"')
        return "\n".join(lines) + "\n"

    @classmethod
    def from_toml(cls, text: str) -> "HarnessManifest":
        data = tomllib.loads(text)
        tier_raw = str(data.get("workflow_tier", "D")).strip().upper()
        # Defensive: an unknown tier value defaults back to D so audit
        # can still reason about the project. Validation surfaces via the
        # tier-violation detector, not via parser hard-fail.
        tier = tier_raw if tier_raw in VALID_WORKFLOW_TIERS else "D"
        return cls(
            ai_ops_sha=data.get("ai_ops_sha", ""),
            last_sync=data.get("last_sync", ""),
            harness_files=dict(data.get("harness_files", {})),
            workflow_tier=tier,
        )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _ai_ops_head_sha(ai_ops_root: Path) -> str:
    """Return current HEAD SHA of the ai-ops repository (for self-tracking)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(ai_ops_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_manifest(
    project_root: Path,
    ai_ops_root: Path,
    files: Iterable[str] = DEFAULT_HARNESS_FILES,
) -> HarnessManifest:
    """Build a HarnessManifest by hashing files that actually exist in project_root."""
    hashes: dict[str, str] = {}
    for rel in files:
        p = project_root / rel
        if p.is_file():
            hashes[rel] = _sha256(p)
    return HarnessManifest(
        ai_ops_sha=_ai_ops_head_sha(ai_ops_root),
        harness_files=hashes,
        last_sync=_now_iso(),
    )


@dataclasses.dataclass
class HarnessDrift:
    missing: list[str]  # manifest にあるが actual に無い
    extra: list[str]  # actual にあるが manifest に無い (= harness files set 内で想定外)
    modified: list[str]  # 両方ある hash 違い
    manifest_present: bool
    ai_ops_sha_drift: bool  # current ai-ops SHA != manifest's ai_ops_sha


def detect_drift(
    project_root: Path,
    ai_ops_root: Path,
    files: Iterable[str] = DEFAULT_HARNESS_FILES,
) -> HarnessDrift:
    """Compare actual file hashes vs `.ai-ops/harness.toml` manifest."""
    manifest_path = project_root / HARNESS_MANIFEST
    if not manifest_path.is_file():
        # No manifest: every present harness file is "extra" (= un-tracked harness).
        present = [
            rel for rel in files if (project_root / rel).is_file()
        ]
        return HarnessDrift(
            missing=[],
            extra=present,
            modified=[],
            manifest_present=False,
            ai_ops_sha_drift=False,
        )

    try:
        manifest = HarnessManifest.from_toml(
            manifest_path.read_text(encoding="utf-8")
        )
    except Exception:
        return HarnessDrift(
            missing=[],
            extra=[],
            modified=[],
            manifest_present=True,
            ai_ops_sha_drift=False,
        )

    actual: dict[str, str] = {}
    for rel in files:
        p = project_root / rel
        if p.is_file():
            actual[rel] = _sha256(p)

    manifest_keys = set(manifest.harness_files)
    actual_keys = set(actual)

    missing = sorted(manifest_keys - actual_keys)
    extra = sorted(actual_keys - manifest_keys)
    modified = sorted(
        rel
        for rel in (manifest_keys & actual_keys)
        if manifest.harness_files[rel] != actual[rel]
    )

    current_sha = _ai_ops_head_sha(ai_ops_root)
    sha_drift = bool(
        current_sha
        and manifest.ai_ops_sha
        and current_sha != manifest.ai_ops_sha
    )

    return HarnessDrift(
        missing=missing,
        extra=extra,
        modified=modified,
        manifest_present=True,
        ai_ops_sha_drift=sha_drift,
    )


def run_harness_audit(
    project_root: Path,
    ai_ops_root: Path,
    *,
    strict: bool = False,
) -> int:
    """Print drift report.

    Returns:
      - 0 when the harness is in sync with its manifest, or when no manifest
        exists and the project hasn't adopted ai-ops harness files yet.
      - 0 when no manifest exists but harness files are present, *unless*
        `strict=True`. The default is "non-blocking visibility": cross-project
        runs over many projects show adoption status without failing every
        repo that hasn't seeded a manifest yet.
      - 1 when manifest exists and drift is detected, or when
        `strict=True` and a manifest is missing despite harness files being
        present.
    """
    drift = detect_drift(project_root, ai_ops_root)
    print(f"==> Harness drift audit (Phase 8-B, L3)")
    print(f"  project: {project_root}")
    if not drift.manifest_present:
        if drift.extra:
            severity = "FAIL" if strict else "WARN"
            note = "" if strict else " (non-blocking; pass --strict to fail)"
            print(
                f"  {severity}: no .ai-ops/harness.toml; "
                f"{len(drift.extra)} untracked harness file(s) present"
                f"{note}"
            )
            print(
                f"    seed with: ai-ops migrate {project_root} --update-harness"
            )
            for rel in drift.extra:
                print(f"    untracked: {rel}")
            return 1 if strict else 0
        print("  OK: no manifest, no harness files; project pre-adoption")
        return 0

    has_drift = bool(
        drift.missing
        or drift.extra
        or drift.modified
        or drift.ai_ops_sha_drift
    )
    if not has_drift:
        print("  OK: harness in sync with manifest")
        return 0

    if drift.ai_ops_sha_drift:
        print(
            "  WARN: ai-ops SHA in manifest differs from current HEAD "
            "(consider re-running `migrate --update-harness`)"
        )
    if drift.missing:
        print(f"  FAIL: {len(drift.missing)} file(s) missing vs manifest:")
        for rel in drift.missing:
            print(f"    missing: {rel}")
    if drift.modified:
        print(f"  WARN: {len(drift.modified)} file(s) modified vs manifest hash:")
        for rel in drift.modified:
            print(f"    modified: {rel}")
    if drift.extra:
        print(f"  WARN: {len(drift.extra)} file(s) present but not in manifest:")
        for rel in drift.extra:
            print(f"    extra: {rel}")
    return 1
