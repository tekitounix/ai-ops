"""Nix adoption audit with per-project rubric (ADR 0005 amended 2026-04-29).

Stage A (hard gates) → Stage B (stack-aware default) → Stage C (score adjust)
で per-project の Nix fitness を判定。出力は JSON record (machine-parseable)。

3 modes:
  - run_nix_audit(root): cwd の flake.nix 妥当性 + rubric 評価。CI 用。
  - run_nix_report(roots): ghq list 全 walk、recommendation table。
  - run_nix_propose(path): 単一 project の retrofit Markdown 提案。
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable


# ─────────────────────────────────────────────────────
# Stage A — hard gates (early exit)
# ─────────────────────────────────────────────────────


@dataclasses.dataclass
class StageAExit:
    reason: str  # "archive" / "scratch" / "docs-only" / "existing-flake" / "vendor-locked" / "upstream-fork"
    recommended_level: str  # "none" / "preserve" / "amend" / "minimal"


_DOC_EXTS = {".md", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".svg", ".csv"}


def _git_log_one(path: Path, fmt: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "log", "-1", f"--format={fmt}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _git_remote_url(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _git_first_author(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "log", "--format=%ae", "--reverse"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        first_line = result.stdout.strip().splitlines()
        return first_line[0] if first_line else ""
    except Exception:
        return ""


def _last_commit_age_days(path: Path) -> int | None:
    iso = _git_log_one(path, "%aI")
    if not iso:
        return None
    try:
        ts = datetime.datetime.fromisoformat(iso)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        return (now - ts).days
    except Exception:
        return None


def _list_top_level(path: Path) -> list[str]:
    try:
        return sorted([p.name for p in path.iterdir()])
    except Exception:
        return []


def _is_docs_only(top_names: Iterable[str]) -> bool:
    names = [n for n in top_names if not n.startswith(".")]
    if not names:
        return False
    for name in names:
        ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        if ext not in _DOC_EXTS:
            return False
    return True


def _is_scratch(path: Path) -> bool:
    """~/scratch/ 配下 AND no remote AND tracked < 5 file → scratch.

    self-review #2 fix: 旧実装は path だけで判定していたが、~/scratch/ に Git remote 付き
    クローンを置くケースで誤判定する。3 条件 AND に修正。
    """
    home = Path.home()
    try:
        rel = path.resolve().relative_to(home)
    except ValueError:
        return False
    if not (rel.parts and rel.parts[0] in ("scratch", "tmp")):
        return False
    # remote 確認: 設定なしなら ephemeral 候補
    remote = _git_remote_url(path)
    if remote:
        return False
    # tracked file count
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "ls-files"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        tracked_count = len(result.stdout.strip().splitlines()) if result.stdout.strip() else 0
    except Exception:
        tracked_count = 0
    return tracked_count < 5


def _stage_a_exit(path: Path, top_names: list[str]) -> StageAExit | None:
    # archive: last commit > 18mo
    age = _last_commit_age_days(path)
    if age is not None and age > 540:
        return StageAExit(reason="archive", recommended_level="none")

    # existing flake — preserve / amend
    if (path / "flake.nix").is_file():
        return StageAExit(reason="existing-flake", recommended_level="preserve")

    # docs-only
    if _is_docs_only(top_names):
        return StageAExit(reason="docs-only", recommended_level="none")

    # scratch
    if _is_scratch(path):
        return StageAExit(reason="scratch", recommended_level="none")

    # upstream fork: remote owner が user の ghq.user と一致しない場合
    # self-review #3 fix: 旧実装は path 上の owner と remote owner を比較していたが、
    # path layout が ~/ghq/github.com/... 限定だったり、user の secondary account との
    # 区別ができないため、`git config --get ghq.user` を真の owner として比較する。
    remote = _git_remote_url(path)
    if remote:
        m = re.search(r"(?:github\.com|gitlab\.com|bitbucket\.org)[:/]([^/]+)/", remote)
        remote_owner = m.group(1) if m else ""
        try:
            user_result = subprocess.run(
                ["git", "config", "--get", "ghq.user"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            ghq_user = user_result.stdout.strip()
        except Exception:
            ghq_user = ""
        if remote_owner and ghq_user and remote_owner.lower() != ghq_user.lower():
            return StageAExit(reason="upstream-fork", recommended_level="none")

    return None


# ─────────────────────────────────────────────────────
# Stage B — stack-aware default
# ─────────────────────────────────────────────────────


_STACK_RULES: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    # (stack_hint, marker filenames, recommended_level, template_variant)
    # Note: rust / go / cmake は専用 template が無いため `flake.nix.minimal` (= 最少 tool) に
    # fallback する。AI agent が retrofit 時に project-specific tool (cargo / go / cmake) を
    # tools 配列に追加するのが正解。`flake.nix.python` を rust/go に流用すると uv/ruff/pytest が
    # 不要に混入するため誤り (self-review #1 finding)。
    ("xmake", ("xmake.lua",), "devshell", "flake.nix.xmake"),
    ("cmake", ("CMakeLists.txt",), "devshell", "flake.nix.minimal"),  # tools = cmake/ninja/clang を AI が追加
    ("node", ("package.json", "pnpm-lock.yaml", "bun.lockb"), "devshell", "flake.nix.node"),
    ("python", ("pyproject.toml", "uv.lock", "requirements.txt", "Pipfile"), "devshell", "flake.nix.python"),
    ("rust", ("Cargo.toml",), "devshell", "flake.nix.minimal"),  # tools = cargo/rustc を AI が追加
    ("go", ("go.mod",), "devshell", "flake.nix.minimal"),  # tools = go を AI が追加
    ("dsl", (".ato",), "devshell", "flake.nix.minimal"),  # extension match
)


def _stage_b(top_names: list[str]) -> tuple[str, str, str]:
    """Return (stack_hint, recommended_level, template_variant)."""
    # Case-insensitive marker matching: top_names を lowercase 化、_STACK_RULES の marker
    # も lowercase で比較する (CMakeLists.txt vs cmakelists.txt 等の差を吸収)。
    lower = [n.lower() for n in top_names]
    for hint, markers, level, template in _STACK_RULES:
        for marker in markers:
            marker_lower = marker.lower()
            if marker_lower.startswith("."):
                if any(name.endswith(marker_lower) for name in lower):
                    return hint, level, template
            elif marker_lower in lower:
                return hint, level, template
    return "unknown", "minimal", "flake.nix.minimal"


# ─────────────────────────────────────────────────────
# Stage C — score adjustment
# ─────────────────────────────────────────────────────


def _stage_c_score(path: Path, top_names: list[str]) -> tuple[int, list[str], list[str]]:
    """Return (score, pros_signals, cons_signals)."""
    pros: list[str] = []
    cons: list[str] = []
    score = 0

    # Pros
    if (path / ".github" / "workflows").is_dir():
        pros.append("ci_yaml")
        score += 2
    if any((path / d).is_dir() for d in ("tests", "test", "__tests__")):
        pros.append("tests")
        score += 1
    if (path / "LICENSE").is_file():
        pros.append("license")
        score += 1
    if (path / "CONTRIBUTING.md").is_file():
        pros.append("external_contrib")
        score += 2
    if any((path / d).is_dir() for d in ("dist", "out", "release", "build")):
        pros.append("release_artifact")
        score += 2
    if any((path / d).is_dir() for d in ("vendor", "third_party")):
        pros.append("vendor_binary")
        score += 3
    if (path / "AGENTS.md").is_file() or (path / "CLAUDE.md").is_file():
        pros.append("ai_session_active")
        score += 2
    age = _last_commit_age_days(path)
    if age is not None and age <= 90:
        pros.append("active")
        score += 1

    # Cons
    if age is not None and 270 < age <= 540:
        cons.append("stale_not_archive")
        score -= 1
    try:
        tracked = subprocess.run(
            ["git", "-C", str(path), "ls-files"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        tracked_count = len(tracked.stdout.strip().splitlines()) if tracked.stdout.strip() else 0
    except Exception:
        tracked_count = 0
    if tracked_count and tracked_count < 5:
        cons.append("tiny_project")
        score -= 2
    # Many top-level memo / PLAN files (stalled prototype signal)
    memo_count = sum(
        1
        for n in top_names
        if any(n.upper().startswith(p) for p in ("PLAN", "MEMO", "TODO", "REDESIGN", "NOTES"))
    )
    if memo_count > 3:
        cons.append("many_memo_files")
        score -= 1

    return score, pros, cons


# ─────────────────────────────────────────────────────
# Public API: evaluate_project
# ─────────────────────────────────────────────────────


def evaluate_project(path: Path) -> dict:
    """Run Stage A/B/C and return JSON-serializable rubric output."""
    if not path.is_dir():
        return {"path": str(path), "error": "not a directory"}

    top_names = _list_top_level(path)
    a = _stage_a_exit(path, top_names)
    if a:
        return {
            "path": str(path),
            "stage_a_exit": a.reason,
            "stack_hint": "n/a",
            "current_nix": "yes" if (path / "flake.nix").is_file() else "no",
            "recommended_level": a.recommended_level,
            "score": 0,
            "pros_signals": [],
            "cons_signals": [a.reason] if a.reason != "existing-flake" else [],
            "gap": "ok" if a.reason == "existing-flake" else "n/a",
            "confidence": "high",
        }

    stack_hint, level_b, template = _stage_b(top_names)
    score, pros, cons = _stage_c_score(path, top_names)

    # Stage C action mapping
    if score >= 6:
        if level_b == "devshell":
            level = "apps"
        else:
            level = level_b
    elif score >= 0:
        level = level_b
    else:
        level = "none"

    confidence = "high"
    if 0 <= score <= 1:
        confidence = "low"  # borderline

    current_nix = "yes" if (path / "flake.nix").is_file() else "no"
    gap = "ok" if current_nix == "yes" else "missing-flake"

    return {
        "path": str(path),
        "stage_a_exit": None,
        "stack_hint": stack_hint,
        "current_nix": current_nix,
        "recommended_level": level,
        "recommended_template": template,
        "score": score,
        "pros_signals": pros,
        "cons_signals": cons,
        "gap": gap,
        "confidence": confidence,
    }


# ─────────────────────────────────────────────────────
# Mode 1: cwd audit (run_nix_audit) — invoked by `ai-ops audit nix`
# ─────────────────────────────────────────────────────


def run_nix_audit(root: Path) -> int:
    print("==> Nix adoption audit (per-project rubric, ADR 0005 amended 2026-04-29)")
    record = evaluate_project(root)
    print(json.dumps(record, indent=2, ensure_ascii=False))

    # CI gate logic:
    # - existing-flake: validate it (loose) — must reference Python CLI for ai-ops self
    # - missing flake when level >= devshell + no opt-out justification: FAIL
    # - none-recommended: PASS (Stage A or score < 0)
    fail = 0
    if record.get("stage_a_exit") == "existing-flake":
        flake = root / "flake.nix"
        text = flake.read_text(encoding="utf-8")
        if root.name == "ai-ops":
            if "ai_ops" in text and "python" in text:
                print("  OK: ai-ops flake.nix references Python CLI")
            else:
                print("  FAIL: ai-ops flake.nix should wrap Python CLI")
                fail += 1
        else:
            # other projects: loose check (devShells / mkShell present)
            if "devShells" in text or "mkShell" in text:
                print("  OK: flake.nix has devShells / mkShell (loose match)")
            else:
                print("  WARN: flake.nix lacks recognizable devShells / mkShell")
        lock = root / "flake.lock"
        if lock.is_file():
            print("  OK: flake.lock exists")
        else:
            print("  WARN: flake.lock missing")
        return 1 if fail else 0

    if record.get("recommended_level") in ("devshell", "apps", "full") and record.get("gap") == "missing-flake":
        print(f"  FAIL: recommended_level={record['recommended_level']} but flake.nix is missing")
        return 1

    print(f"  OK: recommendation = {record.get('recommended_level')}")
    return 0


# ─────────────────────────────────────────────────────
# Mode 2: --report (run_nix_report) — multi-project survey
# ─────────────────────────────────────────────────────


def _ghq_list_paths() -> list[Path]:
    try:
        result = subprocess.run(
            ["ghq", "list", "-p"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return [Path(line) for line in result.stdout.strip().splitlines() if line]
    except Exception:
        return []


def run_nix_report(roots: list[Path] | None = None) -> int:
    """Walk ghq list -p (or provided roots), emit recommendation table.

    The `mgd` column shows whether the project has been onboarded to ai-ops
    harness tracking (`.ai-ops/harness.toml` present). A fleet survey can
    then separate ai-ops-managed projects from validation fixtures /
    untouched repos at a glance.
    """
    paths = roots or _ghq_list_paths()
    if not paths:
        print("No projects found via ghq list -p")
        return 1

    print("==> Nix fleet survey (rubric, ADR 0005)")
    print(f"  {len(paths)} project(s)\n")
    print(
        f"{'project':<50} {'mgd':<4} {'stack':<10} {'cur':<5} "
        f"{'rec':<10} {'score':>5} {'gap':<15} {'conf':<6}"
    )
    print("-" * 115)

    n_ok = 0
    n_missing = 0
    n_borderline = 0
    n_error = 0
    n_managed = 0

    for p in paths:
        name = p.name
        if len(name) > 48:
            name = "…" + name[-47:]
        managed = (p / ".ai-ops" / "harness.toml").is_file()
        if managed:
            n_managed += 1
        mgd_label = "yes" if managed else "no"
        try:
            r = evaluate_project(p)
        except Exception as exc:
            # One bad project (corrupted .git, symlink loop, permission denied)
            # must not abort a fleet survey. Emit an error row and move on.
            print(f"{name:<50} {mgd_label:<4} ERROR: {type(exc).__name__}: {str(exc)[:55]}")
            n_error += 1
            continue
        print(
            f"{name:<50} "
            f"{mgd_label:<4} "
            f"{r.get('stack_hint', 'n/a'):<10} "
            f"{r.get('current_nix', '?'):<5} "
            f"{r.get('recommended_level', '?'):<10} "
            f"{r.get('score', 0):>5} "
            f"{r.get('gap', '?'):<15} "
            f"{r.get('confidence', '?'):<6}"
        )
        gap = r.get("gap", "")
        if gap == "ok":
            n_ok += 1
        elif gap == "missing-flake":
            n_missing += 1
        if r.get("confidence") == "low":
            n_borderline += 1

    print("-" * 115)
    print(
        f"summary: managed={n_managed}/{len(paths)}, ok={n_ok}, "
        f"missing-flake={n_missing}, borderline={n_borderline}, "
        f"error={n_error}, total={len(paths)}"
    )
    return 0


# ─────────────────────────────────────────────────────
# Mode 3: --propose (run_nix_propose) — Markdown retrofit suggestion
# ─────────────────────────────────────────────────────


def run_nix_propose(path: Path) -> int:
    """Emit Markdown retrofit proposal for a single project."""
    if not path.is_dir():
        print(f"Error: {path} not a directory")
        return 2

    record = evaluate_project(path)
    print(f"# Nix retrofit proposal — {path}")
    print()
    print("## Rubric output")
    print("```json")
    print(json.dumps(record, indent=2, ensure_ascii=False))
    print("```")
    print()

    if record.get("stage_a_exit"):
        print(f"## Stage A exit: {record['stage_a_exit']}")
        print()
        print(f"Recommendation: **{record['recommended_level']}**")
        if record["stage_a_exit"] == "existing-flake":
            print("Action: preserve / amend existing flake.nix")
        else:
            print(f"Action: no Nix adoption (Stage A: {record['stage_a_exit']})")
        return 0

    level = record.get("recommended_level", "none")
    template = record.get("recommended_template", "flake.nix.minimal")
    if level == "none":
        print(f"## Recommendation: **none** (score={record.get('score')}, justification 必須)")
        print()
        print(f"Cons signals: {', '.join(record.get('cons_signals', []))}")
        return 0

    print(f"## Recommendation: **{level}** (template `{template}`)")
    print()
    print(f"- stack_hint: {record.get('stack_hint')}")
    print(f"- score: {record.get('score')}")
    print(f"- pros: {', '.join(record.get('pros_signals', []))}")
    print(f"- cons: {', '.join(record.get('cons_signals', [])) or '(none)'}")
    print()
    print("## Retrofit steps")
    print()
    print(f"1. Copy `templates/artifacts/{template}` to `{path}/flake.nix`")
    print(f"   - Replace `{{{{PROJECT_NAME}}}}` with `{path.name}`")
    print(f"2. Copy `templates/artifacts/.envrc` to `{path}/.envrc`")
    print(f"3. Run `direnv allow` in `{path}`")
    print(f"4. Run `nix flake check` to lock dependencies")
    print(f"5. Commit `flake.nix` + `flake.lock` + `.envrc`")
    print(f"6. Update `AGENTS.md` (or brief) with Nix level: {level}")
    return 0
