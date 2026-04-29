# Migration Brief

> Purpose: 既存プロジェクトを project-specific に移行するための brief。
> Rule: read-only discovery を先に行う。secret value は読まない、書かない。

## 1. Source Project Summary

- Source path:
- Current repo status:
- Remote:
- Current purpose:
- Primary stack:
- Last activity:

## 2. Claim Classification

| Class | 内容 |
|---|---|
| Fact |  |
| Inference |  |
| Risk |  |
| User decision |  |
| AI recommendation |  |

## 3. Discovery Evidence

- Files read:
- Commands run:
- Test/build entrypoints observed:
- Existing AI config:
- Secret/PII indicators:
- Related projects:

## 4. Recommended Target State

- Keep / split / merge:
- Target path:
- Host/owner:
- Visibility:
- Tier:
- Rationale:

## 5. Harness Plan

- AGENTS.md / CLAUDE.md strategy:
- Existing AI config preserve / replace:
- Check command strategy:
- Secret hygiene:
- Nix decision: <preserve-existing|amend|replace|adopt-new|opt-out>
- Nix level: <auto|none|devshell|apps|full> (default `auto` → rubric で解決)
- Nix なし justification: (opt-out 時のみ必須、Stage A exit or score < 0 の理由)
- Rubric output (JSON): {"stage_a_exit": null, "stack_hint": "...", "recommended_level": "...", "score": 0, "confidence": "..."}
- Lockfile cadence: <renovate|dependabot|update-flake-lock|preserve-existing|none>
- Existing lockfile tooling: <renovate|dependabot|update-flake-lock|none> (discovery から)
- Tool-specific settings:
- Language strategy (code / docs / public-facing):

## 6. Files

- Preserve:
- Avoid:
- Rename/move:
- Archive:
- Generate:

## 7. AI History Plan

- Tool history detected:
- Dry-run command:
- Migration choice:
- User confirmation required:

## 8. Execution Plan

- Commands to run:
- Copy strategy:
- Manual edits:
- Stop points:
- Destructive operations:
- Rollback plan:

## 9. Verification Plan

- ai-ops checks:
- Project checks:
- Nix checks:
- Smoke/manual checks:
- Known unverified items:

## 10. Open Decisions

| Decision | Options | Recommendation | Required before |
|---|---|---|---|
|  |  |  |  |
