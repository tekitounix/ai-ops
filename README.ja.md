# ai-ops

[![CI](https://github.com/tekitounix/ai-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/tekitounix/ai-ops/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

[English](README.md) | **日本語**

ai-ops は短い Python CLI で、AI コーディング agent (Claude Code、Codex、Cursor 等) が **固定テンプレートではなくプロジェクト個別の提案** を作るためのフレームワークを提供する。User が intent を伝え、agent が観察し、Brief を起草し、user が確認し、agent が実行する。

## Why

cookiecutter / copier / yeoman 等のテンプレートは、プロジェクトが生まれる前にディレクトリ構成や stack を凍結する。理想的な形はプロジェクトごとに違うし、AI agent はそれを推論できる。ai-ops はその枠組みを与える: 文脈を読み、構造化された Brief (Fact / Inference / Risk / User decision / AI recommendation) を起草し、確認を待ってから通常のツールで実行する。

## 最短開始

AI agent にそのまま渡す。残りは agent が repo を読んで処理する。

```text
github.com/tekitounix/ai-ops に従って、「<やりたいこと>」のための新規プロジェクトを立ち上げてください。
```

```text
github.com/tekitounix/ai-ops に従って、<project-name> を「<one-line-purpose>」のために作成してください。
```

```text
github.com/tekitounix/ai-ops に従って、<source-path> を移行してください。
```

```text
https://github.com/tekitounix/ai-ops/blob/main/docs/realignment.md に従って、このプロジェクトを矯正してください。
```

agent はこの repo を読み、環境を discovery し (`git config --get ghq.user`、OS 等)、11-section の Brief を起草、target の形 (name、`~/ghq/...` への配置、tier、stack、check コマンド) を提案、確認を待ってからファイル作成 / 移行を実行する。矯正用 prompt は「既に存在するが理想からずれてしまった」project 向けで、agent が read-only で観察し、可逆性で 3 段 (P0 doc-only / P1 structural / P2 behavioral) に分けた Realignment Brief を出し、scope ごとの個別承認を待ってから編集する。

すでに AI session 内で作業している場合、その AI は `--agent claude` / `--agent codex` で別 AI を入れ子に呼ばない。必要なら `--agent prompt-only` または `--dry-run` で prompt / brief / discovery 出力だけを使う。

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

Python 3.11+ 必須。runtime 依存ゼロ (stdlib のみ)。

## コマンド

| コマンド | 用途 |
|---|---|
| `ai-ops new <name> --purpose "..."` | 新規 project の prompt + Brief draft 組立 |
| `ai-ops migrate <path>` | 既存 project の read-only discovery + Brief |
| `ai-ops migrate <path> --retrofit-nix` | 既管理 project に `flake.nix` + `.envrc` を追加する narrow scope |
| `ai-ops bootstrap [--tier {1,2}]` | 必須 tool (git, ghq, direnv, jq, gh, nix; +shellcheck/actionlint/gitleaks/fzf/rg) の存在確認と user 承認後 install。default `--tier 1` (必須のみ) |
| `ai-ops update [--tier {1,2}]` | 既存 tool の survey と user 承認後 update。default `--tier 2` (必須 + 推奨) |
| `ai-ops audit {lifecycle,nix,security,harness,standard}` | 自己 audit (`lifecycle` は ai-ops 自身、`security` は任意 cwd で動作) |
| `ai-ops audit nix --report` | `ghq list -p` を歩いて fleet 全体の Nix gap table を出力 |
| `ai-ops audit nix --propose <path>` | 1 project 用の Markdown retrofit 提案を出力 |
| `ai-ops audit harness [--path PATH]` | `.ai-ops/harness.toml` と実 file hash を比較し harness drift を検出 |
| `ai-ops audit standard --since REF` | reference 以降の ADR (docs/decisions/) 変更を検出 (propagation 用) |
| `ai-ops check` | 全 audit + pytest |
| `ai-ops promote-plan <slug> [--source PATH]` | user が選んだ local AI plan を確認後に `docs/plans/<slug>/plan.md` へ昇格 |

各コマンドは本 repo の `templates/` を読み、`AGENTS.md` を operating rule として embed し、prompt を出力するか configured agent を invoke する。

`new` / `migrate` のフラグ: `--agent {claude,codex,prompt-only,...}`、`--tier {T1,T2,T3}`、`--nix {auto,none,devshell,apps,full}` (default `auto` = AI agent が per-project rubric で機械決定、ADR 0005)、`--output <path>`、`--dry-run`、`--interactive`。`migrate` は加えて `--retrofit-nix` (Nix-only narrow scope) と `--update-harness` (harness drift 修復) を持つ。

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

CLI flag `--agent <name>` で override。設定ファイル無しでも built-in default で動作。

## 役割

```text
AI agent: project-specific な判断、提案、承認後の実行
User: 公開範囲、機密境界、長期判断の確認
Python CLI: discovery、prompt assembly、agent invocation、check/audit、tool bootstrap
Nix: default-required reproducibility layer (stack-aware、per-project rubric、ADR 0005 amended)
Git: 履歴と復元。repo 内 archive は通常不要
```

この repo は *silent* installer ではない。ユーザーの shell、global git config、OS scheduler、AI tool の user config を確認なしに変更しない。`ai-ops bootstrap` / `ai-ops update` は user 承認 (Operation Model: Propose → Confirm → Execute) を経てから必須 tool を install / upgrade する。

## 概念

- **Lifecycle (8-step)**: Intake → Discovery → Brief → Proposal → Confirm → Agent Execute → Verify → Adopt。詳細は [docs/ai-first-lifecycle.md](docs/ai-first-lifecycle.md)。
- **Brief**: AI が execute 前に埋める 11-section の構造化提案書。[templates/](templates/) 参照。
- **Execution plan**: 非自明な execution work 用の living plan。`docs/plans/<slug>/plan.md` に置き、[templates/plan.md](templates/plan.md) を起点にする。
- **Self-operation**: ai-ops 自身の dogfood、release gate、file hygiene、drift review の運用。[docs/self-operation.md](docs/self-operation.md) 参照。
- **Realignment**: 既に運用しているが理想からずれた project を ai-ops モデルに戻す手順。read-only Discovery -> Realignment Brief -> scope 単位の Execute on confirmation。[docs/realignment.md](docs/realignment.md) 参照。
- **Tier**: T1 public / T2 private / T3 local / OFF (PII)。[docs/project-addition-and-migration.md](docs/project-addition-and-migration.md) 参照。
- **Operation Model**: 破壊的・横断的変更には Propose → Confirm → Execute。[AGENTS.md](AGENTS.md) で定義。
- **Multi-agent**: parallel session は `claude --worktree` / Codex の built-in worktree を使う。AGENTS.md "Multi-agent" 参照。

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
  self-operation.md
  decisions/   ADR 0001-0008
  plans/       active execution plans + archive
templates/     project-brief / migration-brief / agent-handoff / plan
```

Phase 9 より前の旧計画・旧スクリプト・旧テンプレートは active tree に置かない。必要なら Git history から参照・復元する。

## 検証

```sh
python -m ai_ops check                # 全部
python -m ai_ops audit security       # secret scan のみ
direnv exec . nix flake check         # Nix がある場合
```

Nix は **default-required** な project-level reproducibility layer (per-project rubric、ADR 0005 amended)。`python -m ai_ops check` は bootstrap fallback として Nix なしでも動くが、stack を持つ project (Node / Python / Rust / Go / xmake / DSL) は `flake.nix` が無い限り `ai-ops audit nix` が fail する (brief で明示的に opt-out した場合のみ許容)。

## License

[MIT](LICENSE)。
