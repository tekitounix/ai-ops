# Agent Handoff

> Purpose: fresh AI session または別 AI agent に、現在の作業を安全に引き継ぐ。
> Rule: この handoff は secret や credential を含めない。

## 0. Binding (ADR 0010)

- Plan path: `docs/plans/<slug>/plan.md`
- Branch: `<type>/<slug>`
- Worktree: `../<repo-name>.<slug>/` (sibling layout)

## 1. First Read

Read these files first:

- `AGENTS.md`
- `docs/operation.md` (master 運用ガイド、AI ワークフロー 14 step + 5 戦略 + 責任分界表)
- Relevant plan: (path above)
- Relevant brief:

## 2. Current Scope

- User request:
- Approved scope:
- Not approved:
- Current phase:

## 3. Current State

- Git status summary:
- Files changed:
- Files intentionally untouched:
- External/user environment changes:
- Nix state: <flake exists / level / last lock date>
- Reproducibility tool: <nix-flake|none|other>

## 4. Commands Already Run

```sh
# command
```

Result summary:

- Passed:
- Failed:
- Skipped:
- Warnings:

## 5. Next Safe Actions

1. TBD
2. TBD
3. TBD

## 6. Do Not Do

- Do not edit user environment files unless the user explicitly approves a specific operation.
- Do not read or expose secret values.
- Do not run destructive operations without Propose -> Confirm -> Execute.
- Do not replace project-specific harness files without an approved brief.

## 7. Open Questions

| Question | Recommendation | Blocking? |
|---|---|---|
|  |  |  |
