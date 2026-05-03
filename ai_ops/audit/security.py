from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


SKIP_DIRS = {
    # VCS / direnv / Python tool caches
    ".git", ".direnv", ".pytest_cache", ".tox", ".eggs", "__pycache__",
    # Python virtual env (path-encoded in pyc files; not source-of-truth)
    ".venv", "venv",
    # Node / package managers
    "node_modules",
    # Build / dependency vendor trees
    "vendor", "target", "dist", "build", ".cache", ".next", ".gradle",
    # Nix / Bazel
    "result", "bazel-out",
}
# tests/ 配下を一律 skip すると、gitleaks fallback 時に test fixture を装った
# 実 secret を見逃す。fixture が必要なら tests/fixtures/ に隔離する規約に絞る。
# Lowercase only — `tests/Fixtures/` 等の大文字混在は意図的に skip しない
# (POSIX 慣習に揃えてもらう方が、case-insensitive にしてカテゴリを増やすより安全)。
VALUE_SCAN_FIXTURE_PARTS = ("tests", "fixtures")
# Suffixes after `.env.` that mark a template / placeholder file rather than a
# real secret store. `.env.example` is universal; `.env.template` / `.sample` /
# `.dist` / `.default` are common in cookiecutter / Rails / Laravel layouts.
ENV_TEMPLATE_SUFFIXES = frozenset({
    "example", "template", "sample", "dist", "default", "tmpl",
})
SECRET_NAME_PATTERNS = (
    re.compile(r"(^|/)\.env(\..*)?$"),
    re.compile(r"(^|/)secrets?(/|$)"),
    re.compile(r"\.(key|pem|p12|pfx)$"),
    re.compile(r"(^|/)id_(rsa|dsa|ecdsa|ed25519)$"),
)
SECRET_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
)

# ADR 0004 hardening (PR β): Python ソース内で secret 値を CLI 引数に渡す pattern を
# 機械検出する。process list (`ps auxww`) 経由で値が漏れるのを防ぐ。stdin 経由
# (`--body-file -`、`--password-stdin`) または環境変数渡しに統一する。
# scan 対象は `ai_ops/` のみ (tests/ は意図的な fixture / mock を含む)。
SECRET_ARG_FORBIDDEN_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (
        re.compile(r"['\"]--body['\"]\s*,\s*[^'\"]*?(value|secret|key|token|password)"),
        "secret value passed via `--body <value>` (use `--body-file -` + stdin)",
    ),
    (
        re.compile(r"['\"]--password['\"]\s*,\s*[^'\"]*?(value|secret|key|token|password)"),
        "password passed via `--password <value>` CLI arg",
    ),
    (
        re.compile(r"['\"]--token['\"]\s*,\s*[^'\"]*?(value|secret|key|token)"),
        "token passed via `--token <value>` CLI arg",
    ),
)


def run_security_audit(root: Path) -> int:
    print("==> Public security audit")
    fail = 0
    files = list(_iter_files(root))

    for path in files:
        rel = path.relative_to(root).as_posix()
        if _is_secret_name(rel):
            print(f"  FAIL: secret-looking file is present: {rel}")
            fail += 1

    for path in files:
        rel = path.relative_to(root).as_posix()
        rel_parts = path.relative_to(root).parts
        if rel_parts[: len(VALUE_SCAN_FIXTURE_PARTS)] == VALUE_SCAN_FIXTURE_PARTS:
            continue
        if _contains_secret_value(path):
            print(f"  FAIL: secret-looking value pattern found in: {rel}")
            fail += 1

    if not fail:
        print("  OK: no secret-looking active files or values found")

    # ADR 0004 hardening: ai_ops/ 配下で secret 値を CLI 引数に渡す pattern を検出。
    # 自モジュール (ai_ops/audit/security.py) は pattern 定義そのものを含むので除外。
    self_module = root / "ai_ops" / "audit" / "security.py"
    forbidden_arg_hits: list[tuple[Path, int, str]] = []
    ai_ops_dir = root / "ai_ops"
    if ai_ops_dir.is_dir():
        for path in ai_ops_dir.rglob("*.py"):
            if path.resolve() == self_module.resolve():
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(lines, 1):
                for pattern, description in SECRET_ARG_FORBIDDEN_PATTERNS:
                    if pattern.search(line):
                        forbidden_arg_hits.append(
                            (path.relative_to(root), i, description)
                        )
    if forbidden_arg_hits:
        for rel_path, line_no, desc in forbidden_arg_hits:
            print(f"  FAIL: forbidden secret-arg pattern at {rel_path}:{line_no} — {desc}")
            fail += 1
    else:
        print("  OK: no forbidden secret-arg patterns in ai_ops/")

    if shutil.which("gitleaks"):
        fail += _run_gitleaks(["gitleaks", "dir", str(root), "--no-banner", "--redact"])
        if (root / ".git").is_dir():
            fail += _run_gitleaks(["gitleaks", "git", str(root), "--no-banner", "--redact"])
    else:
        print("  WARN: gitleaks not installed; built-in security scan only")

    return 1 if fail else 0


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            yield path


def _is_secret_name(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    # `.env.example` and friends are explicit templates, not real secrets.
    if name.startswith(".env."):
        suffix = name[len(".env."):].lower()
        if suffix in ENV_TEMPLATE_SUFFIXES:
            return False
    return any(pattern.search(rel) for pattern in SECRET_NAME_PATTERNS)


def _contains_secret_value(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    return any(pattern.search(text) for pattern in SECRET_VALUE_PATTERNS)


def _run_gitleaks(args: list[str]) -> int:
    label = " ".join(args[:2])
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode == 0:
        print(f"  OK: {label} passed")
        return 0
    print(f"  FAIL: {label} reported findings")
    if result.stdout:
        print(result.stdout.rstrip())
    return 1
