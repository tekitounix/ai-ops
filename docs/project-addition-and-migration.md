# プロジェクト追加・移行 — 判断基準

> Master operation guide: [`operation.md`](operation.md). This is the deep-dive on judgment criteria for choosing between `new` and `migrate` sub-flows.

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

## Nix (default-required、ADR 0005 amended 2026-04-29)

Nix flake を default-required reproducibility layer とする。AI agent が per-project rubric (Stage A/B/C) で機械判定。

### Level

| Level | 意味 |
|---|---|
| `none` | Nix を使わない (Stage A hard gate or score < 0、justification 必須) |
| `devshell` | toolchain を固定する (default for stack-bearing project) |
| `apps` | `nix run .#check` 等を提供する (score ≥ +6 で promote) |
| `full` | checks / packages まで Nix に寄せる |

### Rubric

Stage A / B / C による採用判定の正本表は [ADR 0005 §Per-project rubric](decisions/0005-nix-optional-reproducibility-layer.md) を参照。本 playbook では決定経路の概念だけ示す:

- **Stage A** が hard gate (archive / scratch / docs-only / existing flake / vendor too closed / upstream fork で early exit)
- **Stage B** が stack signal (xmake / cmake / package.json / pyproject.toml 等) から default level を決定
- **Stage C** が score 補正 (Pros / Cons) で promote / keep / borderline / demote を決める

`ai-ops audit nix --report` で全 project の Nix gap 一覧、`ai-ops audit nix --propose <path>` で個別 retrofit 提案。`ai-ops check` は Nix がなくても bootstrap fallback として動くが、stack-bearing project では Nix audit fail = check fail。

## 完了条件

- brief が存在し、重要 claim が分類されている。
- proposal / target path / rollback が明記されている。
- project-specific check または `ai-ops check` の結果が記録されている。
- Nix 採用時は `nix flake check` の結果が記録されている。

## 既管理 retrofit (Nix のみ追加)

ghq 管理下の既存 project に対し、scope を **Nix 追加のみ** に narrow した migration:

```sh
ai-ops audit nix --report                 # ghq list 全 project の Nix gap survey
ai-ops audit nix --propose <path>          # 単一 project の retrofit Markdown 提案
ai-ops migrate <path> --retrofit-nix       # AI agent 経由で flake.nix + .envrc を追加 (PR scaffold)
```

`--retrofit-nix` 時、AI agent は既管理 project の AGENTS.md / brief / 既存 harness を **変更せず**、flake.nix + .envrc + flake.lock のみ追加する。Brief filename は `docs/brief-YYYYMMDD-nix-retrofit.md` 推奨。

## Promotion (Tier 昇格)

T3 → T2 → T1 への昇格は destructive / visibility change なので Propose -> Confirm -> Execute。各段階の checklist:

### T3 → T2 (local-only から private GitHub remote へ)

```sh
gh repo create <owner>/<repo> --private --source=. --remote=origin --push
```

repo 配置を `~/ghq/local/.../<repo>` から `~/ghq/github.com/<owner>/<repo>` に move する場合は、`mv` 後に `git remote -v` で確認する。 ghq 外 (`~/work/...` 等) からの本格的な物理移行 (AI session / IDE state を含む) は [docs/project-relocation.md](project-relocation.md) を使う。

### T2 → T1 (private から public へ)

ai-ops 自身が 2026-04-27 に T2 → T1 した手順を playbook 化:

1. **History audit**: `gitleaks detect --source . --log-opts="--all"` で leak 確認
2. **Secret 残存 grep**: 個人 email、private project 名、`/Users/<name>` 等の hardcoded path、商業ベンダー名を **全 history** で grep
3. **必要なら history rewrite**: 残存があれば backup branch 作成 → orphan branch + 新規 single commit → `git push --force-with-lease`
4. **LICENSE 追加**: MIT / Apache-2.0 / BSD-3 等
5. **Public docs 整備**: `README.md` は英語の public first entrypoint にする。既存の主言語版が日本語なら `README.ja.md` に置き、各 README 冒頭に language selector を 1 行置く。README 以外の英語 docs は、完成度・公開目的・外部 contributor / user の重要度に応じて追加する
6. **CI 整備**: GitHub Actions でテスト・audit を自動化
7. **`pyproject.toml` / package metadata**: `license` field、`description`、topics 設定
8. **Visibility flip**: `gh repo edit <owner>/<repo> --visibility public --accept-visibility-change-consequences`
9. **Smoke test**: external location から `nix run github:<owner>/<repo> -- ...` 等で external 利用可能性確認

各 step は in-session で 1 つずつ user 承認を得て実行する。batch approval は使わない。
