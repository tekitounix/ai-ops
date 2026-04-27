# ai-ops

[English](README.md) | **日本語**

AI-first project lifecycle system for creating, migrating, and operating projects with AI agents.

## 最短開始

AI agent にそのまま渡す。

新規プロジェクト (やりたいことだけ伝える):

```text
github.com/tekitounix/ai-ops の README.md、AGENTS.md、docs/ai-first-lifecycle.md に従い、「<やりたいこと>」を実現する新規プロジェクトを AI-first で立ち上げてください。プロジェクト名、配置先 (`~/ghq/github.com/<owner>/<repo>/`)、tier、stack、check 方法を AI 側で提案し、重要判断は確認しながら Propose -> Confirm -> Execute で進めてください。
```

新規プロジェクト (名前も指定する):

```text
github.com/tekitounix/ai-ops の README.md、AGENTS.md、docs/ai-first-lifecycle.md に従い、<project-name> を「<one-line-purpose>」のために AI-first で新規作成してください。重要判断だけ確認し、Propose -> Confirm -> Execute で進めてください。
```

既存プロジェクトを移行:

```text
github.com/tekitounix/ai-ops の README.md、AGENTS.md、docs/ai-first-lifecycle.md に従い、<source-path> を AI-first で移行してください。まず read-only discovery を行い、移行案を提示してから Propose -> Confirm -> Execute で進めてください。
```

CLI から直接始める:

```sh
nix run github:tekitounix/ai-ops -- new my-app --purpose "Markdown note app"
nix run github:tekitounix/ai-ops -- migrate "$HOME/ghq/github.com/user/project"
```

すでに AI agent に依頼している場合、その AI は `ai-ops --agent claude` や `--agent codex` で別 AI を入れ子に呼びません。必要なら `--agent prompt-only` または `--dry-run` で prompt / brief / discovery だけを使います。

## 役割

```text
AI agent: project-specific な判断、提案、承認後の実行
User: 公開範囲、機密境界、長期判断の確認
Python CLI: discovery、prompt assembly、agent invocation、check/audit
Nix: optional reproducibility layer
Git: 履歴と復元。repo 内 archive は通常不要
```

この repo は installer ではありません。ユーザーの shell、global git config、OS scheduler、AI tool の user config は自動変更しません。

## 構成

```text
README.md
AGENTS.md
CLAUDE.md
pyproject.toml
flake.nix
ai_ops/
tests/
docs/
  ai-first-lifecycle.md
  project-addition-and-migration.md
  decisions/
templates/
```

履歴・旧計画・旧スクリプト・旧テンプレートは active tree に置きません。必要なら Git history から参照・復元します。

## 検証

```sh
python -m ai_ops check
python -m ai_ops audit security
direnv exec . nix flake check
git diff --check
```

Nix は optional です。Nix がない環境でも `python -m ai_ops check` は動く必要があります。
