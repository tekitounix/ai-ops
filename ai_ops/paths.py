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
    2. ai_ops/_resources/    (wheel install: bundled by setup.py at build time).
    3. ai_ops/../            (editable install or running from source clone).

    Falling back to (3) is what makes `pip install -e .` and `python -m ai_ops`
    from a clone work. (2) is what makes `pip install ai-ops` (non-editable)
    work, since AGENTS.md and templates/ live outside the ai_ops package
    source in the repo and would not otherwise reach the wheel. (1) handles
    `nix run` without hijacking the user's cwd.
    """
    env = os.environ.get("AI_OPS_PACKAGE_ROOT")
    if env:
        envp = Path(env)
        if (envp / "AGENTS.md").is_file() and (envp / "templates").is_dir():
            return envp
    here = Path(__file__).resolve().parent
    bundled = here / "_resources"
    if (bundled / "AGENTS.md").is_file() and (bundled / "templates").is_dir():
        return bundled
    return here.parent


def template_path(*parts: str, root: Path | None = None) -> Path:
    return (root or package_root()) / "templates" / Path(*parts)
