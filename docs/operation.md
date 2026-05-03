# ai-ops 運用ガイド

ai-ops の運用全体を理解するためのマスター入口である。まずこの文書を読み、必要に応じて各 deep-dive へ進む。

## ai-ops とは何か

ai-ops は、AI コーディングエージェント (Claude Code、Codex、Cursor など) に対して、複数プロジェクトを横断する共通の運用台本を repo にコミットして提供する仕組みである。台本の中身は、新規プロジェクトの立ち上げ、既存プロジェクトの取り込み、監査、変更の伝播。各プロジェクトは tier に応じた git ワークフロー規約 (ADR 0009) を持ち、並行作業は plan と 1:1:1 で結びついた sibling worktree で行い (ADR 0010)、ai-ops 自身の改善は GitHub-native な PR / Issue を経由して管理対象プロジェクトへ届く (ADR 0011)。通知の中心は使用者の GitHub Notifications。

## ライフサイクル

非自明な作業は次のフローを通る。

```text
Intake → Discovery → Brief → Proposal → Confirm → Agent Execute → Verify → Adopt
```

エージェントは状況を読み (Discovery)、プロジェクト固有の判断を Brief にまとめ、使用者が確認した後にはじめて通常のツールでファイルを変更する。各フェーズの詳細と Fact / Inference / Risk 分類は [`docs/ai-first-lifecycle.md`](ai-first-lifecycle.md) を参照。

## 目的別 sub-flow

| やりたいこと | 使う sub-flow | doc |
|---|---|---|
| 新規プロジェクトを始める | `ai-ops new` → Brief → 実行 | [`ai-first-lifecycle.md`](ai-first-lifecycle.md) |
| 既存プロジェクトを ai-ops 配下に取り込む | `ai-ops migrate <path>` → Brief → 実行 | [`project-addition-and-migration.md`](project-addition-and-migration.md) |
| 管理中プロジェクトの drift を修正 | `align this project` プロンプト → Brief → 実行 | [`realignment.md`](realignment.md) |
| repo を `~/ghq/...` 配下へ移動 | Phase 1 read-only Discovery → relocation Brief → 実行 | [`project-relocation.md`](project-relocation.md) |
| ghq 管理下の全プロジェクトを一括監査 | `audit my projects` プロンプト → 優先度ソート表 → 個別 sub-flow | [`projects-audit.md`](projects-audit.md) |
| ai-ops の改善を管理対象プロジェクトへ反映 | `propagate-anchor` / `propagate-init` / `propagate-files` → 各プロジェクトに PR | (CLI 一覧参照) |
| ai-ops 自身の作業を運用 | self-check + plans + ADR | [`self-operation.md`](self-operation.md) |

各 sub-flow は同じライフサイクル (Discovery → Brief → Confirm → Execute) を辿る。違いは scope と入口条件のみ。

## ワークフロー tier (ADR 0009)

各管理対象プロジェクトは `.ai-ops/harness.toml::workflow_tier` で 4 段階の tier を宣言する。tier は期待される git 運用規範を決め、ai-ops は監査するが強制はしない。

- **Tier A — 軽量**: trunk-based、main への直接 push 可、CI は green 必須。ai-ops 自身、knx3 系の個人ツールなど。
- **Tier B — 管理**: feature branch + PR 必須、ブランチ保護あり。mi_share、audio-dsp-docs など。
- **Tier C — 本番 / 公開**: 上記に加えてレビュー承認、署名コミット、merge queue を要求。
- **Tier D — スパイク / 研究**: 何でもあり (long-lived branch も許容)。umipal phase-a、fx-llm-research など。

宣言が無い場合は D (最も寛容) として扱う。監査の `tier_violations` 信号は、宣言と実態が乖離した時に立つ。詳細定義と検出ルールは [ADR 0009](decisions/0009-git-workflow-tiers.md)。

## worktree ベース並行作業 (ADR 0010)

非自明な作業 (複数コミット、並行ストリーム、plan を要する任意の作業) では、次の 1:1:1 を維持する。

- **plan** 1 つ (`docs/plans/<slug>/plan.md`)
- **branch** 1 つ (`<type>/<slug>`、`<type>` は `feat`/`fix`/`chore`/`docs`/`refactor`)
- **worktree** 1 つ (`<repo-parent>/<repo-name>.<slug>/`、sibling 配置)

`ai-ops worktree-new <slug>` で 3 点セットを一気に作成し、canonical テンプレートから plan の skeleton を seed する。`ai-ops worktree-cleanup` は「PR がマージ済み AND plan が archive 済み」の両方が成立した worktree のみ削除する (安全のため両信号必須)。実用上の上限は 1 repo あたり 3〜5 worktree。詳しい規約は [ADR 0010](decisions/0010-worktree-workflow.md)。

## GitHub-native エコシステム運用 (ADR 0011)

ai-ops の主たる使用者向け表面は、ローカル CLI ではなく **GitHub Issues + sub-issues + Projects v2 ボード + scheduled Actions + Repository Rulesets + CODEOWNERS** である。drift 状況や伝播作業は使用者の既存の GitHub Notifications に乗る。

3 層構成。

1. **ai-ops repo がスケジュール workflow を回す** (`.github/workflows/ecosystem-watch.yml`、`propagate-cron.yml`)
   - 週次 cron で管理対象プロジェクトを監査 → 中央の "Ecosystem" 親 issue 配下に sub-issue を open / update / close
   - 週次 cron で `propagate-* --auto-yes` を実行 → 各管理対象プロジェクトに PR を open
2. **各管理対象プロジェクトに薄い caller workflow を配置** (`.github/workflows/ai-ops.yml`、opt-in は `ai-ops setup-ci-workflow`)。これは ai-ops 側の reusable `managed-project-check.yml` を呼び、PR と schedule で `audit harness --strict` を走らせる。Tier B 以上では Repository Ruleset により必須ステータスチェックになる。
3. **CODEOWNERS で ai-ops 関連変更をプロジェクト所有者にルーティング** (`ai-ops setup-codeowners`)。tier 別 ruleset (`ai-ops setup-ruleset --tier {A,B,C}`) で tier 規範を強制する。

drift 検出はローカルでもスケジュール GitHub Actions でも回り、結果は標準的な GitHub UI に Issue / sub-issue / PR として現れる。設計と setup フローの詳細は [ADR 0011](decisions/0011-github-native-operation.md)。

## plan 駆動実行 (ADR 0008)

非自明な作業は `docs/plans/<slug>/plan.md` で追跡する (canonical schema は [`templates/plan.md`](../templates/plan.md))。必須 section は Purpose / Big Picture、Progress、Surprises & Discoveries、Decision Log、Outcomes & Retrospective、Improvement Candidates、Context、Plan of Work、Concrete Steps、Validation and Acceptance、Idempotence、Artifacts、Interfaces。

plan は living document として、作業中に Progress / Surprises / Decision Log / Outcomes を更新し続ける。完了後 (Verify / Adopt 後) は `docs/plans/archive/YYYY-MM-DD-<slug>/` へ移動する。Progress 完了後も active ディレクトリに残った plan は lifecycle audit が WARN を出す。schema と採用ルールの詳細は [ADR 0008](decisions/0008-plan-persistence.md)。

## Improvement Capture ループ

各 plan は `Improvement Candidates` section を持つ。実行中の学びは `Recommended adoption target` (`current-plan` / `durable-doc` / `adr` / `template` / `audit` / `harness` / `test` / `deferred` / `rejected`) と `Disposition` (`open` / `adopted` / `deferred` / `rejected` / `superseded`) を付けて記録する。横断的または破壊的な adopt は Propose → Confirm → Execute を通す。詳細は [`self-operation.md`](self-operation.md) と [`ai-first-lifecycle.md`](ai-first-lifecycle.md)。

## CLI クイックリファレンス (目的別)

flag 全部入りの正本リストは [`AGENTS.md`](../AGENTS.md) の Subcommands、または [`README.md`](../README.md) の CLI 表を参照。

**セットアップ**
- `ai-ops new <name> --purpose "..."` — 新規プロジェクトの Brief
- `ai-ops migrate <path>` — 既存プロジェクトを ai-ops 配下に取り込み
- `ai-ops bootstrap` / `ai-ops update` — tier 1/2 ツールの install / 更新

**監査**
- `ai-ops audit projects` — ghq 管理下の全プロジェクトを一括監査 (priority + sub-flow を出力)
- `ai-ops audit harness` — `.ai-ops/harness.toml` と実ファイルの drift
- `ai-ops audit nix` — Nix 採用 gap
- `ai-ops audit security` — secret 名称スキャン
- `ai-ops audit lifecycle` — ai-ops 自身の self-audit
- `ai-ops check` — 上記すべて + pytest

**並行作業 (ADR 0010)**
- `ai-ops worktree-new <slug>` — branch + worktree + plan skeleton を作成
- `ai-ops worktree-cleanup` — PR merged + plan archived の worktree を削除

**ai-ops 改善の伝播 (ADR 0011)**
- `ai-ops propagate-anchor` — 管理対象プロジェクトの `ai_ops_sha` を bump
- `ai-ops propagate-init` — 未追跡 manifest を commit
- `ai-ops propagate-files` — `[harness_files]` ハッシュを refresh
- すべて CI / スケジュール実行向けに `--auto-yes` を受け付ける

**GitHub-native エコシステム setup (ADR 0011)**
- `ai-ops setup-ci-workflow --project PATH` — drift-check workflow を追加する PR
- `ai-ops setup-codeowners --project PATH` — CODEOWNERS routing を追加する PR
- `ai-ops setup-ruleset --project PATH --tier {A,B,C}` — Repository Ruleset を適用
- `ai-ops report-drift` — 監査結果を Issue / sub-issue ライフサイクルに翻訳 (ecosystem-watch workflow から呼ばれる)

## さらに読む

トピック別:

- **AI エージェント契約と横断ポリシー** → [`AGENTS.md`](../AGENTS.md)
- **ライフサイクル deep-dive** → [`ai-first-lifecycle.md`](ai-first-lifecycle.md)
- **マルチプロジェクト監査 playbook** → [`projects-audit.md`](projects-audit.md)
- **drift 修正** → [`realignment.md`](realignment.md)
- **物理的な relocation (`~/work/...` → `~/ghq/...`)** → [`project-relocation.md`](project-relocation.md)
- **ai-ops 自身の運用** → [`self-operation.md`](self-operation.md)

設計判断 (ADR) 別:

- [0001 AGENTS.md primary](decisions/0001-agents-md-as-primary.md)
- [0002 Portability first](decisions/0002-portability-first.md)
- [0003 Deletion policy](decisions/0003-deletion-policy.md)
- [0004 Secrets management](decisions/0004-secrets-management.md)
- [0005 Nix optional reproducibility layer](decisions/0005-nix-optional-reproducibility-layer.md)
- [0006 AI-first project lifecycle](decisions/0006-ai-first-project-lifecycle.md)
- [0007 Python canonical CLI](decisions/0007-python-canonical-cli.md)
- [0008 Plan persistence](decisions/0008-plan-persistence.md)
- [0009 Git workflow tiers](decisions/0009-git-workflow-tiers.md)
- [0010 Worktree workflow](decisions/0010-worktree-workflow.md)
- [0011 GitHub-native ecosystem operation](decisions/0011-github-native-operation.md)
