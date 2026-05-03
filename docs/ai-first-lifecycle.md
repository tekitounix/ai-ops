# AI ファースト・プロジェクトライフサイクル

> Master operation guide: [`operation.md`](operation.md). This is the deep-dive on the canonical lifecycle (Intake → Adopt) for new project creation and existing project migration.

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
| Agent Execute | AI agent が承認済み内容を通常ツールで実行する | files / repo / harness / optional `docs/plans/<slug>/plan.md` |
| Verify | check と audit で実態を確認する | check output |
| Adopt | 採用内容と延期事項を記録する | `docs/brief-YYYYMMDD.md` / commit message / README / AGENTS.md 反映 |

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

## Routes

Lifecycle の入口は 2 route。両 route の到達点 (Brief / Proposal / Execute) は同じ。

- **Chat route (主)**: `README.md` Quick start の prompt を AI agent (Claude Code、Codex、Cursor 等) に渡す。AI が repo を読み、本 lifecycle に自律的に乗る。対話 / IDE / 通常作業の主流。
- **CLI route**: `ai-ops new` / `ai-ops migrate` を直接呼ぶ。CI、scripts、batch 処理向け。同じ lifecycle を CLI 側から triggers する。

以降の節は CLI route の syntax を例示する。chat route は `README.md` 参照。

## Brief artifact

非自明な creation / migration では、**最初の Brief を `docs/brief-YYYYMMDD.md` として project に commit する** ことを推奨。後日「なぜ T2 にしたか」「stack 選定の理由」「言語方針」を辿れる archeology になる。

CLI route なら `ai-ops new ... --output docs/brief-YYYYMMDD.md` でそのまま生成・commit できる。chat route ならセッション末尾の Brief 部分を copy & paste で `docs/brief-YYYYMMDD.md` に保存する。

Brief template の各 section は project-specific に解釈する。fit しない section は "TBD" / "N/A" / 削除のいずれかで OK。research notes 等の non-code project では Verification Plan の lint / typecheck は無くて良い。

## Execution plan artifact

非自明な feature / migration / refactor で、複数 session・複数 agent・長時間 execution のいずれかが見込まれる場合は、Agent Execute の開始時に `docs/plans/<slug>/plan.md` を作ってよい。`templates/plan.md` を起点にし、`Progress`、`Surprises & Discoveries`、`Decision Log`、`Outcomes & Retrospective` を作業中に更新する。

active plan は `docs/plans/<slug>/` に置く。Verify / Adopt 後、残す価値がある plan は `docs/plans/archive/YYYY-MM-DD-<slug>/` に移す。小さな単発変更では plan を作らず、commit message / PR / Brief だけで足りる。

Claude Code 等が作る user-local plan (`~/.claude/plans/` など) は canonical ではない。必要な場合だけ、user 承認のもとで `ai-ops promote-plan <slug> --source <path>` を使い、repo-local plan へ昇格する。

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
- Nix adoption level (`none`, `devshell`, `apps`, `full`) — default-required, AI agent が rubric (Stage A/B/C) で機械決定 (ADR 0005 amended 2026-04-29)
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
direnv exec . sh -c '
set -e
nix flake check --all-systems --no-build
nix build --no-link ".#checks.$(nix eval --impure --raw --expr builtins.currentSystem).all"
'
git diff --check
```

`ai-ops check` は Nix なしでも bootstrap fallback として動く。ただし Nix は default-required reproducibility layer (ADR 0005 amended)、stack-bearing project では `ai-ops audit nix` fail が `ai-ops check` fail を引き起こす。Nix install は `ai-ops bootstrap` で user 承認後に実行。

project-specific な検証は brief に書く。検証不能なものは「未検証」と明記し、完了扱いにしない。

**Note**: `ai-ops audit lifecycle` は ai-ops 自身の structural integrity を確認する self-audit。新規 project の audit には使わない (project ごとに必要な構造が違うため)。各 project は project-specific check を持ち、`AGENTS.md` の Checks に記述する。`ai-ops audit security` は cwd を scan するので任意の project でも有用。

## Improvement Capture

`Agent Execute` の途中で得た非自明な学びは、Verify / Adopt の前に triage する。各 active plan の `## Improvement Candidates` section に observation / evidence / 採用先 / 確認要否 / verification / disposition を記録し、Adopt 時に「同 plan 内で完結」「durable doc / ADR / template / audit / harness / test に昇格」「deferred (理由付き)」「rejected (理由付き)」「superseded (置換先参照)」のいずれかに振り分ける。広範・破壊的・標準化を伴う採用は `AGENTS.md` Operation Model の Propose -> Confirm -> Execute を通す。schema は `templates/plan.md` を、ai-ops 自身の dogfood 手順は `docs/self-operation.md` を参照。

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
- ADR 0008: execution plan persistence
- ADR 0009: Git workflow tiers
- ADR 0010: Worktree workflow
- ADR 0011: GitHub-native ecosystem operation
- ADR 0012: PR 自動レビュー (二層構成 + AI エージェント主体ワークフロー)
- 全 ADR の navigation は [`decisions/INDEX.md`](decisions/INDEX.md)
