# ai-ops

[![CI](https://github.com/tekitounix/ai-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/tekitounix/ai-ops/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

[English](README.md) | **日本語**

ai-ops は小さな Python CLI で、AI コーディング agent (Claude Code、Codex、Cursor など) が **固定テンプレートではなくプロジェクトごとの提案** を作るための枠組みを提供する。ユーザーが意図を伝え、agent が観察し、Brief を起草し、ユーザーが確認したうえで agent が実行する。

## なぜ

cookiecutter / copier / yeoman などのテンプレートは、プロジェクトが生まれる前にディレクトリ構成や stack を凍結してしまう。理想的な形はプロジェクトごとに異なり、AI agent はそれを推論できる。ai-ops はそのための枠組みを提供する: 文脈を読み、構造化された Brief (Fact / Inference / Risk / User decision / AI recommendation) を起草し、ユーザーの確認を待ってから通常のツールで実行する。

## 最短開始

以下のいずれかを AI agent に渡せばよい。残りは agent が本 repo を読んで進める。

```text
github.com/tekitounix/ai-ops に従って、新規プロジェクトを立ち上げてください。目的:「<やりたいこと>」
```

```text
github.com/tekitounix/ai-ops に従って、このプロジェクトを整えてください。
```

```text
github.com/tekitounix/ai-ops に従って、自分の fleet を監査してください。
```

最初のプロンプトは新規プロジェクト用。観察対象の working tree がないため、目的だけは user が伝える必要がある (末尾の「<やりたいこと>」を書き換えるだけ)。 agent は 11-section の Brief を起草し、target の形 (name、`~/ghq/...` への配置、tier、stack、check コマンド) を提案し、ユーザーの確認を経てから初めてファイルを作成する。

2 つ目のプロンプトは既存 working tree 全般の単一 entry point。agent が cwd を read-only で観察し、どの sub-flow に行くかを自分で判断する ── migrate (ai-ops 未管理)、realign (管理済みだが drift)、relocate (path が `~/ghq/...` 外)、または「対応不要」を返す。判断後、scope ごとに個別の承認を待ってから編集する。

3 つ目のプロンプトは fleet-wide 監査。agent が `ghq list -p` を walk し、 各 project から signal (managed 状態 / nix gap / secret-name file / location drift / 最終 commit / dirty state / TODO 滞留) を収集して、 priority-sorted の Fleet Audit Brief を出す。 action は per-project のまま ── 各 P0 / P1 行を適切な sub-flow (relocate / migrate / realign) に route し、 1 件ずつ確認を取る。 P2 行は観察のみ。

すでに AI session のなかで作業している場合、その AI から `--agent claude` / `--agent codex` で別の AI を入れ子で呼び出さない。必要なら `--agent prompt-only` または `--dry-run` を使い、prompt / brief / discovery の出力だけを得る。

## インストール

```sh
# Nix (install 不要)
nix run github:tekitounix/ai-ops -- --help

# pip (clone 後に editable install)
git clone https://github.com/tekitounix/ai-ops
cd ai-ops && pip install -e .

# install せずソースから
git clone https://github.com/tekitounix/ai-ops
cd ai-ops && python -m ai_ops --help
```

Python 3.11 以上が必要。実行時依存はゼロ (stdlib のみ)。

## コマンド

| コマンド | 用途 |
|---|---|
| `ai-ops new <name> --purpose "..."` | 新規 project の prompt + Brief draft 組立 |
| `ai-ops migrate <path>` | 既存 project の read-only discovery + Brief |
| `ai-ops migrate <path> --retrofit-nix` | 既管理 project に `flake.nix` + `.envrc` を追加する narrow scope |
| `ai-ops bootstrap [--tier {1,2}]` | 必須 tool (git, ghq, direnv, jq, gh, nix; +shellcheck/actionlint/gitleaks/fzf/rg) の存在確認と、ユーザー承認後の install。default `--tier 1` (必須のみ) |
| `ai-ops update [--tier {1,2}]` | 既存 tool の survey と、ユーザー承認後の update。default `--tier 2` (必須 + 推奨) |
| `ai-ops audit {lifecycle,nix,security,harness,standard,fleet}` | 自己 audit (`lifecycle` は ai-ops 自身、`security` は任意 cwd、`fleet` は ghq 管理下の全 project を walk) |
| `ai-ops audit fleet [--json] [--priority {P0,P1,P2,all}]` | `ghq list -p` を walk し各 project を 8 signal で採点、 priority-sorted table を出力 (`--json` で機械可読)。 P0/P1 が残れば exit 1 — cron / CI から利用可 |
| `ai-ops audit nix --report` | `ghq list -p` を歩いて fleet 全体の Nix gap table を出力 |
| `ai-ops audit nix --propose <path>` | 1 project 用の Markdown retrofit 提案を出力 |
| `ai-ops audit harness [--path PATH] [--strict]` | `.ai-ops/harness.toml` と実 file hash を比較し harness drift を検出。 default では manifest 不在を non-blocking warning として扱い fleet survey を pre-adoption repo 横断で回せる。 `--strict` で manifest 不在を failure に昇格 |
| `ai-ops audit standard --since REF` | reference 以降の ADR (docs/decisions/) 変更を検出 (propagation 用) |
| `ai-ops check` | 全 audit + pytest |
| `ai-ops promote-plan <slug> [--source PATH]` | ユーザーが選んだ local AI plan を、確認のうえ `docs/plans/<slug>/plan.md` へ昇格 |

各コマンドは本 repo の `templates/` を読み込み、`AGENTS.md` を operating rule として埋め込んだうえで、prompt を出力するか configured agent を呼び出す。

`new` / `migrate` のフラグ: `--agent {claude,codex,prompt-only,...}`、`--tier {T1,T2,T3}`、`--nix {auto,none,devshell,apps,full}` (default `auto` = AI agent が per-project rubric で機械決定、ADR 0005)、`--output <path>`、`--dry-run`、`--interactive`。`migrate` はこれに加えて `--retrofit-nix` (Nix-only narrow scope) と `--update-harness` (harness drift 修復) を持つ。

## 設定

`~/.config/ai-ops/config.toml` (user 単位) または `./ai-ops.toml` (repo 単位):

```toml
[agent]
default = "claude"

[agents.claude]
command = ["claude", "-p", "--no-session-persistence", "--tools", ""]

[agents.codex]
command = ["codex", "exec", "-m", "gpt-5.2", "--sandbox", "read-only", "-"]
```

CLI フラグ `--agent <name>` で上書きする。設定ファイルが無くても built-in default で動作する。

## 役割

```text
AI agent: project-specific な判断、提案、承認後の実行
User: 公開範囲、機密境界、長期判断の確認
Python CLI: discovery、prompt assembly、agent invocation、check/audit、tool bootstrap
Nix: default-required reproducibility layer (stack-aware、per-project rubric、ADR 0005 amended)
Git: 履歴と復元 (repo 内 archive は通常不要)
```

本 repo は *silent* installer ではない。ユーザーの shell、global git config、OS scheduler、AI tool の user config を、ユーザー承認なしに変更することはない。`ai-ops bootstrap` / `ai-ops update` は、ユーザー承認 (Operation Model: Propose → Confirm → Execute) を経てから必須 tool を install / upgrade する。

## 概念

- **Lifecycle (8-step)**: Intake → Discovery → Brief → Proposal → Confirm → Agent Execute → Verify → Adopt。詳細は [docs/ai-first-lifecycle.md](docs/ai-first-lifecycle.md)。
- **Brief**: AI が execute 前に埋める 11-section の構造化提案書。[templates/](templates/) を参照。
- **Execution plan**: 非自明な execution work 用の living plan。`docs/plans/<slug>/plan.md` に置き、[templates/plan.md](templates/plan.md) を起点にする。
- **Self-operation**: ai-ops 自身の dogfood、release gate、file hygiene、drift review の運用。[docs/self-operation.md](docs/self-operation.md) を参照。
- **Realignment**: すでに運用しているが理想からずれてしまったプロジェクトを ai-ops モデルへ戻す手順。read-only Discovery → Realignment Brief → scope 単位の Execute on confirmation。[docs/realignment.md](docs/realignment.md) を参照。
- **Fleet audit**: ghq 管理下の全プロジェクトを一気に監査する手順。priority-sorted Fleet Audit Brief で各 P0 / P1 を該当 sub-flow に route、 per-project confirmation で実行する。[docs/fleet-audit.md](docs/fleet-audit.md) を参照。
- **Tier**: T1 public / T2 private / T3 local / OFF (PII)。[docs/project-addition-and-migration.md](docs/project-addition-and-migration.md) を参照。
- **Operation Model**: 破壊的・横断的変更には Propose → Confirm → Execute。[AGENTS.md](AGENTS.md) で定義。
- **Multi-agent**: parallel session は `claude --worktree` または Codex の built-in worktree を使う。AGENTS.md "Multi-agent" を参照。

## 構成

```text
README.md  AGENTS.md  CLAUDE.md
pyproject.toml  flake.nix
ai_ops/        Python CLI source
tests/         pytest
docs/
  ai-first-lifecycle.md
  project-addition-and-migration.md
  realignment.md
  fleet-audit.md
  self-operation.md
  decisions/   ADR 0001-0008
  plans/       active execution plans + archive
templates/     project-brief / migration-brief / agent-handoff / plan
```

Phase 9 より前の旧計画・旧スクリプト・旧テンプレートは active tree に置かない。必要があれば Git history から参照または復元する。

## 検証

```sh
python -m ai_ops check                # 全部
python -m ai_ops audit security       # secret scan のみ
direnv exec . sh -c '
set -e
nix flake check --all-systems --no-build
nix build --no-link ".#checks.$(nix eval --impure --raw --expr builtins.currentSystem).all"
'
```

Nix は **default-required** な project-level reproducibility layer (per-project rubric、ADR 0005 amended)。`python -m ai_ops check` は bootstrap fallback として Nix が無くても動作するが、stack を持つプロジェクト (Node / Python / Rust / Go / xmake / DSL) では `flake.nix` が無い限り `ai-ops audit nix` が失敗する (brief で明示的に opt-out した場合のみ許容)。

## ライセンス

[MIT ライセンス](LICENSE) のもとで公開。
