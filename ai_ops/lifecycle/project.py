from __future__ import annotations

from pathlib import Path

from ai_ops.lifecycle.prompts import load_template, project_prompt
from ai_ops.models import ProjectSpec
from ai_ops.paths import template_path


def build_project_prompt(spec: ProjectSpec, *, root: Path) -> str:
    template = load_template(template_path("project-brief.md", root=root))
    agents_md = (root / "AGENTS.md").read_text(encoding="utf-8")
    return project_prompt(
        template=template,
        agents_md=agents_md,
        name=spec.name,
        purpose=spec.purpose,
        tier=spec.tier,
        project_type=spec.project_type,
        nix_level=spec.nix_level,
    )


def draft_project_brief(spec: ProjectSpec) -> str:
    return f"""# Project Brief

> Purpose: 新規プロジェクトを AI-first に開始するための brief。
> Rule: secret value、credential、customer data、production token は書かない。

## 1. Summary

- Project name: {spec.name}
- One-line purpose: {spec.purpose}
- Primary users: TBD
- Initial milestone: TBD

## 2. Claim Classification

| Class | 内容 |
|---|---|
| Fact | User requested project `{spec.name}` |
| Inference | Purpose suggests: {spec.purpose} |
| Risk | TBD |
| User decision | Confirm repo visibility, stack, and first milestone |
| AI recommendation | Start with the smallest verifiable scaffold |

## 3. Scope

- Goals: TBD
- Non-goals: TBD
- Standalone / part of existing system: TBD
- Related projects: TBD

## 4. Repo Placement and Tier

- Host: local
- Owner: <username>
- Repo path: $HOME/ghq/local/<username>/{spec.name}
- Visibility: local only
- Tier: {spec.tier}
- Project type: {spec.project_type}
- Rationale: TBD

## 5. Stack Decision

- Language/runtime: TBD
- Framework: TBD
- Package manager: TBD
- Database/storage: TBD
- External services: TBD
- Rationale: TBD

## 6. Data and Secrets

- Data handled: TBD
- PII/customer data: TBD
- Secrets required: TBD
- Secret source of truth: TBD
- Files AI must not read: .env, *.key, *.pem, secrets/

## 7. AI Operating Rules

- AI may edit: TBD
- AI must ask before editing: destructive operations, visibility changes, secret handling
- AI must not edit: user environment files
- Required checks before reporting done: ai-ops check
- Destructive operations policy: Propose -> Confirm -> Execute
- Language strategy (code / docs / public-facing): English by default; record project-specific exceptions

## 8. Initial Files

- AGENTS.md / CLAUDE.md strategy: minimal AGENTS.md with CLAUDE.md adapter if needed
- README strategy: describe purpose and first milestone
- check strategy: project-specific command, no false green
- .gitignore / secret hygiene: ADR 0004 patterns
- Nix level: {spec.nix_level} (= 'auto' のとき AI が rubric で決定、ADR 0005 amended 2026-04-29)
- Nix なし justification: (Nix level: none を選ぶ場合のみ必須、Stage A exit or score < 0 の理由)
- Rubric output (JSON): {{"stage_a_exit": null, "stack_hint": "...", "recommended_level": "...", "score": 0, "confidence": "..."}}
- Lockfile cadence: T1/T2 GitHub projects should prefer renovate; otherwise update-flake-lock fallback

## 9. Execution Plan

- Commands to run: AI agent proposes exact commands and target paths, then executes after confirmation
- Files to create: AGENTS.md, README.md, check entrypoint, .gitignore
- Files to customize after scaffold: project-specific check
- Confirmation needed: yes

## 10. Verification Plan

- Syntax/lint: TBD
- Typecheck: TBD
- Tests: TBD
- Build: TBD
- Smoke/manual checks: TBD
- Known unverified items: TBD

## 11. Open Decisions

| Decision | Options | Recommendation | Required before |
|---|---|---|---|
| Stack | TBD | Choose the smallest stack that proves the first milestone | execution |
"""
