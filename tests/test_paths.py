"""Tests for ai_ops.paths.package_root resolution order."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_ops.paths import package_root


def test_package_root_prefers_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AI_OPS_PACKAGE_ROOT must win over bundled and source-tree fallbacks.

    This is what `nix run` relies on: the wrapper exports the flake's source
    path so paths.py can find AGENTS.md + templates/ without changing $PWD.
    """
    fake_root = tmp_path / "fake"
    (fake_root / "templates").mkdir(parents=True)
    (fake_root / "AGENTS.md").write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv("AI_OPS_PACKAGE_ROOT", str(fake_root))
    assert package_root() == fake_root


def test_package_root_ignores_invalid_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If AI_OPS_PACKAGE_ROOT points at a directory missing AGENTS.md or
    templates/, paths.py must fall through, not silently accept a half-set
    environment."""
    monkeypatch.setenv("AI_OPS_PACKAGE_ROOT", str(tmp_path))
    # tmp_path has neither AGENTS.md nor templates/ → fall through to the
    # editable / source-tree fallback, which for this checkout is the repo
    # root. Just check we did not accept tmp_path.
    assert package_root() != tmp_path
