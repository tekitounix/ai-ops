"""Canonical schema constants shared across ai-ops audits.

This module exists to keep schema knowledge in one place so that
`audit lifecycle` (ai-ops self-audit) and `audit projects` (managed
projects policy drift detection) cannot drift apart in their
expectations.

Constants are read-only data; any policy/detector logic stays in the
audit module that owns the signal.
"""

from __future__ import annotations


# Top-level Markdown headings (`^## ...`) that every canonical execution
# plan must include. Source of truth is `templates/plan.md`. Update both
# in lockstep when the plan schema evolves.
REQUIRED_PLAN_SECTIONS: tuple[str, ...] = (
    "Purpose / Big Picture",
    "Progress",
    "Surprises & Discoveries",
    "Decision Log",
    "Outcomes & Retrospective",
    "Improvement Candidates",
    "Context and Orientation",
    "Plan of Work",
    "Concrete Steps",
    "Validation and Acceptance",
    "Idempotence and Recovery",
    "Artifacts and Notes",
    "Interfaces and Dependencies",
)


# Repository-relative paths whose changes are considered "propagation
# relevant" — i.e., a change to one of these paths in ai-ops is a
# candidate for surfacing as policy drift in managed projects.
#
# Path-based heuristic is deliberately permissive (false-positives are
# bounded — a wasted realignment cycle — while false-negatives would be
# silent drift). Author-driven `[propagate]` tags can refine this in the
# future but are not required.
CANONICAL_LIFECYCLE_PATHS: tuple[str, ...] = (
    "AGENTS.md",
    "templates/plan.md",
    "templates/project-brief.md",
    "templates/migration-brief.md",
    "templates/agent-handoff.md",
    "docs/ai-first-lifecycle.md",
    "docs/self-operation.md",
    "docs/realignment.md",
    "docs/projects-audit.md",
    "docs/project-addition-and-migration.md",
    "docs/project-relocation.md",
)


# Directory prefix matched in addition to the explicit paths above.
# Any change under this prefix is propagation-relevant (ADRs are
# load-bearing by definition).
CANONICAL_LIFECYCLE_DIR_PREFIXES: tuple[str, ...] = (
    "docs/decisions/",
)


def required_plan_section_set() -> frozenset[str]:
    """Return REQUIRED_PLAN_SECTIONS as a frozenset for set-comparison use."""
    return frozenset(REQUIRED_PLAN_SECTIONS)
