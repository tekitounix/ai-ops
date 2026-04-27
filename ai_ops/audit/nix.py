from __future__ import annotations

from pathlib import Path


def run_nix_audit(root: Path) -> int:
    print("==> Nix adoption audit")
    flake = root / "flake.nix"
    lock = root / "flake.lock"
    fail = 0
    if flake.is_file():
        print("  OK: flake.nix exists")
    else:
        print("  FAIL: flake.nix missing")
        fail += 1
    if lock.is_file():
        print("  OK: flake.lock exists")
    else:
        print("  WARN: flake.lock missing")
    if flake.is_file():
        text = flake.read_text(encoding="utf-8")
        if "ai_ops" in text and "python" in text:
            print("  OK: flake.nix references Python CLI")
        else:
            print("  FAIL: flake.nix should wrap Python CLI")
            fail += 1
    return 1 if fail else 0
