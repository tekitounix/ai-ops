# プロジェクト追加・移行 — 判断基準

詳細な workflow と CLI 例は `docs/ai-first-lifecycle.md` を参照する。ここでは判断軸だけを補足する。

## 共通原則

- CLI に project strategy を決めさせない。AI agent が project-specific に判断する。
- 既存プロジェクトは機械的に移行しない。read-only discovery を先に行う。
- secret value は読まない、書かない。secret らしいファイル名や pattern は Risk として扱う。
- User confirmation までは repo 作成・file 書き込み・visibility 変更をしない。

## Tier

| Tier | 置き場所 | 使う場面 |
|---|---|---|
| `T1` | public remote | 公開前提の OSS |
| `T2` | private remote | 標準。共有・将来公開未定 |
| `T3` | local only under `~/ghq/local/` | 個人実験、短期検証 |
| `OFF` | ai-ops 対象外 | PII、生 credential、顧客データ等 |

`T1` public は必ず明示確認する。迷う場合は `T2` または `T3`。

## Nix

| Level | 意味 |
|---|---|
| `none` | Nix を使わない |
| `devshell` | toolchain を固定する |
| `apps` | `nix run .#check` 等を提供する |
| `full` | checks / packages まで Nix に寄せる |

Nix は optional。`ai-ops check` は Nix がなくても動く必要がある。

## 完了条件

- brief が存在し、重要 claim が分類されている。
- proposal / target path / rollback が明記されている。
- project-specific check または `ai-ops check` の結果が記録されている。
- Nix 採用時は `nix flake check` の結果が記録されている。
