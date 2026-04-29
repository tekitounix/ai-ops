from __future__ import annotations

from pathlib import Path


def load_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# Rubric block — both new and migration prompts reference this per ADR 0005 amendment.
NIX_RUBRIC = """
Nix adoption rubric (ADR 0005 amended 2026-04-29):

Nix flake は default-required reproducibility layer。AI agent は brief を作る際に以下の
Stage A/B/C を順に評価し、`Nix level:` field の推奨値を決める。

Stage A — hard gates (early exit):
  - archive (last commit > 18mo, no PR)             → none
  - scratch (~/scratch/, no remote, < 5 file)        → none
  - docs-only (md/pdf/png のみ)                       → none / minimal
  - existing flake                                    → preserve / amend
  - vendor too closed (GUI installer / dongle)        → devshell with vendor outside closure
  - upstream fork (other-org remote, mostly upstream) → none

Stage B — stack-aware default (Stage A 通過時):
  - xmake.lua / CMakeLists.txt (組込み)              → devshell + flake.nix.xmake
  - 商用 SDK / vendor binary                          → devshell + overlay (flake.nix.xmake 派生)
  - package.json / pnpm-lock.yaml / bun.lockb         → devshell + flake.nix.node
  - pyproject.toml / uv.lock / requirements.txt       → devshell + flake.nix.python
  - Cargo.toml / go.mod                               → devshell + flake.nix.python 派生
  - DSL (*.ato 等)                                    → devshell minimal + flake.nix.minimal

Stage C — score adjustment:
  Pros (+1〜+3): toolchain volatility / multi-developer / CI imperative steps /
                long-term maintenance / external contributor / release artifact /
                vendor binary / AI session 高頻度 / sandbox 需要 / tests / activity / LOC > 500
  Cons (−1〜−5): dormant / scratch / docs-only / throwaway / system-tool only /
                vendor too closed / tiny project / single binary / strong existing repro
                layer / stale-not-archive / many top-level memo files
  Score ≥ +6 → promote (devshell → apps)
  Score +2〜+5 → keep
  Score 0〜+1 → borderline (brief で flag)
  Score < 0 → demote to none (justification 必須)

Stage A signal は discovery evidence の `existing_flake` / `docs_only` / `stack_hint`
等から取得。`Nix level: none` を選ぶ場合は brief §「Nix なし justification:」を埋める。
template variant は `templates/artifacts/flake.nix.{minimal,node,python,xmake}` を copy 起点。
"""


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
- nix level: {nix_level} (= 'auto' のとき rubric で決定。下記参照)

{NIX_RUBRIC}

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
    retrofit_nix: bool = False,
    update_harness: bool = False,
) -> str:
    if update_harness:
        scope_directive = (
            "**SCOPE: Harness drift remediation only (Phase 8-B).** This project is already "
            "ai-ops managed. Use the `Harness drift` evidence below to add missing files, "
            "update modified ones to current ai-ops standard, and refresh `.ai-ops/harness.toml`. "
            "Do NOT change project source code, AGENTS.md content beyond ai-ops template "
            "alignment, or brief structure. Brief filename suggestion: "
            "docs/brief-YYYYMMDD-harness-update.md.\n\n"
        )
    elif retrofit_nix:
        scope_directive = (
            # Retrofit-narrow: 既管理 project に flake.nix のみ追加する scope
            "**SCOPE: Nix retrofit only.** This project is already ai-ops managed. "
            "Do NOT change AGENTS.md / brief / harness scope beyond adding flake.nix + .envrc + "
            "lock. Brief filename suggestion: docs/brief-YYYYMMDD-nix-retrofit.md.\n\n"
        )
    else:
        scope_directive = ""
    return f"""You are migrating an existing project with ai-ops as the source of truth.

{scope_directive}This is not a mechanical migration. Use project-specific judgment to decide the ideal
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
Nix level: {nix_level} (= 'auto' のとき rubric で決定。下記参照)

Discovery evidence (rubric inputs を含む):
{evidence}

{NIX_RUBRIC}

Template:
{template}
"""
