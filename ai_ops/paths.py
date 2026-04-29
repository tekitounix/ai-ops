from __future__ import annotations

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
    1. ai_ops/_resources/  (wheel install: bundled by setup.py at build time)
    2. ai_ops/../          (editable install or running from source clone)

    Falling back to (2) is what makes `pip install -e .` and `python -m ai_ops`
    from a clone work. (1) is what makes `pip install ai-ops` (non-editable)
    work, since AGENTS.md and templates/ live outside the ai_ops package source
    in the repo and would not otherwise reach the wheel.
    """
    here = Path(__file__).resolve().parent
    bundled = here / "_resources"
    if (bundled / "AGENTS.md").is_file() and (bundled / "templates").is_dir():
        return bundled
    return here.parent


def template_path(*parts: str, root: Path | None = None) -> Path:
    return (root or package_root()) / "templates" / Path(*parts)
