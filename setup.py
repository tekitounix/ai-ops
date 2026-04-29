"""Bundle root-level AGENTS.md + templates/ into the wheel.

pyproject.toml is the canonical declaration. This file only exists so that
non-editable `pip install` produces a self-contained package: the build_py
hook copies AGENTS.md and templates/ into ai_ops/_resources/ at build time,
which package-data then includes in the wheel. The _resources/ directory is
recreated each build and ignored by Git.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithBundledResources(build_py):
    def run(self) -> None:
        repo = Path(__file__).resolve().parent
        resources = repo / "ai_ops" / "_resources"
        if resources.exists():
            shutil.rmtree(resources)
        resources.mkdir(parents=True)
        shutil.copy(repo / "AGENTS.md", resources / "AGENTS.md")
        shutil.copytree(repo / "templates", resources / "templates")
        super().run()


setup(cmdclass={"build_py": BuildWithBundledResources})
