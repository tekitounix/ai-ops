# ADR 0007: 削除は Git 履歴と復旧可能性を優先する

> Status: Accepted
> Date: 2026-04-21

## Decision

削除は復旧可能性が高い手段から選ぶ。

1. tracked file: Git deletion として扱い、`git diff` で確認する。
2. untracked user data: trash / quarantine を優先する。
3. generated artifacts: deterministic path のみ削除可。
4. `rm -rf` は default 禁止。再生成可能、隔離済み、guard 付き、個別承認済みの場合だけ使う。

repo 内 `archive/` は通常使わない。Git 管理下の古いファイルは active tree から削除し、履歴で復元する。

## Rationale

in-repo archive は source of truth を増やし、AI と人間を誤誘導する。Git が履歴・復元・レビューの役割を持つため、active tree は現在必要なものだけにする。

## Related

- ADR 0004: portability first
