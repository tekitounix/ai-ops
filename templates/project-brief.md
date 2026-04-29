# Project Brief

> Purpose: 新規プロジェクトを AI-first に開始するための brief。
> Rule: secret value、credential、customer data、production token は書かない。

## 1. Summary

- Project name:
- One-line purpose:
- Primary users:
- Initial milestone:

## 2. Claim Classification

| Class | 内容 |
|---|---|
| Fact |  |
| Inference |  |
| Risk |  |
| User decision |  |
| AI recommendation |  |

## 3. Scope

- Goals:
- Non-goals:
- Standalone / part of existing system:
- Related projects:

## 4. Repo Placement and Tier

- Host:
- Owner:
- Repo path:
- Visibility:
- Tier:
- Project type:
- Rationale:

## 5. Stack Decision

- Language/runtime:
- Framework:
- Package manager:
- Database/storage:
- External services:
- Rationale:

## 6. Data and Secrets

- Data handled:
- PII/customer data:
- Secrets required:
- Secret source of truth:
- Files AI must not read:

## 7. AI Operating Rules

- AI may edit:
- AI must ask before editing:
- AI must not edit:
- Required checks before reporting done:
- Destructive operations policy:
- Language strategy (code / docs / public-facing):

## 8. Initial Files

- AGENTS.md / CLAUDE.md strategy:
- README strategy:
- Check command strategy:
- .gitignore / secret hygiene:
- Nix level: <auto|none|devshell|apps|full> (default `auto` → rubric で解決)
- Nix なし justification: (Nix level: none を選ぶ場合のみ必須、Stage A exit or score < 0 の理由)
- Rubric output (JSON): {"stage_a_exit": null, "stack_hint": "...", "recommended_level": "...", "score": 0, "confidence": "..."}
- Lockfile cadence: <renovate|dependabot|update-flake-lock|none> (default: T1/T2 GitHub project は renovate、それ以外は update-flake-lock fallback。`none` は justification 必須)

## 9. Execution Plan

- Commands to run:
- Files to create:
- Files to customize after scaffold:
- Confirmation needed:

## 10. Verification Plan

- Syntax/lint:
- Typecheck:
- Tests:
- Build:
- Smoke/manual checks:
- Known unverified items:

## 11. Open Decisions

| Decision | Options | Recommendation | Required before |
|---|---|---|---|
|  |  |  |  |
