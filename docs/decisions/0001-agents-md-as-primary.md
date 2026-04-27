# ADR 0001: AGENTS.md を AI ルールの source of truth にする

> Status: Accepted
> Date: 2026-04-20

## Decision

`AGENTS.md` を、この repo の AI 向け永続ルールの source of truth にする。Claude Code 向けの `CLAUDE.md` は `@AGENTS.md` だけでよい。

## Rationale

- 複数 AI tool 間で同じルールを共有できる。
- tool-specific 設定ファイルへのルール散在を避けられる。
- 人間のレビュー入口が 1 つに集約される。

## Consequences

- `AGENTS.md` は短く保つ。一時的なタスク状態は書かない。
- 詳細説明は `docs/` に置き、必要時だけ読む。

## Related

- ADR 0002: portability first
- ADR 0006: AI-first project lifecycle
- ADR 0007: Python canonical CLI
