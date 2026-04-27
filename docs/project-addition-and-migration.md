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

## Promotion (Tier 昇格)

T3 → T2 → T1 への昇格は destructive / visibility change なので Propose -> Confirm -> Execute。各段階の checklist:

### T3 → T2 (local-only から private GitHub remote へ)

```sh
gh repo create <owner>/<repo> --private --source=. --remote=origin --push
```

repo 配置を `~/ghq/local/.../<repo>` から `~/ghq/github.com/<owner>/<repo>` に move する場合は、`mv` 後に `git remote -v` で確認する。

### T2 → T1 (private から public へ)

ai-ops 自身が 2026-04-27 に T2 → T1 した手順を playbook 化:

1. **History audit**: `gitleaks detect --source . --log-opts="--all"` で leak 確認
2. **Secret 残存 grep**: 個人 email、private project 名、`/Users/<name>` 等の hardcoded path、商業ベンダー名を **全 history** で grep
3. **必要なら history rewrite**: 残存があれば backup branch 作成 → orphan branch + 新規 single commit → `git push --force-with-lease`
4. **LICENSE 追加**: MIT / Apache-2.0 / BSD-3 等
5. **README 英語化**: `README.md` を英訳、現主言語版を `README.<locale>.md` に rename (sibling pattern)。各ファイル冒頭に language selector を 1 行
6. **CI 整備**: GitHub Actions でテスト・audit を自動化
7. **`pyproject.toml` / package metadata**: `license` field、`description`、topics 設定
8. **Visibility flip**: `gh repo edit <owner>/<repo> --visibility public --accept-visibility-change-consequences`
9. **Smoke test**: external location から `nix run github:<owner>/<repo> -- ...` 等で external 利用可能性確認

各 step は in-session で 1 つずつ user 承認を得て実行する。batch approval は使わない。
