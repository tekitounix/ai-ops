from __future__ import annotations

import os
from pathlib import Path


def repo_root(start: Path | None = None) -> Path | None:
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "templates").is_dir():
            return candidate
    return None


def package_root() -> Path:
    """Locate the directory containing AGENTS.md + templates/.

    Resolution order:
    1. $AI_OPS_PACKAGE_ROOT  (set by `nix run` so the flake's source tree
       reaches paths.py without changing $PWD).
    2. ai_ops/../            (editable install or running from source clone).
    3. ai_ops/_resources/    (wheel install: bundled by setup.py at build time).

    Checking the source-tree parent before bundled resources keeps local
    development honest even when ignored build artifacts from a previous wheel
    build are present. Bundled resources still make `pip install ai-ops`
    (non-editable) self-contained because site-packages has no repo-root
    AGENTS.md / templates/. (1) handles `nix run` without hijacking the user's
    cwd.
    """
    env = os.environ.get("AI_OPS_PACKAGE_ROOT")
    if env:
        envp = Path(env)
        if (envp / "AGENTS.md").is_file() and (envp / "templates").is_dir():
            return envp
    here = Path(__file__).resolve().parent
    source_root = here.parent
    if (source_root / "AGENTS.md").is_file() and (source_root / "templates").is_dir():
        return source_root
    bundled = here / "_resources"
    if (bundled / "AGENTS.md").is_file() and (bundled / "templates").is_dir():
        return bundled
    return source_root


def template_path(*parts: str, root: Path | None = None) -> Path:
    return (root or package_root()) / "templates" / Path(*parts)
