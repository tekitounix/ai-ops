from __future__ import annotations

import compileall
import shutil
import subprocess
import sys
from pathlib import Path

from ai_ops.audit.lifecycle import run_lifecycle_audit
from ai_ops.audit.nix import run_nix_audit
from ai_ops.audit.security import run_security_audit


def run_check(root: Path) -> int:
    fail = 0

    print("==> python compile")
    ai_ops_dir = root / "ai_ops"
    if ai_ops_dir.is_dir():
        if not compileall.compile_dir(ai_ops_dir, quiet=1):
            fail += 1
    else:
        print(f"  SKIP: {ai_ops_dir} not a directory")

    print("==> lifecycle audit")
    fail += run_lifecycle_audit(root)

    print("==> nix audit")
    fail += run_nix_audit(root)

    print("==> security audit")
    fail += run_security_audit(root)

    if (root / "tests").is_dir() and shutil.which("pytest"):
        print("==> pytest (excluding slow / network / pip-install integration)")
        # `slow` markers cover integration tests that build a wheel or shell
        # out to pip — those need a pip-bearing environment and don't fit
        # inside the Nix sandbox or this in-process check. Run them explicitly
        # via `python -m pytest -m slow` (e.g. in CI or before a release).
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-m", "not slow"],
            cwd=str(root),
            check=False,
        )
        if result.returncode != 0:
            fail += 1
    else:
        print("==> pytest skipped (pytest or tests missing)")

    if fail:
        print(f"==> ai-ops check failed ({fail})")
        return 1
    print("==> ai-ops check passed")
    return 0
