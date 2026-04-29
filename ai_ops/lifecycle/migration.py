from __future__ import annotations

from pathlib import Path

from ai_ops.lifecycle.prompts import load_template, migration_prompt
from ai_ops.models import MigrationSpec
from ai_ops.paths import template_path
from ai_ops.process import run


_STACK_HINT_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # (stack_hint, marker filenames)
    ("xmake", ("xmake.lua",)),
    ("cmake", ("CMakeLists.txt",)),
    ("node", ("package.json", "pnpm-lock.yaml", "bun.lockb")),
    ("python", ("pyproject.toml", "uv.lock", "requirements.txt", "Pipfile")),
    ("rust", ("Cargo.toml",)),
    ("go", ("go.mod",)),
    ("dsl", (".ato",)),  # atopile etc — extension match
)
_DOC_EXTS = {".md", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".svg", ".csv"}


def _classify_stack(top_names: list[str]) -> str:
    """Return stack_hint from top-level file names."""
    lower = {name.lower() for name in top_names}
    for hint, markers in _STACK_HINT_MARKERS:
        for marker in markers:
            if marker.startswith("."):
                # extension match
                if any(name.endswith(marker) for name in lower):
                    return hint
            elif marker in lower:
                return hint
    return "unknown"


def _is_docs_only(top_names: list[str]) -> bool:
    """True when all top-level files are docs/media (= no executable stack)."""
    if not top_names:
        return False
    for name in top_names:
        if name.startswith("."):
            continue  # skip dotfiles for this heuristic
        ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        if ext not in _DOC_EXTS:
            return False
    return True


def discovery(source: Path) -> str:
    """Read-only discovery + rubric inputs (ADR 0005 amendment 2026-04-29)."""
    lines: list[str] = []
    lines.append(f"source_exists: {source.exists()}")
    lines.append(f"source_is_dir: {source.is_dir()}")
    if not source.is_dir():
        return "\n".join(lines)

    for command in (
        ["git", "-C", str(source), "status", "--short"],
        ["git", "-C", str(source), "log", "-1", "--format=%ai %s"],
        ["git", "-C", str(source), "remote", "-v"],
    ):
        result = run(command, cwd=source, check=False)
        lines.append(f"$ {' '.join(command)}")
        lines.append(result.stdout.strip() or result.stderr.strip() or "<no output>")

    top_files = sorted(path.name for path in source.iterdir())[:40]
    lines.append("top_level_files: " + ", ".join(top_files))
    secret_names = [
        path.name
        for path in source.iterdir()
        if any(marker in path.name.lower() for marker in ("secret", "token", ".env", ".key", ".pem"))
    ]
    lines.append("secret_looking_names: " + (", ".join(secret_names) if secret_names else "none"))

    # === Rubric inputs (ADR 0005 amendment 2026-04-29) ===
    lines.append("")
    lines.append("# Rubric inputs (Stage A/B/C signals for Nix fitness)")

    flake = source / "flake.nix"
    envrc = source / ".envrc"
    lines.append(f"existing_flake: {flake.is_file()}")
    lines.append(f"existing_envrc: {envrc.is_file()}")

    stack_hint = _classify_stack(top_files)
    lines.append(f"stack_hint: {stack_hint}")
    lines.append(f"docs_only: {_is_docs_only(top_files)}")

    # git stats (read-only)
    first_commit = run(
        ["git", "-C", str(source), "log", "--format=%ai", "--reverse"],
        cwd=source,
        check=False,
    )
    last_commit = run(
        ["git", "-C", str(source), "log", "-1", "--format=%ai"],
        cwd=source,
        check=False,
    )
    authors = run(
        ["git", "-C", str(source), "log", "--format=%ae"],
        cwd=source,
        check=False,
    )
    first_line = first_commit.stdout.strip().splitlines()[0] if first_commit.stdout.strip() else ""
    last_line = last_commit.stdout.strip()
    unique_authors = len(set(authors.stdout.strip().splitlines())) if authors.stdout.strip() else 0
    lines.append(f"git_first_commit_date: {first_line or '<none>'}")
    lines.append(f"git_last_commit_date: {last_line or '<none>'}")
    lines.append(f"unique_authors: {unique_authors}")

    tracked = run(
        ["git", "-C", str(source), "ls-files"],
        cwd=source,
        check=False,
    )
    tracked_count = len(tracked.stdout.strip().splitlines()) if tracked.stdout.strip() else 0
    lines.append(f"tracked_file_count: {tracked_count}")

    ci_present = (source / ".github" / "workflows").is_dir()
    lines.append(f"ci_present: {ci_present}")

    tests_present = any(
        (source / d).is_dir() for d in ("tests", "test", "__tests__")
    ) or any(
        (source / f).is_file() for f in ("pytest.ini", "vitest.config.js", "vitest.config.ts", "jest.config.js")
    )
    lines.append(f"tests_present: {tests_present}")

    vendor_signals = any((source / d).is_dir() for d in ("vendor", "third_party", "tools/sdk"))
    lines.append(f"vendor_signals: {vendor_signals}")

    # Lockfile cadence signals (Phase 8-A): existing dependency drift tooling
    existing_renovate = (source / "renovate.json").is_file() or (source / ".renovaterc.json").is_file()
    existing_dependabot = (source / ".github" / "dependabot.yml").is_file()
    existing_update_flake_lock = (source / ".github" / "workflows" / "update-flake-lock.yml").is_file()
    lines.append(f"existing_renovate: {existing_renovate}")
    lines.append(f"existing_dependabot: {existing_dependabot}")
    lines.append(f"existing_update_flake_lock: {existing_update_flake_lock}")

    return "\n".join(lines)


def build_migration_prompt(
    spec: MigrationSpec,
    *,
    root: Path,
    retrofit_nix: bool = False,
) -> str:
    template = load_template(template_path("migration-brief.md", root=root))
    agents_md = (root / "AGENTS.md").read_text(encoding="utf-8")
    return migration_prompt(
        template=template,
        agents_md=agents_md,
        source=spec.source,
        tier=spec.tier,
        nix_level=spec.nix_level,
        evidence=discovery(spec.source),
        retrofit_nix=retrofit_nix,
    )
