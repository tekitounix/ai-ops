"""Tests for ai_ops.bootstrap (ADR 0002 amendment 2026-04-29)."""

from __future__ import annotations

import subprocess

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
    """Every tool must have either an automatic install command or an explicit
    manual_install_note for macOS and Linux apt — never silently nothing."""
    for tool in bootstrap.TOOLS:
        for os_kind in (bootstrap.OS_MACOS, bootstrap.OS_LINUX_APT):
            has_install = os_kind in tool.install_via
            has_note = os_kind in tool.manual_install_note
            assert has_install or has_note, (
                f"{tool.name} on {os_kind}: needs install_via or manual_install_note"
            )
        assert bootstrap.OS_MACOS in tool.install_via, (
            f"{tool.name} missing macOS install (manual on macOS would be unusual)"
        )
        assert bootstrap.OS_MACOS in tool.update_via, f"{tool.name} missing macOS update"


def test_install_command_shapes() -> None:
    """install_via commands must start with the expected prefix per OS so
    detect_os routing maps onto a coherent installer (no `apt-get` slipping
    into a brew section, etc.)."""
    expected_prefix: dict[str, list[str]] = {
        bootstrap.OS_MACOS: ["brew", "install"],
        bootstrap.OS_LINUX_APT: ["sudo", "apt-get", "install", "-y"],
        bootstrap.OS_WINDOWS_WSL: ["sudo", "apt-get", "install", "-y"],
        bootstrap.OS_LINUX_DNF: ["sudo", "dnf", "install", "-y"],
        bootstrap.OS_LINUX_PACMAN: ["sudo", "pacman", "-S", "--noconfirm"],
    }
    # nix uses Determinate installer; some Linux entries route through brew (Linuxbrew).
    nix_or_brew_exempt = {"nix", "actionlint", "gitleaks"}
    for tool in bootstrap.TOOLS:
        if tool.name in nix_or_brew_exempt:
            continue
        for os_kind, prefix in expected_prefix.items():
            cmd = tool.install_via.get(os_kind)
            if cmd is None:
                # Acceptable: tool has manual_install_note for this OS.
                assert os_kind in tool.manual_install_note, (
                    f"{tool.name} on {os_kind}: neither install nor note"
                )
                continue
            assert cmd[: len(prefix)] == prefix, (
                f"{tool.name} install for {os_kind} should start with {prefix}, got {cmd}"
            )
            assert all(isinstance(p, str) and p for p in cmd), (
                f"{tool.name} install for {os_kind} has empty / non-string component"
            )


def test_ghq_linux_uses_manual_note_not_apt() -> None:
    """Regression: ghq is not in Debian/Ubuntu apt repos, so install_via for
    apt-based OSes must be absent and a manual_install_note must be present."""
    ghq = next(t for t in bootstrap.TOOLS if t.name == "ghq")
    for os_kind in (bootstrap.OS_LINUX_APT, bootstrap.OS_WINDOWS_WSL):
        assert os_kind not in ghq.install_via
        assert os_kind in ghq.manual_install_note
        assert "ghq" in ghq.manual_install_note[os_kind].lower()


def test_run_install_warns_for_manual_only_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the only missing tier-1 tool needs manual install, run_install
    must surface the note and return 1, without prompting for confirmation."""

    only_ghq = next(t for t in bootstrap.TOOLS if t.name == "ghq")
    monkeypatch.setattr(bootstrap, "TOOLS", (only_ghq,))
    monkeypatch.setattr(bootstrap, "tool_present", lambda _t: False)
    monkeypatch.setattr(bootstrap, "tool_version", lambda _t: None)

    # `input()` should never be called. Make it raise to enforce that.
    def _no_input(_prompt):  # type: ignore[no-untyped-def]
        raise AssertionError("run_install must not prompt when only manual tools remain")

    monkeypatch.setattr("builtins.input", _no_input)

    rc = bootstrap.run_install(tier_max=1, os_override=bootstrap.OS_LINUX_APT)
    assert rc == 1  # tier-1 manual install required → not satisfied


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


# ---------- run_install_secrets (PR α: Bitwarden + gh) ----------


def test_install_secrets_returns_2_when_bw_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "_bw_available", lambda: False)
    monkeypatch.setattr(bootstrap, "_gh_available", lambda: True)
    rc = bootstrap.run_install_secrets(
        repo="o/r", anthropic_item="X", openai_item=None,
    )
    assert rc == 2


def test_install_secrets_returns_2_when_session_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "_bw_available", lambda: True)
    monkeypatch.setattr(bootstrap, "_gh_available", lambda: True)
    monkeypatch.delenv("BW_SESSION", raising=False)
    rc = bootstrap.run_install_secrets(
        repo="o/r", anthropic_item="X", openai_item=None,
    )
    assert rc == 2


def test_install_secrets_returns_2_when_no_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "_bw_available", lambda: True)
    monkeypatch.setattr(bootstrap, "_gh_available", lambda: True)
    monkeypatch.setenv("BW_SESSION", "session-token")
    rc = bootstrap.run_install_secrets(
        repo="o/r", anthropic_item=None, openai_item=None,
    )
    assert rc == 2


def test_install_secrets_proceeds_after_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_confirm を True 返却に固定すると secrets 登録ループが回る。"""
    monkeypatch.setattr(bootstrap, "_bw_available", lambda: True)
    monkeypatch.setattr(bootstrap, "_gh_available", lambda: True)
    monkeypatch.setenv("BW_SESSION", "session-token")
    monkeypatch.setattr(bootstrap, "_bw_get_field", lambda item, field: "fake-key")
    monkeypatch.setattr(bootstrap, "_confirm", lambda *a, **kw: True)

    secret_calls: list[tuple] = []

    def fake_set(repo, key, value, dry_run):
        secret_calls.append((repo, key, value, dry_run))
        return True

    monkeypatch.setattr(bootstrap, "_gh_secret_set", fake_set)
    rc = bootstrap.run_install_secrets(
        repo="o/r",
        anthropic_item="A",
        openai_item="O",
        dry_run=True,
    )
    assert rc == 0
    assert len(secret_calls) == 2
    assert {call[1] for call in secret_calls} == {"ANTHROPIC_API_KEY", "OPENAI_API_KEY"}


def test_install_secrets_records_failure_when_bw_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "_bw_available", lambda: True)
    monkeypatch.setattr(bootstrap, "_gh_available", lambda: True)
    monkeypatch.setenv("BW_SESSION", "session-token")
    monkeypatch.setattr(bootstrap, "_bw_get_field", lambda item, field: None)
    monkeypatch.setattr(bootstrap, "_gh_secret_set", lambda *a, **kw: True)
    monkeypatch.setattr(bootstrap, "_confirm", lambda *a, **kw: True)
    rc = bootstrap.run_install_secrets(
        repo="o/r", anthropic_item="A", openai_item=None, dry_run=True,
    )
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


# ─────────────────────────────────────────────────────
# install / update logic — actual subprocess paths
# ─────────────────────────────────────────────────────


def _stub_all_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every tool appear missing so run_install attempts to install."""
    monkeypatch.setattr(bootstrap, "tool_present", lambda _t: False)
    monkeypatch.setattr(bootstrap, "tool_version", lambda _t: None)


def _stub_all_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "tool_present", lambda _t: True)
    monkeypatch.setattr(bootstrap, "tool_version", lambda _t: "x.y.z")


_INSTALL_PREFIXES = ("brew", "sudo", "sh", "apt-get")


def _make_capturing_run(captured: list[list[str]], returncode: int = 0):
    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        first = cmd[0] if cmd else ""
        if first in _INSTALL_PREFIXES:
            captured.append(list(cmd))
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        # leave everything else alone
        return subprocess.run(cmd, *args, **kwargs)

    return fake_run


def test_run_install_invokes_subprocess_after_user_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User confirms with 'y' → install command is invoked for each missing tool."""
    import subprocess as _subprocess

    captured: list[list[str]] = []
    _stub_all_missing(monkeypatch)
    monkeypatch.setattr(bootstrap.subprocess, "run", _make_capturing_run(captured))
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")

    rc = bootstrap.run_install(tier_max=1, os_override=bootstrap.OS_MACOS)
    assert rc == 0
    assert captured, "expected install commands to be invoked"
    # tier-1 has 6 tools; all should be attempted under macOS
    assert len(captured) == 6
    del _subprocess  # unused


def test_run_install_returns_error_on_subprocess_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When subprocess.run raises CalledProcessError, run_install returns 1."""
    captured: list[list[str]] = []
    _stub_all_missing(monkeypatch)
    monkeypatch.setattr(
        bootstrap.subprocess, "run", _make_capturing_run(captured, returncode=2)
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")

    rc = bootstrap.run_install(tier_max=1, os_override=bootstrap.OS_MACOS)
    assert rc == 1


def test_run_install_returns_error_on_filenotfound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the install binary is missing entirely, FileNotFoundError → fail."""

    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        first = cmd[0] if cmd else ""
        if first in _INSTALL_PREFIXES:
            raise FileNotFoundError(f"command not found: {first}")
        return subprocess.run(cmd, *args, **kwargs)

    _stub_all_missing(monkeypatch)
    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")

    rc = bootstrap.run_install(tier_max=1, os_override=bootstrap.OS_MACOS)
    assert rc == 1


def test_run_install_aborts_when_user_declines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User answers 'n' → no install attempted; tier-1 missing → exit 1."""
    captured: list[list[str]] = []
    _stub_all_missing(monkeypatch)
    monkeypatch.setattr(bootstrap.subprocess, "run", _make_capturing_run(captured))
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    rc = bootstrap.run_install(tier_max=1, os_override=bootstrap.OS_MACOS)
    assert captured == []
    assert rc == 1  # tier-1 still missing


def test_run_install_returns_zero_when_all_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If nothing is missing, run_install returns 0 without prompting."""
    _stub_all_present(monkeypatch)
    # Even an `input` call would raise OSError under pytest if no stdin —
    # asserting we never reach it is enforced by the rc==0 short-circuit.
    rc = bootstrap.run_install(tier_max=1, os_override=bootstrap.OS_MACOS)
    assert rc == 0


def test_run_update_skips_tools_with_no_command_for_os(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool with no install_via entry for current OS is reported but not run."""
    _stub_all_present(monkeypatch)
    captured: list[list[str]] = []
    monkeypatch.setattr(bootstrap.subprocess, "run", _make_capturing_run(captured))
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")

    # Use a synthetic OS that no tool registers update commands for.
    rc = bootstrap.run_update(tier_max=2, os_override="zos-fictional")
    # Nothing matched, nothing invoked, no failures → rc 0.
    assert rc == 0
    assert captured == []
