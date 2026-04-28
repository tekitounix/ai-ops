"""Bootstrap and update of required tools (ADR 0002 amendment 2026-04-29).

ai-ops は silent installer ではないが、user 明示承認 (Operation model:
Propose → Confirm → Execute) を経た install / update は許可される。
本 module は必須 tool の existence check + user 承認付き install/update を提供。
"""

from __future__ import annotations

import dataclasses
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence


@dataclasses.dataclass(frozen=True)
class Tool:
    """Required tool descriptor."""

    name: str  # binary name (= shutil.which 検索 key)
    tier: int  # 1 = required, 2 = recommended
    purpose: str  # 説明 (audit / lint / 等)
    install_via: dict[str, list[str]]  # OS -> install command (argv form)
    update_via: dict[str, list[str]]  # OS -> update command (argv form)
    version_arg: tuple[str, ...] = ("--version",)  # version 表示 argv


# OS detection — `detect_os()` で得られる文字列と一致
OS_MACOS = "macos"
OS_LINUX_APT = "linux-apt"  # Debian / Ubuntu
OS_LINUX_DNF = "linux-dnf"  # Fedora / RHEL
OS_LINUX_PACMAN = "linux-pacman"  # Arch
OS_WINDOWS_WSL = "windows-wsl"  # WSL = Linux 内
OS_UNKNOWN = "unknown"


def detect_os() -> str:
    """Detect OS for installer mapping. WSL is treated as Linux."""
    system = platform.system()
    if system == "Darwin":
        return OS_MACOS
    if system == "Linux":
        # WSL detection (uname -r contains "microsoft" or "WSL")
        try:
            release = platform.release().lower()
        except Exception:
            release = ""
        if "microsoft" in release or "wsl" in release:
            return OS_WINDOWS_WSL  # = treated as Linux + apt
        # detect package manager
        if shutil.which("apt-get"):
            return OS_LINUX_APT
        if shutil.which("dnf"):
            return OS_LINUX_DNF
        if shutil.which("pacman"):
            return OS_LINUX_PACMAN
        return OS_LINUX_APT  # default
    return OS_UNKNOWN


def _brew(*pkgs: str) -> list[str]:
    return ["brew", "install", *pkgs]


def _brew_upgrade(*pkgs: str) -> list[str]:
    return ["brew", "upgrade", *pkgs]


def _apt_install(*pkgs: str) -> list[str]:
    return ["sudo", "apt-get", "install", "-y", *pkgs]


def _apt_upgrade(*pkgs: str) -> list[str]:
    return ["sudo", "apt-get", "install", "--only-upgrade", "-y", *pkgs]


def _dnf_install(*pkgs: str) -> list[str]:
    return ["sudo", "dnf", "install", "-y", *pkgs]


def _dnf_upgrade(*pkgs: str) -> list[str]:
    return ["sudo", "dnf", "upgrade", "-y", *pkgs]


def _pacman_install(*pkgs: str) -> list[str]:
    return ["sudo", "pacman", "-S", "--noconfirm", *pkgs]


def _pacman_upgrade(*pkgs: str) -> list[str]:
    return ["sudo", "pacman", "-Syu", "--noconfirm", *pkgs]


# Determinate Nix Installer (recommended). Nix は package manager 経由ではなく
# 公式 installer を使う (= multi-user daemon 設定 + macOS upgrade 耐性のため)。
_DETERMINATE_NIX_INSTALL = [
    "sh",
    "-c",
    "curl --proto '=https' --tlsv1.2 -sSf -L "
    "https://install.determinate.systems/nix | sh -s -- install --determinate",
]
_DETERMINATE_NIX_UPGRADE = ["sudo", "-i", "nix", "upgrade-nix"]


# Tier 1 (必須) + Tier 2 (推奨) inventory
TOOLS: tuple[Tool, ...] = (
    # Tier 1: 必須
    Tool(
        name="git",
        tier=1,
        purpose="version control (ai-ops + 全 project の前提)",
        install_via={
            OS_MACOS: _brew("git"),
            OS_LINUX_APT: _apt_install("git"),
            OS_WINDOWS_WSL: _apt_install("git"),
            OS_LINUX_DNF: _dnf_install("git"),
            OS_LINUX_PACMAN: _pacman_install("git"),
        },
        update_via={
            OS_MACOS: _brew_upgrade("git"),
            OS_LINUX_APT: _apt_upgrade("git"),
            OS_WINDOWS_WSL: _apt_upgrade("git"),
            OS_LINUX_DNF: _dnf_upgrade("git"),
            OS_LINUX_PACMAN: _pacman_upgrade("git"),
        },
    ),
    Tool(
        name="ghq",
        tier=1,
        purpose="repo placement (ai-ops が認識する project = ghq managed)",
        install_via={
            OS_MACOS: _brew("ghq"),
            OS_LINUX_APT: ["sudo", "apt-get", "install", "-y", "ghq"],
            OS_WINDOWS_WSL: ["sudo", "apt-get", "install", "-y", "ghq"],
            OS_LINUX_DNF: _dnf_install("ghq"),
            OS_LINUX_PACMAN: _pacman_install("ghq"),
        },
        update_via={
            OS_MACOS: _brew_upgrade("ghq"),
            OS_LINUX_APT: _apt_upgrade("ghq"),
            OS_WINDOWS_WSL: _apt_upgrade("ghq"),
            OS_LINUX_DNF: _dnf_upgrade("ghq"),
            OS_LINUX_PACMAN: _pacman_upgrade("ghq"),
        },
    ),
    Tool(
        name="direnv",
        tier=1,
        purpose="per-project env loader (Nix flake devshell 自動 enter)",
        install_via={
            OS_MACOS: _brew("direnv"),
            OS_LINUX_APT: _apt_install("direnv"),
            OS_WINDOWS_WSL: _apt_install("direnv"),
            OS_LINUX_DNF: _dnf_install("direnv"),
            OS_LINUX_PACMAN: _pacman_install("direnv"),
        },
        update_via={
            OS_MACOS: _brew_upgrade("direnv"),
            OS_LINUX_APT: _apt_upgrade("direnv"),
            OS_WINDOWS_WSL: _apt_upgrade("direnv"),
            OS_LINUX_DNF: _dnf_upgrade("direnv"),
            OS_LINUX_PACMAN: _pacman_upgrade("direnv"),
        },
    ),
    Tool(
        name="jq",
        tier=1,
        purpose="JSON parser (audit / hooks / scripts 全般)",
        install_via={
            OS_MACOS: _brew("jq"),
            OS_LINUX_APT: _apt_install("jq"),
            OS_WINDOWS_WSL: _apt_install("jq"),
            OS_LINUX_DNF: _dnf_install("jq"),
            OS_LINUX_PACMAN: _pacman_install("jq"),
        },
        update_via={
            OS_MACOS: _brew_upgrade("jq"),
            OS_LINUX_APT: _apt_upgrade("jq"),
            OS_WINDOWS_WSL: _apt_upgrade("jq"),
            OS_LINUX_DNF: _dnf_upgrade("jq"),
            OS_LINUX_PACMAN: _pacman_upgrade("jq"),
        },
    ),
    Tool(
        name="gh",
        tier=1,
        purpose="GitHub CLI (T1/T2 project 作成 + visibility 監査)",
        install_via={
            OS_MACOS: _brew("gh"),
            OS_LINUX_APT: _apt_install("gh"),
            OS_WINDOWS_WSL: _apt_install("gh"),
            OS_LINUX_DNF: _dnf_install("gh"),
            OS_LINUX_PACMAN: _pacman_install("github-cli"),
        },
        update_via={
            OS_MACOS: _brew_upgrade("gh"),
            OS_LINUX_APT: _apt_upgrade("gh"),
            OS_WINDOWS_WSL: _apt_upgrade("gh"),
            OS_LINUX_DNF: _dnf_upgrade("gh"),
            OS_LINUX_PACMAN: _pacman_upgrade("github-cli"),
        },
    ),
    Tool(
        name="nix",
        tier=1,
        purpose="reproducibility layer (project-level flake、ADR 0005)",
        install_via={
            OS_MACOS: _DETERMINATE_NIX_INSTALL,
            OS_LINUX_APT: _DETERMINATE_NIX_INSTALL,
            OS_WINDOWS_WSL: _DETERMINATE_NIX_INSTALL,
            OS_LINUX_DNF: _DETERMINATE_NIX_INSTALL,
            OS_LINUX_PACMAN: _DETERMINATE_NIX_INSTALL,
        },
        update_via={
            OS_MACOS: _DETERMINATE_NIX_UPGRADE,
            OS_LINUX_APT: _DETERMINATE_NIX_UPGRADE,
            OS_WINDOWS_WSL: _DETERMINATE_NIX_UPGRADE,
            OS_LINUX_DNF: _DETERMINATE_NIX_UPGRADE,
            OS_LINUX_PACMAN: _DETERMINATE_NIX_UPGRADE,
        },
    ),
    # Tier 2: 推奨
    Tool(
        name="shellcheck",
        tier=2,
        purpose="shell script audit",
        install_via={
            OS_MACOS: _brew("shellcheck"),
            OS_LINUX_APT: _apt_install("shellcheck"),
            OS_WINDOWS_WSL: _apt_install("shellcheck"),
            OS_LINUX_DNF: _dnf_install("ShellCheck"),
            OS_LINUX_PACMAN: _pacman_install("shellcheck"),
        },
        update_via={
            OS_MACOS: _brew_upgrade("shellcheck"),
            OS_LINUX_APT: _apt_upgrade("shellcheck"),
            OS_WINDOWS_WSL: _apt_upgrade("shellcheck"),
            OS_LINUX_DNF: _dnf_upgrade("ShellCheck"),
            OS_LINUX_PACMAN: _pacman_upgrade("shellcheck"),
        },
    ),
    Tool(
        name="actionlint",
        tier=2,
        purpose="GitHub Actions workflow lint",
        install_via={
            OS_MACOS: _brew("actionlint"),
            OS_LINUX_APT: _brew("actionlint"),  # apt にないため Homebrew on Linux 推奨
            OS_WINDOWS_WSL: _brew("actionlint"),
            OS_LINUX_DNF: _brew("actionlint"),
            OS_LINUX_PACMAN: _pacman_install("actionlint"),
        },
        update_via={
            OS_MACOS: _brew_upgrade("actionlint"),
            OS_LINUX_APT: _brew_upgrade("actionlint"),
            OS_WINDOWS_WSL: _brew_upgrade("actionlint"),
            OS_LINUX_DNF: _brew_upgrade("actionlint"),
            OS_LINUX_PACMAN: _pacman_upgrade("actionlint"),
        },
    ),
    Tool(
        name="gitleaks",
        tier=2,
        purpose="secrets scanning (pre-commit / CI)",
        install_via={
            OS_MACOS: _brew("gitleaks"),
            OS_LINUX_APT: _brew("gitleaks"),
            OS_WINDOWS_WSL: _brew("gitleaks"),
            OS_LINUX_DNF: _brew("gitleaks"),
            OS_LINUX_PACMAN: _pacman_install("gitleaks"),
        },
        update_via={
            OS_MACOS: _brew_upgrade("gitleaks"),
            OS_LINUX_APT: _brew_upgrade("gitleaks"),
            OS_WINDOWS_WSL: _brew_upgrade("gitleaks"),
            OS_LINUX_DNF: _brew_upgrade("gitleaks"),
            OS_LINUX_PACMAN: _pacman_upgrade("gitleaks"),
        },
    ),
    Tool(
        name="fzf",
        tier=2,
        purpose="interactive selection (横断 ghq / project 探索)",
        install_via={
            OS_MACOS: _brew("fzf"),
            OS_LINUX_APT: _apt_install("fzf"),
            OS_WINDOWS_WSL: _apt_install("fzf"),
            OS_LINUX_DNF: _dnf_install("fzf"),
            OS_LINUX_PACMAN: _pacman_install("fzf"),
        },
        update_via={
            OS_MACOS: _brew_upgrade("fzf"),
            OS_LINUX_APT: _apt_upgrade("fzf"),
            OS_WINDOWS_WSL: _apt_upgrade("fzf"),
            OS_LINUX_DNF: _dnf_upgrade("fzf"),
            OS_LINUX_PACMAN: _pacman_upgrade("fzf"),
        },
    ),
    Tool(
        name="rg",
        tier=2,
        purpose="ripgrep (cross-project search)",
        install_via={
            OS_MACOS: _brew("ripgrep"),
            OS_LINUX_APT: _apt_install("ripgrep"),
            OS_WINDOWS_WSL: _apt_install("ripgrep"),
            OS_LINUX_DNF: _dnf_install("ripgrep"),
            OS_LINUX_PACMAN: _pacman_install("ripgrep"),
        },
        update_via={
            OS_MACOS: _brew_upgrade("ripgrep"),
            OS_LINUX_APT: _apt_upgrade("ripgrep"),
            OS_WINDOWS_WSL: _apt_upgrade("ripgrep"),
            OS_LINUX_DNF: _dnf_upgrade("ripgrep"),
            OS_LINUX_PACMAN: _pacman_upgrade("ripgrep"),
        },
    ),
)


def tool_present(tool: Tool) -> bool:
    return shutil.which(tool.name) is not None


def tool_version(tool: Tool) -> str | None:
    """Return version string or None if unavailable."""
    if not tool_present(tool):
        return None
    try:
        result = subprocess.run(
            [tool.name, *tool.version_arg],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
            check=False,
        )
        return result.stdout.strip().splitlines()[0] if result.stdout else None
    except Exception:
        return None


def survey(tools: Iterable[Tool] = TOOLS) -> list[tuple[Tool, bool, str | None]]:
    """Return [(tool, present, version_or_None)] for each tool."""
    return [(t, tool_present(t), tool_version(t)) for t in tools]


def print_survey(rows: Sequence[tuple[Tool, bool, str | None]]) -> None:
    print("==> Required tool survey")
    for tool, present, version in rows:
        tier_label = f"T{tool.tier}"
        if present:
            print(f"  OK  ({tier_label}) {tool.name:<12} {version or ''}")
        else:
            mark = "MISSING" if tool.tier == 1 else "missing"
            print(f"  {mark} ({tier_label}) {tool.name:<12} — {tool.purpose}")


def _confirm(prompt: str, *, dry_run: bool) -> bool:
    if dry_run:
        print(f"  [dry-run] would prompt: {prompt}")
        return False
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def run_install(
    *,
    tier_max: int = 1,
    dry_run: bool = False,
    os_override: str | None = None,
) -> int:
    """Install missing tools at or below tier_max.

    Returns 0 if all required tools are now present, 1 otherwise.
    """
    os_kind = os_override or detect_os()
    if os_kind == OS_UNKNOWN:
        print(f"Error: unsupported OS ({platform.system()})", file=sys.stderr)
        return 1

    rows = survey()
    print_survey(rows)
    missing = [(t, p, v) for (t, p, v) in rows if not p and t.tier <= tier_max]
    if not missing:
        print("\nAll required tools present.")
        return 0

    print(f"\n==> {len(missing)} missing tool(s) to install (tier ≤ {tier_max}, OS={os_kind})")
    for tool, _, _ in missing:
        cmd = tool.install_via.get(os_kind)
        if not cmd:
            print(f"  WARN: {tool.name} has no install command for {os_kind}")
            continue
        print(f"  - {tool.name}: {' '.join(cmd)}")

    if not _confirm("\nProceed to install above tools?", dry_run=dry_run):
        print("Skipped (no install performed).")
        return 1 if any(t.tier == 1 for t, _, _ in missing) else 0

    failed = 0
    for tool, _, _ in missing:
        cmd = tool.install_via.get(os_kind)
        if not cmd:
            failed += 1
            continue
        print(f"\n==> Installing {tool.name} ...")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            print(f"  FAIL: {tool.name} (exit {exc.returncode})", file=sys.stderr)
            failed += 1
        except FileNotFoundError as exc:
            print(f"  FAIL: {tool.name} (command not found: {exc})", file=sys.stderr)
            failed += 1

    if failed:
        print(f"\n{failed} tool(s) failed to install.")
        return 1
    print("\nAll requested tools installed.")
    return 0


def run_update(
    *,
    tier_max: int = 2,
    dry_run: bool = False,
    os_override: str | None = None,
) -> int:
    """Update all present tools at or below tier_max."""
    os_kind = os_override or detect_os()
    if os_kind == OS_UNKNOWN:
        print(f"Error: unsupported OS ({platform.system()})", file=sys.stderr)
        return 1

    rows = survey()
    print_survey(rows)
    present = [(t, p, v) for (t, p, v) in rows if p and t.tier <= tier_max]
    if not present:
        print("\nNo tools to update.")
        return 0

    print(f"\n==> {len(present)} tool(s) to update (tier ≤ {tier_max}, OS={os_kind})")
    for tool, _, _ in present:
        cmd = tool.update_via.get(os_kind)
        if not cmd:
            print(f"  WARN: {tool.name} has no update command for {os_kind}")
            continue
        print(f"  - {tool.name}: {' '.join(cmd)}")

    if not _confirm("\nProceed to update above tools?", dry_run=dry_run):
        print("Skipped (no update performed).")
        return 0

    failed = 0
    for tool, _, _ in present:
        cmd = tool.update_via.get(os_kind)
        if not cmd:
            continue
        print(f"\n==> Updating {tool.name} ...")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            print(f"  FAIL: {tool.name} (exit {exc.returncode})", file=sys.stderr)
            failed += 1
        except FileNotFoundError as exc:
            print(f"  FAIL: {tool.name} (command not found: {exc})", file=sys.stderr)
            failed += 1

    if failed:
        print(f"\n{failed} tool(s) failed to update.")
        return 1
    print("\nAll requested tools updated.")
    return 0
