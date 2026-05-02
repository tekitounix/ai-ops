from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path


SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_slug(slug: str) -> str | None:
    if not SLUG_RE.fullmatch(slug):
        return "slug must match [A-Za-z0-9][A-Za-z0-9._-]*"
    if ".." in slug:
        return "slug must not contain '..'"
    return None


def default_claude_plan_path(slug: str) -> Path:
    return Path.home() / ".claude" / "plans" / f"{slug}.md"


def build_promoted_plan(
    *,
    slug: str,
    source_path: Path,
    source_text: str,
    now: datetime | None = None,
) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%MZ")
    date = stamp[:10]
    title = _first_markdown_heading(source_text) or slug.replace("-", " ").replace("_", " ")
    source_rel = str(source_path.expanduser())
    indented_source = _indent_block(source_text.rstrip() or "(empty source plan)")

    return f"""# {title}

This ExecPlan is a living document. Keep `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` current as work proceeds.

Plan path: `docs/plans/{slug}/plan.md`. Archive path after adoption: `docs/plans/archive/{date}-{slug}/`.

Branch: `feat/{slug}` (default; pick `fix`/`chore`/`docs`/`refactor` if more appropriate).
Worktree: `../<repo-name>.{slug}/` when parallel isolation is wanted (created via `ai-ops worktree-new {slug}`); `n/a` for trivial single-commit work.

## Purpose / Big Picture

Promote a user-local AI plan into a repo-local, tool-agnostic execution plan so future agents can resume from Git-tracked context instead of tool-specific storage.

## Progress

- [ ] ({stamp}) Review the promoted source plan and replace TBD fields with project-specific execution detail.

## Surprises & Discoveries

- Observation: Source plan was promoted from `{source_rel}`.
  Evidence: See `Artifacts and Notes`.

## Decision Log

- Decision: Promote `{source_rel}` into `docs/plans/{slug}/plan.md`.
  Rationale: Repo-local Markdown is portable across AI tools and reviewable through Git; user-local AI plan storage is not canonical.
  Date/Author: {stamp} / ai-ops promote-plan.

## Outcomes & Retrospective

TBD. At completion, summarize what shipped, what remains, and whether the promoted source plan was accurate enough to guide execution.

## Improvement Candidates

Capture each non-obvious learning that could improve future operation. Triage before completion: adopt the high-value ones into durable artifacts (docs / ADR / templates / audit / harness / tests), defer the rest with a reason. Cross-cutting or destructive adoption requires Propose -> Confirm -> Execute. If nothing surfaced this pass, write `### (none this pass)`.

### <candidate name>

- Observation: <fact learned during the work>
- Evidence: <file / command / output reference>
- Recommended adoption target: <current-plan | durable-doc | adr | template | audit | harness | test | deferred | rejected>
- Confirmation needed: <yes | no> — <reason>
- Verification: <how adoption will be checked / `n/a`>
- Disposition: <open | adopted | deferred | rejected | superseded> — <short reason or reference>

## Context and Orientation

This plan was generated from a user-selected local AI plan. Treat the source content below as input material, not as already-approved repository policy. Re-read the current working tree before executing.

## Plan of Work

TBD. Convert the source plan into concrete repository-relative edits, milestones, and validation steps before implementation begins.

## Concrete Steps

TBD. List exact commands to run from the repository root and the expected signals.

## Validation and Acceptance

TBD. Include `python -m ai_ops check`, `git diff --check`, and any project-specific checks when relevant.

## Idempotence and Recovery

TBD. Describe how to retry, inspect the diff, or roll back if implementation diverges from this plan.

## Artifacts and Notes

Source plan copied from `{source_rel}`:

{indented_source}

## Interfaces and Dependencies

TBD. Name any CLI commands, file formats, public interfaces, or cross-repo contracts that this plan changes.
"""


def run_promote_plan(
    *,
    root: Path,
    slug: str,
    source: Path | None,
    dry_run: bool,
) -> int:
    slug_error = validate_slug(slug)
    if slug_error:
        print(f"Error: {slug_error}")
        return 2

    source_path = (source or default_claude_plan_path(slug)).expanduser().resolve()
    target = root / "docs" / "plans" / slug / "plan.md"

    if not source_path.is_file():
        print(f"Error: source plan not found: {source_path}")
        return 1
    if target.exists():
        print(f"Error: target plan already exists: {target.relative_to(root)}")
        return 1

    source_text = source_path.read_text(encoding="utf-8")
    draft = build_promoted_plan(slug=slug, source_path=source_path, source_text=source_text)

    print("==> promote-plan proposal")
    print(f"  source: {source_path}")
    print(f"  target: {target.relative_to(root)}")
    print("  action: write repo-local ExecPlan from user-selected local AI plan")
    print()
    print(draft)

    if dry_run:
        print("==> dry run: no files written")
        return 0

    confirmation = input(f"Type 'promote {slug}' to write {target.relative_to(root)}: ").strip()
    if confirmation != f"promote {slug}":
        print("Aborted: confirmation did not match.")
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(draft, encoding="utf-8")
    print(f"Wrote plan: {target.relative_to(root)}")
    return 0


def _first_markdown_heading(text: str) -> str | None:
    for line in text.splitlines():
        match = re.fullmatch(r"\s*#\s+(.+?)\s*", line)
        if match:
            return match.group(1)
    return None


def _indent_block(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.splitlines())
