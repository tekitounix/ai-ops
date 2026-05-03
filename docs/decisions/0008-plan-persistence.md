# ADR 0008: Execution plan persistence

> Status: Accepted
> Date: 2026-04-29

## Context

ai-ops already keeps durable project intent in Briefs and long-lived decisions in ADRs. It does not yet have a repo-local artifact for execution-time plans: the living state an AI agent updates while implementing a non-trivial feature, migration, or refactor.

Relying on user-local AI tool storage such as `~/.claude/plans/` is not portable. Those files are outside the repository, have tool-specific naming, and cannot be reviewed by another agent or by Git history. ADR 0002 also forbids ai-ops from silently changing AI tool user-level configuration or data.

## Decision

Use repo-committed Markdown under `docs/plans/` for execution-time living plans.

```text
docs/plans/
  <slug>/
    plan.md
    tasks.md        # optional
  archive/
    YYYY-MM-DD-<slug>/
      plan.md
      tasks.md      # optional
```

`templates/plan.md` is the starting schema. A plan is appropriate for complex features, significant refactors, migrations, cross-cutting edits, or work that needs handoff between agents. Small single-turn changes do not need a plan.

Active plans live in `docs/plans/<slug>/`. Completed plans move to `docs/plans/archive/YYYY-MM-DD-<slug>/` after Verify / Adopt. Archive is recovery and archeology, not a substitute for ADRs or README updates.

`AGENTS.md` only points agents to `docs/plans/` and `templates/plan.md`; it must not accumulate per-task state.

`~/.claude/plans/`, `~/.cursor/`, `~/.codex/`, and other user-level AI data remain non-canonical. ai-ops may provide a promote helper that reads a user-selected local plan and proposes a repo-local plan, but it must not silently scan, migrate, or rewrite user-level AI storage.

## Consequences

Positive:

- Codex, Claude Code, Cursor, and other agents can share the same plan through Git.
- Long-running work can resume from the repository instead of chat history or user-local tool state.
- Active vs archived state is visible in the file tree.
- ADR 0001 stays small because transient state lives outside `AGENTS.md`.

Negative:

- Plans can rot if they are not updated during implementation.
- Plan files add process overhead for small changes.
- Archived plans may duplicate information also visible in commits; use them only when the execution record is useful.

## Rejected Options

A. Store plans only in `~/.claude/plans/`.

Rejected because this is Claude-specific, user-local, and outside Git review.

B. Put the current plan directly in `AGENTS.md`.

Rejected because ADR 0001 requires `AGENTS.md` to remain short and free of transient task state.

C. Adopt GitHub Spec Kit or OpenSpec as the full project workflow.

Rejected for now because ai-ops already has Briefs, ADRs, Nix audit, harness audit, and migration flow. A lightweight `docs/plans/` layer covers the missing execution-time artifact without importing a larger orchestrator.

D. Use a numeric TTL that deletes old plans automatically.

Rejected because deletion hides useful archeology and can conflict with recovery. ai-ops may warn on old active plans, but completion is represented by moving a plan to `docs/plans/archive/YYYY-MM-DD-<slug>/`.

## Verification

Adoption is verified by:

```sh
python -m ai_ops check
git diff --check
```

When Nix is available:

```sh
direnv exec . sh -c '
set -e
nix flake check --all-systems --no-build
nix build --no-link ".#checks.$(nix eval --impure --raw --expr builtins.currentSystem).all"
'
```

## Related

- ADR 0001: AGENTS.md primary
- ADR 0002: portability first
- ADR 0006: AI-first project lifecycle
- ADR 0007: Python canonical CLI
- `templates/plan.md`

## Amendment 2026-05-03 (PR θ): Backlog の導入

### Context

各 plan の `Improvement Candidates` で `deferred` 判定された候補は、plan が archive されると忘れ去られる構造だった。「次の PR で対応」とだけ書かれた残課題が active plan を膨張させ、順序最適化 (今やめて後でやる) の退避場所も無かった。

### Decision

`docs/plans/backlog.md` を 1 ファイル新設し、deferred / Cancelled 候補の集約場所とする。

### 構造

- **High** — 近 1-2 PR で着手したい
- **Medium** — 落ち着いたら
- **Low** — 見直し材料、参考
- **Cancelled / Deferred** — 履歴 (理由付きで strikethrough、再評価で active に戻す場合は新 entry として High/Medium に追加)

### 遷移

```text
[active plan の Improvement Candidates]
       │ deferred 判定
       ▼
[backlog.md High/Medium/Low]
       │ 新 plan 起草で pick
       ▼
[active plan の Plan of Work]
       │ 完了
       ▼
[archive]
```

### 運用ルール

1. **Backlog → active plan**: 新 plan 起草時、backlog から 1-3 candidate を pick。pick した candidate は backlog から削除 (Cancelled に履歴を残したい場合は strikethrough)。
2. **Active plan → Backlog**: plan の Improvement Candidates で `deferred` と判定したものは、archive 前に backlog の適切な priority section に転記する。出所として plan slug を明記。
3. **3-deferred 閾値**: 同じ candidate が 3 plan 連続で deferred のまま動かなければ、High → Medium → Low → Cancelled の降格を検討する (本 ADR 本体の Improvement Capture loop 3-deferred 閾値と一貫)。
4. **Cancelled の不可逆性**: Cancelled は履歴。再評価で active に戻す場合は新 entry として追加し、Cancelled の strikethrough は残す。

### Enforcement

- `audit lifecycle` の REQUIRED_FILES に `docs/plans/backlog.md` を追加 (存在のみ)。
- `templates/plan.md` の Improvement Candidates Enum reference に「`deferred` 判定時は backlog.md への転記必須」を明記。
- 機械的な hygiene check (Cancelled section が空、出所未記載 等) は本 PR では実装しない (over-engineering 回避、規律 + 監査ファイル存在の 2 段で運用開始)。
