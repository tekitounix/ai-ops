"""Tests for ai_ops.bootstrap (ADR 0002 amendment 2026-04-29)."""

from __future__ import annotations

import pytest

from ai_ops import bootstrap


def test_inventory_has_required_tier1_tools() -> None:
    """Tier 1 (= required) tools include git/ghq/direnv/jq/gh/nix."""
    tier1 = {t.name for t in bootstrap.TOOLS if t.tier == 1}
    assert {"git", "ghq", "direnv", "jq", "gh", "nix"} <= tier1


def test_inventory_has_recommended_tier2_tools() -> None:
    """Tier 2 (= recommended) tools include audit/lint helpers."""
    tier2 = {t.name for t in bootstrap.TOOLS if t.tier == 2}
    assert {"shellcheck", "actionlint", "gitleaks"} <= tier2


def test_every_tool_has_install_and_update_for_macos_and_linux_apt() -> None:
    """Every tool must have at least macOS + Linux (apt) install/update commands."""
    for tool in bootstrap.TOOLS:
        assert bootstrap.OS_MACOS in tool.install_via, f"{tool.name} missing macOS install"
        assert bootstrap.OS_LINUX_APT in tool.install_via, f"{tool.name} missing Linux apt install"
        assert bootstrap.OS_MACOS in tool.update_via, f"{tool.name} missing macOS update"
        assert bootstrap.OS_LINUX_APT in tool.update_via, f"{tool.name} missing Linux apt update"


def test_detect_os_returns_known_value() -> None:
    """detect_os returns one of the documented constants."""
    assert bootstrap.detect_os() in {
        bootstrap.OS_MACOS,
        bootstrap.OS_LINUX_APT,
        bootstrap.OS_LINUX_DNF,
        bootstrap.OS_LINUX_PACMAN,
        bootstrap.OS_WINDOWS_WSL,
        bootstrap.OS_UNKNOWN,
    }


def test_survey_returns_one_row_per_tool() -> None:
    """survey() returns (tool, present, version) triples for each tool."""
    rows = bootstrap.survey()
    assert len(rows) == len(bootstrap.TOOLS)
    for tool, present, version in rows:
        assert isinstance(tool, bootstrap.Tool)
        assert isinstance(present, bool)
        assert version is None or isinstance(version, str)


_INSTALL_UPDATE_COMMANDS = {"brew", "sudo", "sh"}


def _make_install_blocker(captured: list[list[str]]):
    """Return a fake subprocess.run that blocks install/update commands but
    delegates other (e.g. version) calls to the real subprocess.run.
    """
    real_run = bootstrap.subprocess.run

    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        first = cmd[0] if cmd else ""
        if first in _INSTALL_UPDATE_COMMANDS:
            captured.append(cmd)
            raise AssertionError(f"install/update should not be called in dry-run: {cmd}")
        return real_run(cmd, *args, **kwargs)

    return fake_run


def test_run_install_dry_run_does_not_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """--dry-run path never invokes subprocess.run for installation."""
    called: list[list[str]] = []
    monkeypatch.setattr(bootstrap.subprocess, "run", _make_install_blocker(called))
    rc = bootstrap.run_install(tier_max=1, dry_run=True, os_override=bootstrap.OS_MACOS)
    # rc 0 if everything present, 1 if any tier-1 missing — both acceptable
    assert rc in (0, 1)
    assert called == []


def test_run_update_dry_run_does_not_update(monkeypatch: pytest.MonkeyPatch) -> None:
    """--dry-run path never invokes subprocess.run for updates."""
    called: list[list[str]] = []
    monkeypatch.setattr(bootstrap.subprocess, "run", _make_install_blocker(called))
    rc = bootstrap.run_update(tier_max=2, dry_run=True, os_override=bootstrap.OS_MACOS)
    assert rc == 0
    assert called == []


def test_unsupported_os_returns_error_code() -> None:
    rc = bootstrap.run_install(tier_max=1, dry_run=True, os_override=bootstrap.OS_UNKNOWN)
    assert rc == 1


def test_nix_install_uses_determinate_installer() -> None:
    """Nix install must use Determinate Nix Installer for all OSes (macOS upgrade resilience)."""
    nix_tool = next(t for t in bootstrap.TOOLS if t.name == "nix")
    for os_kind, cmd in nix_tool.install_via.items():
        joined = " ".join(cmd)
        assert "install.determinate.systems" in joined, (
            f"Nix install for {os_kind} must use Determinate installer, got: {joined}"
        )


def test_detect_os_returns_unknown_when_no_package_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a Linux box without apt/dnf/pacman (Alpine, NixOS, void), detect_os
    must return OS_UNKNOWN — not silently fall back to apt and try `apt-get
    install` at execute time."""
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Linux")
    monkeypatch.setattr(bootstrap.platform, "release", lambda: "6.0.0-generic")
    monkeypatch.setattr(bootstrap.shutil, "which", lambda _name: None)
    assert bootstrap.detect_os() == bootstrap.OS_UNKNOWN
