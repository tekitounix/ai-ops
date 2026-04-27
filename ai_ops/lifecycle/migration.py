from __future__ import annotations

from pathlib import Path

from ai_ops.lifecycle.prompts import load_template, migration_prompt
from ai_ops.models import MigrationSpec
from ai_ops.paths import template_path
from ai_ops.process import run


def discovery(source: Path) -> str:
    lines: list[str] = []
    lines.append(f"source_exists: {source.exists()}")
    lines.append(f"source_is_dir: {source.is_dir()}")
    if source.is_dir():
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
    return "\n".join(lines)


def build_migration_prompt(spec: MigrationSpec, *, root: Path) -> str:
    template = load_template(template_path("migration-brief.md", root=root))
    agents_md = (root / "AGENTS.md").read_text(encoding="utf-8")
    return migration_prompt(
        template=template,
        agents_md=agents_md,
        source=spec.source,
        tier=spec.tier,
        nix_level=spec.nix_level,
        evidence=discovery(spec.source),
    )
