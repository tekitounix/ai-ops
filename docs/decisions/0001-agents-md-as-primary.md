# ADR 0001: AGENTS.md を AI ルールの source of truth にする

> Status: Accepted
> Date: 2026-04-20

## Decision

`AGENTS.md` を、この repo の AI 向け永続ルールの source of truth にする。Claude Code 向けの `CLAUDE.md` は `@AGENTS.md` だけでよい。

## Rationale

- 複数 AI tool 間で同じルールを共有できる。
- tool-specific 設定ファイルの重複を避けられる。
- 人間がレビューする入口が 1 つになる。

## Consequences

- `AGENTS.md` は短く保つ。
- 一時的なタスク状態は書かない。
- 詳細説明は `docs/` に置き、必要時だけ読む。

## Related

- ADR 0004: portability first
- ADR 0015: AI-first lifecycle
- ADR 0016: Python canonical CLI
