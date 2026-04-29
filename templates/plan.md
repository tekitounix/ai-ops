# <Short, action-oriented plan title>

This ExecPlan is a living document. Keep `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` current as work proceeds.

Plan path: `docs/plans/<slug>/plan.md`. Archive path after adoption: `docs/plans/archive/YYYY-MM-DD-<slug>/`.

## Purpose / Big Picture

Explain what someone can do after this change that they could not do before. State the user-visible or operator-visible outcome and how to observe it working.

## Progress

- [ ] (YYYY-MM-DD HH:MMZ) Initial plan drafted.

## Surprises & Discoveries

- Observation: TBD.
  Evidence: TBD.

## Decision Log

- Decision: TBD.
  Rationale: TBD.
  Date/Author: YYYY-MM-DD / TBD.

## Outcomes & Retrospective

TBD. At completion, summarize what shipped, what remains, and what should change in future plans.

## Context and Orientation

Describe the current state relevant to this task as if the reader has only the current working tree and this plan. Name repository-relative files and commands. Define any non-obvious terms.

## Plan of Work

Describe the sequence of edits and additions in prose. For each meaningful change, name the file or module and the intended behavioral effect.

## Concrete Steps

List exact commands to run from the repository root and the expected signals. Keep steps idempotent where possible.

## Validation and Acceptance

State the checks to run and what success looks like. Include project-specific tests, audits, or manual verification. Mark unverifiable claims explicitly as not verified.

## Idempotence and Recovery

Explain whether the steps can be repeated safely. If a step is risky or can fail halfway, describe how to retry, roll back, or inspect the diff before continuing.

## Artifacts and Notes

Include concise transcripts, diffs, links, PRs, or issue references that prove progress. Keep this section focused on evidence, not chat history.

## Interfaces and Dependencies

Name any public interfaces, CLI commands, file formats, dependencies, or cross-repo contracts that must exist when the plan is complete.
