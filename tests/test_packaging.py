"""Verify that a non-editable `pip install` produces a self-contained ai-ops.

The repo ships AGENTS.md and templates/ at the top level (where humans expect
them). Without explicit packaging glue those files are absent from the wheel,
so `pip install ai-ops` would silently break `ai-ops new` / `ai-ops migrate`.
This test installs the project to a fresh target directory and runs the CLI
from outside the repo to ensure the bundled resources are reachable.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.slow
def test_non_editable_install_bundles_agents_md_and_templates(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    target = tmp_path / "site"
    target.mkdir()

    install = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--target",
            str(target),
            "--quiet",
            "--no-deps",
            str(repo),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert install.returncode == 0, f"pip install failed: {install.stderr}"

    bundled = target / "ai_ops" / "_resources"
    assert (bundled / "AGENTS.md").is_file(), "AGENTS.md not bundled into wheel"
    assert (bundled / "templates" / "project-brief.md").is_file(), (
        "templates/ not bundled into wheel"
    )
    assert (bundled / "templates" / "plan.md").is_file()

    env = {**os.environ, "PYTHONPATH": str(target), "PYTHONIOENCODING": "utf-8"}
    # Run from tmp_path (not the repo) so paths.py can't fall back to the
    # source tree's AGENTS.md / templates/. Force UTF-8 in/out so the
    # Windows runner's cp1252 locale doesn't blow up on AGENTS.md kana.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_ops",
            "new",
            "smoke",
            "--purpose",
            "x",
            "--agent",
            "prompt-only",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(tmp_path),
        timeout=30,
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert "Operating rules (from ai-ops AGENTS.md" in result.stdout
    assert "## 1. Summary" in result.stdout
