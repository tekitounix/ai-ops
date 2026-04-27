# AI ファースト・プロジェクトライフサイクル

この文書は、ai-ops における新規プロジェクト作成と既存プロジェクト移行の canonical workflow である。目的は、AI に機械的 scaffold を実行させることではない。AI が project-specific な理想状態を考え、使用者が確認し、その後 AI agent が通常の開発ツールで実行する。

## 全体フロー

```text
Intake -> Discovery -> Brief -> Proposal -> Confirm -> Agent Execute -> Verify -> Adopt
```

| Step | 目的 | 主な成果物 |
|---|---|---|
| Intake | repo から推論できない事項だけを聞く | user decision list |
| Discovery | files / commands / docs / git state を観察する | Fact / Inference / Risk |
| Brief | project-specific な判断を構造化する | project brief または migration brief |
| Proposal | target state と実行案を提示する | commands / paths / risks / rollback |
| Confirm | user が 1 proposal を承認する | approved scope |
| Agent Execute | AI agent が承認済み内容を通常ツールで実行する | files / repo / harness |
| Verify | check と audit で実態を確認する | check output |
| Adopt | 採用内容と延期事項を残す | Git diff / commit message / project docs |

## Agent Contract

AI agent は、重要な claim を必ず分類する。

| Class | 意味 |
|---|---|
| Fact | repo、command output、user 発言から直接観察できる事実 |
| Inference | Fact からの推論 |
| Risk | 害、不確実性、機密、長期運用上の懸念 |
| User decision | repo からは安全に決められない判断 |
| AI recommendation | AI が推奨する default と理由 |

AI は、質問する前に読めるものを読む。質問してよいのは、推測すると構造・機密・長期運用に害があり、かつ trade-off 付きの推奨を提示できる場合だけである。

## 新規プロジェクト

```sh
ai-ops new my-app --purpose "Markdown note app"
ai-ops new --interactive
ai-ops new my-app --purpose "Markdown note app" --agent claude
ai-ops new my-app --purpose "Markdown note app" --agent prompt-only
```

`ai-ops new` は prompt と brief draft を組み立て、設定済み agent に渡す。AI CLI がない環境では `prompt-only` または `--dry-run` でコピー用 prompt を出力する。

最低限決めること:

- purpose / users / non-goals
- repo placement と visibility tier
- stack と runtime
- data / secrets / production access の境界
- AI が自由に触ってよい範囲と確認が必要な範囲
- check command
- Nix adoption level (`none`, `devshell`, `apps`, `full`)
- 初回 milestone

## 既存プロジェクト移行

```sh
ai-ops migrate "$HOME/ghq/github.com/user/project"
ai-ops migrate --interactive
ai-ops migrate "$HOME/ghq/github.com/user/project" --agent codex
ai-ops migrate "$HOME/ghq/github.com/user/project" --dry-run
```

既存プロジェクトは機械的に移行しない。`ai-ops migrate` は read-only discovery を先に行い、evidence 付き prompt を agent に渡す。AI agent は keep / split / merge、harness、check、Nix、AI history、rollback を project-specific に提案する。

secret value は読まない。secret らしいファイル名や pattern は、値を開かず Risk として扱う。

## Python CLI の責務

Python CLI は、次だけを正規責務として持つ。

- config resolution
- default agent selection
- read-only discovery
- prompt / brief assembly
- agent invocation
- lifecycle / nix / security audit
- self-check (`ai-ops check`)

Python CLI は固定 scaffold の materializer ではない。プロジェクトの理想形は project-specific なので、実行は confirmation 後の AI agent が行う。

## Confirm の粒度

`AGENTS.md` の Propose -> Confirm -> Execute が source of truth である。特に次は 1 proposal ずつ確認する。

- destructive operation
- environment change
- AI data substrate operation
- cross-cutting plan execution
- visibility change
- project-specific harness overwrite

batch approval は使わない。承認範囲が広すぎる場合は、phase または file group に分ける。

## Verification

ai-ops 自身の標準検証:

```sh
ai-ops check
direnv exec . nix flake check
git diff --check
```

Nix が未導入でも `ai-ops check` は動く必要がある。Nix は optional wrapper であり、唯一の検証入口ではない。

project-specific な検証は brief に書く。検証不能なものは「未検証」と明記し、完了扱いにしない。

## Handoff

別 AI agent または fresh session に引き継ぐ場合は、`templates/agent-handoff.md` を使う。handoff には最低限、次を含める。

- 最初に読むファイル
- 現在の approved scope
- 実行済み commands
- 未解決の user decisions
- 次に実行してよいこと
- 実行してはいけないこと

## 関連

- ADR 0001: AGENTS.md primary
- ADR 0002: portability first
- ADR 0005: Nix optional reproducibility layer
- ADR 0006: AI-first project lifecycle
- ADR 0007: Python canonical CLI
