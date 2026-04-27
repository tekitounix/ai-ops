from __future__ import annotations

from pathlib import Path


def repo_root(start: Path | None = None) -> Path | None:
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "templates").is_dir():
            return candidate
    return None


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def template_path(*parts: str, root: Path | None = None) -> Path:
    return (root or package_root()) / "templates" / Path(*parts)
