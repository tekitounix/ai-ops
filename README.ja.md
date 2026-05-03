# ai-ops

[![CI](https://github.com/tekitounix/ai-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/tekitounix/ai-ops/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

[English](README.md) | **日本語**

ai-ops は、 AI コーディングエージェント (Claude Code・Codex・Cursor 等) にプロジェクトの構築・移行・監査を任せるための仕組み。 固定のテンプレートを当てるのではなく、 こちらが意図を伝え、 エージェントが文脈を読んで構成案を出し、 こちらが承認してから実行する流れを提供する。

## すぐ使う

以下のいずれかのプロンプトを AI エージェントに渡す。 残りはエージェントが本リポジトリを読んで判断する。

```text
github.com/tekitounix/ai-ops に従って、新規プロジェクトを立ち上げてください。目的:「<やりたいこと>」
```
**新規プロジェクト用。** エージェントが target の形 (名前・`~/ghq/...` 配下のどこに置くか・stack・check コマンド) を提案し、 こちらの承認を経てからファイルを作成する。

```text
github.com/tekitounix/ai-ops に従って、このプロジェクトを整えてください。
```
**1 つの作業ツリー向け。** エージェントが現状を読み取り、 必要な作業を判定する: *migrate* (まだ ai-ops 管理下にない)・*realign* (管理下だがズレている)・*relocate* (`~/ghq/...` の外にある)・*対応不要*。 範囲ごとに承認を取ってから手を入れる。

```text
github.com/tekitounix/ai-ops に従って、自分のプロジェクト群を監査してください。
```
**ghq 管理下の全プロジェクトを一気に。** エージェントが `ghq list -p` を walk し、 各プロジェクトを drift signal 群で採点して優先度順の一覧を出す (正本フィールドは `audit projects --json` を参照)。 実行はプロジェクト単位: 各 P0 / P1 を該当 sub-flow に route し、 1 件ずつ承認を取る。 P2 は観察のみ。 詳しい手順: [`docs/projects-audit.md`](docs/projects-audit.md)。

すでに AI session 内で作業しているなら、 `--agent claude` / `--agent codex` で別の AI を入れ子に呼び出さないこと。 必要なら `--agent prompt-only` か `--dry-run` でプロンプト出力だけを取得する。

## ai-ops の運用ってどうやるの

運用全体のガイド — ライフサイクルの phase、sub-flow の選び方、**5 つの戦略 (Git / ghq / GitHub / Nix / plan) と自動 / 手動の責任分界表**、workflow tier、worktree ベースの並行作業、GitHub-native の運用基盤、plan 駆動の execution、改善学習の取り込みループ、用途別 CLI リファレンス — はすべて **[`docs/operation.md`](docs/operation.md)** にまとめてある。 まずこの 1 ドキュメントを読めば全体構造が分かる。 そこから `docs/` 配下の各 deep-dive と `docs/decisions/` の設計判断 (ADR) に link されている。

一言で言うと: AI agent が context を読み、 Brief を書き、 user が確認し、 通常の git / gh ツールで実行する。 そこに tier 別ポリシー、 sibling git worktree、 GitHub Issues + scheduled Actions による drift 通知 + 反映 PR が組み合わさる仕組み。

## インストール

```sh
# Nix
nix run github:tekitounix/ai-ops -- --help

# pip (clone してから editable install)
git clone https://github.com/tekitounix/ai-ops
cd ai-ops && pip install -e .

# install せずソースから
git clone https://github.com/tekitounix/ai-ops
cd ai-ops && python -m ai_ops --help
```

Python 3.11 以上が必要。 runtime 依存はゼロ (stdlib のみ)。

## ai-ops プロジェクトに期待される姿

ai-ops は固定テンプレートを使わない。 ただし、 上記のプロンプトが安定して動くため、 各プロジェクトには最小限の規約を期待している:

- **`~/ghq/<host>/<owner>/<repo>/` に置く** (`ghq` でリポジトリ配置を統一)。 「audit my projects」 はここを起点に探索する。
- **プロジェクト root に `AGENTS.md` を置く**。 エージェント向けの行動指針 (やること / やらないこと / 完了条件) を記す file。 上記のプロンプトは ai-ops 本体の `AGENTS.md` を「全プロジェクト共通の source of truth」 として参照する。
- **stack を持つプロジェクトには `flake.nix`** (Node・Python・Rust・Go・xmake・DSL 等)。 Nix で開発環境を再現可能にするため。 docs だけのプロジェクトはプロジェクト個別の rubric (`docs/decisions/0005-...`) で opt-out 可能。
- **`.ai-ops/harness.toml`** (任意): 監査が ai-ops 本体と各プロジェクトのズレを検出するための manifest。 `ai-ops migrate <path> --update-harness` で生成する。 未生成なら監査上は「未管理」 として扱われる。

## コマンド

| コマンド | 用途 |
|---|---|
| `ai-ops new <name> --purpose "..."` | 新規プロジェクト用のプロンプト + plan 起草 |
| `ai-ops migrate <path>` | 既存プロジェクトの read-only discovery + plan |
| `ai-ops migrate <path> --retrofit-nix` | 範囲を Nix のみに絞る (`flake.nix` + `.envrc`) |
| `ai-ops migrate <path> --update-harness` | 範囲を harness 更新のみに絞る (`.ai-ops/harness.toml` 再生成) |
| `ai-ops audit projects [--json] [--priority {P0,P1,P2,all}]` | ghq 管理下の全プロジェクトを drift signal 群で採点。 priority-sorted の一覧 (`--json` で機械可読)。 P0/P1 が残れば exit 1 — cron / CI から使える |
| `ai-ops audit nix [--report] [--propose <path>]` | プロジェクト単位の Nix 監査。 `--report` で全プロジェクト walk、 `--propose` で Markdown retrofit 案 |
| `ai-ops audit harness [--path PATH] [--strict]` | `.ai-ops/harness.toml` と実 file hash のズレを検出 |
| `ai-ops audit standard --since REF` | 指定 ref 以降の ADR (`docs/decisions/`) 変更を検出 (伝播用) |
| `ai-ops audit security` | secret 検出 (任意の repo で動く) |
| `ai-ops audit lifecycle` | ai-ops 自身の self-audit |
| `ai-ops check` | 全 audit + pytest |
| `ai-ops bootstrap [--tier {1,2}] [--with-secrets ...] [--with-pre-push-hook --project PATH]` | 必須 tool を承認下で install。 default `--tier 1`、 `--tier 2` で推奨も含む。 optional で Bitwarden 経由の GitHub secrets 注入 (ADR 0004) と ai-ops pre-push hook の install もできる |
| `ai-ops update [--tier {1,2}]` | 既存 tool を承認下で update。 default `--tier 2` |
| `ai-ops promote-plan <slug> [--source PATH]` | local の AI plan を確認のうえ `docs/plans/<slug>/plan.md` に昇格 |
| `ai-ops propagate --kind {anchor,init,files} (--all \| --project PATH) [--dry-run] [--auto-yes]` | 管理対象プロジェクトに ai-ops state を伝播する PR を起票 (ADR 0011)。 `anchor` は `ai_ops_sha` bump、 `init` は未追跡 `.ai-ops/harness.toml` の commit、 `files` は `[harness_files]` ハッシュの refresh (ファイル内容は触らない) |
| `ai-ops worktree {new,cleanup}` | sibling worktree 管理 (ADR 0010)。 `new <slug>` で branch + worktree + plan skeleton を 1:1:1 で生成。 `cleanup [--auto] [--auto-archive]` で「PR merged + plan archived」の worktree を削除 (`--auto-archive` は Tier A / unmanaged で archive コミットも自動で行う) |
| `ai-ops report-drift [--repo OWNER/NAME]` | `audit projects --json` 出力を ai-ops repo の Issue / sub-issue に翻訳 (ADR 0011 Ecosystem dashboard) |
| `ai-ops setup {ci,codeowners,ruleset}` | 管理対象プロジェクトの GitHub 統合 (ADR 0011)。 `ci --project PATH [--tier T]` で drift-check workflow 追加、 `codeowners --project PATH [--owner USER]` で CODEOWNERS routing、 `ruleset --project PATH --tier {A,B,C}` で tier 別 Repository Ruleset を `gh api` で適用 |
| `ai-ops review-pr --pr N [--repo OWNER/NAME] [--provider {auto,anthropic,openai}]` | PR を ai-ops 規約 (ADR 0012) に対して AI レビュー。 Markdown Comment + status check `ai-ops AI Review` を投稿 |

`new` / `migrate` のフラグ: `--agent {claude,codex,prompt-only,...}`、 `--tier {T1,T2,T3}` (T1 public / T2 private / T3 local)、 `--nix {auto,none,devshell,apps,full}` (default `auto` は AI がプロジェクト個別の rubric で機械決定)、 `--output <path>`、 `--dry-run`、 `--interactive`。

## 設定

`~/.config/ai-ops/config.toml` (user) または `./ai-ops.toml` (repo):

```toml
[agent]
default = "claude"

[agents.claude]
command = ["claude", "-p", "--no-session-persistence", "--tools", ""]

[agents.codex]
command = ["codex", "exec", "-m", "gpt-5.2", "--sandbox", "read-only", "-"]
```

`--agent <name>` で上書き可能。 設定 file が無くても built-in default で動く。

## 検証

```sh
python -m ai_ops check                # 全部
python -m ai_ops audit security       # secret 検出のみ
direnv exec . sh -c '
set -e
nix flake check --all-systems --no-build
nix build --no-link ".#checks.$(nix eval --impure --raw --expr builtins.currentSystem).all"
'
```

Nix はプロジェクトレベルの再現性のため **default-required** (プロジェクト個別の rubric、 ADR 0005)。 `python -m ai_ops check` は Nix 無しでも bootstrap fallback として動くが、 stack を持つプロジェクト (Node / Python / Rust / Go / xmake / DSL) は `flake.nix` を入れるか brief で opt-out を明記しないと `audit nix` が落ちる。

## 構成

```text
README.md  AGENTS.md  CLAUDE.md
pyproject.toml  flake.nix
ai_ops/        Python CLI のソース
tests/         pytest
docs/
  ai-first-lifecycle.md       正式なワークフロー (Intake → Discovery → Brief → Confirm → Execute → Verify → Adopt)
  project-addition-and-migration.md
  realignment.md              ズレた既存プロジェクトの矯正
  project-relocation.md       `~/ghq/` 外からの移行
  projects-audit.md           「audit my projects」 の playbook
  self-operation.md           ai-ops 自身の self-audit
  decisions/                  ADR (一覧は decisions/INDEX.md)
  plans/                      active な実行計画 + archive
templates/                    project / migration / handoff / execution-plan の各テンプレート
```

## ライセンス

[MIT](LICENSE)。
