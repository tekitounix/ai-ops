# ADR 0006: AI-first project lifecycle

> Status: Accepted
> Date: 2026-04-27

## Context

ai-ops は「万能 scaffold」ではない。新規プロジェクトの最初の repo 形状は product intent、機密境界、検証方法、AI operating rules に依存する。既存プロジェクトの移行は機械的には決められない。したがって ai-ops の中心は「AI agent が project-specific な brief を作り、user の確認後に project-specific に実行する lifecycle」である。

## Decision

ai-ops の canonical workflow を次に定める。

```text
Intake -> Discovery -> Brief -> Proposal -> Confirm -> Agent Execute -> Verify -> Adopt
```

非自明な新規作成と既存移行では、AI agent は先に brief を作る:

- 新規 project: `templates/project-brief.md`
- 既存 migration: `templates/migration-brief.md`
- fresh session / 別 agent 引き継ぎ: `templates/agent-handoff.md`

brief は必ず Fact / Inference / Risk / User decision / AI recommendation を分ける。user が承認した後、AI agent が通常の開発ツールで実行する。

## Roles

| 担い手 | 役割 |
|---|---|
| User | 事業判断、公開範囲、機密境界、長期優先順位を決める |
| AI agent | 観察、推論、リスク整理、project-specific な提案を行う |
| Python CLI | OS 差を吸収し、discovery、prompt assembly、agent invocation、check/audit を提供する |
| Audits | stale docs、claim drift、secret risk を検出する |
| Nix | default-required reproducibility layer (stack-aware、ADR 0005 amended 2026-04-29) |

`ai-ops` CLI は product strategy を発明しない。AI は戦略を推論できるが、user の承認なしに確定しない。実装言語と command surface は ADR 0007 が定める。

## Agent portability

canonical instructions は tool-specific config ではなく Markdown と Python 製 `ai-ops` CLI に置く。

- `AGENTS.md` が cross-project source of truth。
- `CLAUDE.md` は Claude Code 向けの `@AGENTS.md` adapter だけでよい。
- Codex、Claude Code、Cursor、その他の AI は、同じ `README.md`、`AGENTS.md`、`docs/ai-first-lifecycle.md`、`templates/*.md`、`ai-ops` CLI から再開できる。
- `.claude/settings.json` 等の tool-specific 設定は defense in depth であり、canonical source of truth ではない。

## Consequences

Positive:

- 複数 AI agent (Claude Code / Codex / Cursor 等) で同じ workflow を使える。
- 新規作成と既存移行が同じ判断モデルで扱える。
- CLI と AI の責務境界が明確になる。

Negative:

- 軽微な project には brief が重い。brief 必須は非自明な creation / migration に限定する。
- brief は Markdown field の構造化であり、AI の判断品質そのものは保証しない。

## Verification

採用時点で以下を確認する:

```sh
python -m ai_ops check
python -m ai_ops audit lifecycle
python -m ai_ops new brief-smoke --purpose "brief validation smoke" --dry-run
direnv exec . nix flake check --all-systems --no-build
direnv exec . sh -c 'nix build --no-link ".#checks.$(nix eval --impure --raw --expr builtins.currentSystem).all"'
```

実プロジェクト validation は対象ごとの proposal と Git history に残す。

## Related

- ADR 0001: AGENTS.md primary
- ADR 0002: portability first
- ADR 0005: Nix optional reproducibility layer
- ADR 0007: Python canonical CLI
- `docs/ai-first-lifecycle.md`
