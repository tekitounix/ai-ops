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
    # Some tools are not in distro repos (e.g. ghq on Debian/Ubuntu apt).
    # manual_install_note maps OS -> human instruction shown when install_via
    # has no entry for that OS. The bootstrap step then warns and skips
    # rather than running the wrong package manager.
    manual_install_note: dict[str, str] = dataclasses.field(default_factory=dict)


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
        # detect package manager — never silently fall back to apt on a
        # non-apt system (e.g. Alpine apk, NixOS, void); that would invoke
        # the wrong installer at execute time. Surface unknown and let the
        # caller fail loudly.
        if shutil.which("apt-get"):
            return OS_LINUX_APT
        if shutil.which("dnf"):
            return OS_LINUX_DNF
        if shutil.which("pacman"):
            return OS_LINUX_PACMAN
        return OS_UNKNOWN
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
            # Linux 各 distro の公式 repo に ghq は存在しない。Linuxbrew か
            # `go install github.com/x-motemen/ghq/cmd/ghq@latest` で入れる。
            # Pacman には AUR 版があるが --noconfirm で AUR helper 前提になるため
            # ここでは hands-off にして note のみ。
        },
        update_via={
            OS_MACOS: _brew_upgrade("ghq"),
        },
        manual_install_note={
            OS_LINUX_APT: (
                "ghq is not in apt repos. Install via Linuxbrew "
                "(`brew install ghq`) or `go install github.com/x-motemen/ghq/cmd/ghq@latest`."
            ),
            OS_WINDOWS_WSL: (
                "ghq is not in apt repos. Install via Linuxbrew "
                "(`brew install ghq`) or `go install github.com/x-motemen/ghq/cmd/ghq@latest`."
            ),
            OS_LINUX_DNF: (
                "ghq is not in dnf repos. Install via Linuxbrew or "
                "`go install github.com/x-motemen/ghq/cmd/ghq@latest`."
            ),
            OS_LINUX_PACMAN: (
                "ghq is in AUR; use your preferred AUR helper "
                "(e.g. `yay -S ghq`) or install via Linuxbrew."
            ),
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


def survey(tools: Iterable[Tool] | None = None) -> list[tuple[Tool, bool, str | None]]:
    """Return [(tool, present, version_or_None)] for each tool.

    `tools=None` reads `TOOLS` at call time (not at function-definition time)
    so test monkeypatching of the module-level inventory takes effect.
    """
    iterable = TOOLS if tools is None else tools
    return [(t, tool_present(t), tool_version(t)) for t in iterable]


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
    yes: bool = False,
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

    auto_installable = [m for m in missing if m[0].install_via.get(os_kind)]
    manual_only = [m for m in missing if not m[0].install_via.get(os_kind)]

    print(f"\n==> {len(missing)} missing tool(s) (tier ≤ {tier_max}, OS={os_kind})")
    for tool, _, _ in auto_installable:
        cmd = tool.install_via[os_kind]
        print(f"  - {tool.name}: {' '.join(cmd)}")
    for tool, _, _ in manual_only:
        note = tool.manual_install_note.get(os_kind, "no install command available")
        print(f"  - {tool.name}: MANUAL — {note}")

    manual_tier1_present = any(t.tier == 1 for t, _, _ in manual_only)

    if not auto_installable:
        if manual_only:
            print("\nNo tools can be auto-installed; resolve the manual entries above.")
        return 1 if manual_tier1_present else 0

    if not yes and not _confirm(
        "\nProceed to install the auto-installable tools above?", dry_run=dry_run
    ):
        print("Skipped (no install performed).")
        return 1 if any(t.tier == 1 for t, _, _ in missing) else 0

    failed = 0
    for tool, _, _ in auto_installable:
        cmd = tool.install_via[os_kind]
        print(f"\n==> Installing {tool.name} ...")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            print(f"  FAIL: {tool.name} (exit {exc.returncode})", file=sys.stderr)
            failed += 1
        except FileNotFoundError as exc:
            print(f"  FAIL: {tool.name} (command not found: {exc})", file=sys.stderr)
            failed += 1

    if failed or manual_tier1_present:
        if failed:
            print(f"\n{failed} tool(s) failed to install.")
        if manual_tier1_present:
            print("Some tier-1 tools require manual install (see notes above).")
        return 1
    print("\nAll auto-installable tools installed.")
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


# ---------- secrets (Bitwarden + gh secret set) ----------
#
# `ai-ops bootstrap --with-secrets` の実装。Bitwarden CLI で session を確認し、
# 指定 item から API key を取り出して `gh secret set` で repo secrets に登録する。
# Operation Model に従い、各 secret 設定の前に user 確認を取る。


def _bw_available() -> bool:
    return shutil.which("bw") is not None


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _bw_get_field(item_name: str, field: str = "api_key") -> str | None:
    """`bw get item <name>` から指定 field の値を取り出す。"""
    if not _bw_available():
        return None
    if "BW_SESSION" not in {k for k in __import__("os").environ.keys()}:
        return None
    result = subprocess.run(
        ["bw", "get", "item", item_name],
        capture_output=True, text=True, check=False, timeout=15,
    )
    if result.returncode != 0:
        return None
    import json as _json
    try:
        item = _json.loads(result.stdout)
    except _json.JSONDecodeError:
        return None
    # 1. fields[].name == field, .value で取れる場合 (custom field)
    for f in item.get("fields", []) or []:
        if f.get("name") == field:
            return f.get("value")
    # 2. login.password (default api key 保管場所)
    login = item.get("login") or {}
    if field in ("api_key", "password") and login.get("password"):
        return login["password"]
    # 3. notes (last resort)
    if field == "notes" and item.get("notes"):
        return item["notes"]
    return None


def _gh_secret_set(repo: str, key: str, value: str, dry_run: bool) -> bool:
    """secret 値を stdin 経由で `gh secret set` に渡す (ADR 0004)。

    `--body <value>` の引数渡しは process list (`ps auxww`) に値が瞬間的に出るため
    禁止 (FORBIDDEN_SECRET_PATTERNS で audit 検出)。stdin なら memory のみ。
    """
    if dry_run:
        print(f"  [dry-run] would set secret {key} on {repo}")
        return True
    result = subprocess.run(
        ["gh", "secret", "set", key, "--body-file", "-", "--repo", repo],
        input=value,
        capture_output=True, text=True, check=False, timeout=20,
    )
    if result.returncode != 0:
        print(f"  FAIL: gh secret set {key}: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def run_install_secrets(
    *,
    repo: str,
    anthropic_item: str | None = None,
    openai_item: str | None = None,
    bw_field: str = "api_key",
    dry_run: bool = False,
    yes: bool = False,
) -> int:
    """Bitwarden 経由で取得した API key を `gh secret set` で repo に登録する。

    使用者は事前に `bw unlock --raw` で `BW_SESSION` を発行しておく。
    """
    if not _bw_available():
        print(
            "Error: `bw` (Bitwarden CLI) not found. Install it first "
            "(e.g. `brew install bitwarden-cli` or `npm i -g @bitwarden/cli`).",
            file=sys.stderr,
        )
        return 2
    if not _gh_available():
        print("Error: `gh` (GitHub CLI) not found.", file=sys.stderr)
        return 2
    import os as _os
    if "BW_SESSION" not in _os.environ:
        print(
            "Error: BW_SESSION not set. Run `export BW_SESSION=$(bw unlock --raw)` "
            "and retry.",
            file=sys.stderr,
        )
        return 2

    targets: list[tuple[str, str]] = []  # (env_key, bw_item)
    if anthropic_item:
        targets.append(("ANTHROPIC_API_KEY", anthropic_item))
    if openai_item:
        targets.append(("OPENAI_API_KEY", openai_item))
    if not targets:
        print(
            "Error: pass at least one of --bw-anthropic-item / --bw-openai-item.",
            file=sys.stderr,
        )
        return 2

    print(f"==> Will register {len(targets)} secret(s) on {repo}:")
    for key, item in targets:
        print(f"  - {key} (from Bitwarden item: {item})")
    if not yes and not _confirm("\nProceed?", dry_run=dry_run):
        print("Skipped.")
        return 0

    failed = 0
    for key, item in targets:
        value = _bw_get_field(item, bw_field)
        if value is None:
            print(
                f"  FAIL: could not read Bitwarden item '{item}' field '{bw_field}'",
                file=sys.stderr,
            )
            failed += 1
            continue
        if _gh_secret_set(repo, key, value, dry_run):
            print(f"  OK: set {key} on {repo}")
        else:
            failed += 1
    return 1 if failed else 0


# ---------- pre-push hook install (PR γ, ADR 0009 / 0010 enforcement) ----------


def install_pre_push_hook(
    project: Path,
    *,
    dry_run: bool = False,
    yes: bool = False,
) -> int:
    """`<project>/.git/hooks/pre-push` を `templates/artifacts/pre-push` から copy する。

    既存 hook がある場合は上書きせず警告 + skip する (使用者が明示的に削除してから
    再実行する設計)。
    """
    git_dir = project / ".git"
    if not git_dir.exists():
        print(f"Error: not a git repository: {project}", file=sys.stderr)
        return 2
    hook_path = git_dir / "hooks" / "pre-push"
    template = (
        Path(__file__).resolve().parent.parent / "templates" / "artifacts" / "pre-push"
    )
    if not template.is_file():
        print(f"Error: hook template not found at {template}", file=sys.stderr)
        return 2
    if hook_path.exists():
        print(
            f"WARN: {hook_path} already exists. Remove it first if you want "
            "ai-ops to install ours.",
            file=sys.stderr,
        )
        return 1
    print(f"Will install pre-push hook to {hook_path}")
    print(f"  source: {template}")
    if dry_run:
        print("  [dry-run] no write performed")
        return 0
    if not yes and not _confirm("\nProceed?", dry_run=dry_run):
        print("Skipped.")
        return 0
    import shutil as _shutil
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    _shutil.copy2(template, hook_path)
    hook_path.chmod(0o755)
    print(f"  OK: installed pre-push hook at {hook_path}")
    return 0
