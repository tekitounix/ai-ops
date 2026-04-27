from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


SKIP_DIRS = {".git", ".direnv", ".pytest_cache", "__pycache__", "result"}
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
        if _contains_secret_value(path):
            print(f"  FAIL: secret-looking value pattern found in: {rel}")
            fail += 1

    if not fail:
        print("  OK: no secret-looking active files or values found")

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
