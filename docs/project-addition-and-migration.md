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

#### Stage A: Hard gates (early exit)

| 条件 | signal | 結果 |
|---|---|---|
| archive | last commit > 18mo, no PR | none |
| scratch | `~/scratch/`, no remote, < 5 file | none |
| docs-only | 全 tracked が markdown/pdf | none / minimal |
| existing flake | `flake.nix` あり | preserve / amend |
| vendor too closed | GUI installer / license dongle | devshell with vendor outside closure |
| upstream fork | non-user org remote, mostly upstream commits | none |

#### Stage B: Stack-aware default

| Stack signal | Level | Template |
|---|---|---|
| `xmake.lua` | devshell | `flake.nix.xmake` |
| `CMakeLists.txt` | devshell | `flake.nix.minimal` (cmake/ninja/clang を tools に追加) |
| 商用 SDK / vendor binary | devshell + overlay | `flake.nix.xmake` 派生 |
| `package.json` / `pnpm-lock.yaml` | devshell | `flake.nix.node` |
| `pyproject.toml` / `uv.lock` | devshell | `flake.nix.python` |
| `Cargo.toml` | devshell | `flake.nix.minimal` (cargo/rustc を tools に追加) |
| `go.mod` | devshell | `flake.nix.minimal` (go を tools に追加) |
| DSL (`*.ato` 等) | devshell minimal | `flake.nix.minimal` |

#### Stage C: Score adjustment

Pros (+1〜+3): toolchain volatility / multi-developer / CI imperative steps / long-term maintenance / external contributor / release artifact / vendor binary / AI session 高頻度 / sandbox 需要 / tests / activity / LOC > 500

Cons (−1〜−5): dormant / scratch / docs-only / throwaway / system-tool only / vendor too closed / tiny project / single binary / strong existing repro layer / stale-not-archive / many top-level memo files

Score ≥ +6 で promote、+2〜+5 で keep、0〜+1 で borderline (brief で flag)、< 0 で demote to none (justification 必須)。

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
5. **README 英語化**: `README.md` を英訳、現主言語版を `README.<locale>.md` に rename (sibling pattern)。各ファイル冒頭に language selector を 1 行
6. **CI 整備**: GitHub Actions でテスト・audit を自動化
7. **`pyproject.toml` / package metadata**: `license` field、`description`、topics 設定
8. **Visibility flip**: `gh repo edit <owner>/<repo> --visibility public --accept-visibility-change-consequences`
9. **Smoke test**: external location から `nix run github:<owner>/<repo> -- ...` 等で external 利用可能性確認

各 step は in-session で 1 つずつ user 承認を得て実行する。batch approval は使わない。
