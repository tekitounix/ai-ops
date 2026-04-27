from __future__ import annotations

from pathlib import Path


def load_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def project_prompt(
    *,
    template: str,
    agents_md: str,
    name: str,
    purpose: str,
    tier: str,
    project_type: str,
    nix_level: str,
) -> str:
    return f"""You are creating a new project with ai-ops as the source of truth.

This is not a mechanical scaffold task. First determine the ideal shape for this project,
then propose concrete repo placement, harness, checks, Nix level, and initial files.

Follow Propose -> Confirm -> Execute:
- If the user has not already confirmed an exact proposal in this session, present the proposal and stop.
- After confirmation, create or update files directly with the tools available to you.
- Do not read or write secret values.
- Do not edit user environment files.
- Separate Fact / Inference / Risk / User decision / AI recommendation.

Operating rules (from ai-ops AGENTS.md, source of truth):

{agents_md}

Project:
- name: {name}
- purpose: {purpose}
- tier: {tier}
- project type: {project_type}
- nix level: {nix_level}

Template:
{template}
"""


def migration_prompt(
    *,
    template: str,
    agents_md: str,
    source: Path,
    tier: str,
    nix_level: str,
    evidence: str,
) -> str:
    return f"""You are migrating an existing project with ai-ops as the source of truth.

This is not a mechanical migration. Use project-specific judgment to decide the ideal
target state, then propose a concrete non-destructive migration path.

Follow Propose -> Confirm -> Execute:
- Start with read-only discovery evidence.
- If the user has not already confirmed an exact proposal in this session, present the proposal and stop.
- After confirmation, update the target project directly with the tools available to you.
- Do not read or write secret values.
- Do not request destructive operations unless they are separately justified and confirmed.
- Separate Fact / Inference / Risk / User decision / AI recommendation.

Operating rules (from ai-ops AGENTS.md, source of truth):

{agents_md}

Source: {source}
Tier: {tier}
Nix level: {nix_level}

Discovery evidence:
{evidence}

Template:
{template}
"""
