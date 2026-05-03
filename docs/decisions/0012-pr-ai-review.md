# ADR 0012: PR 自動レビュー (二層構成 + AI エージェント主体ワークフロー)

> Status: Accepted
> Date: 2026-05-03

## Context

ADR 0011 で「PR は通知、Issue は work tracker、Project board は dashboard」という GitHub-native な運用基盤を確立した。CI 必須化 (Tier B+) と人間レビュー必須化 (Tier C のみ) も整備済み。

しかし以下の穴が残っている。

1. **Tier A / B では人間レビューが任意**、CI が通れば誰も読まずにマージされる PR が生まれる。
2. **CI で機械検査できる範囲には限界がある**。AGENTS.md / 全 ADR / harness.toml で宣言された契約 — 例えば「propagate PR は anchor 以外を変更してはならない」「branch 命名は `<type>/<slug>` でなければならない」「plan の Outcomes が完成している」— は audit で部分的に検査できているが、PR 全体としての規約遵守を言語的に判定する層が無い。
3. **人間レビューに依存しても規約遵守の品質は人間の集中力次第**。同じレビュアーが何度も同じ点を指摘する非効率が積もる。

加えて、運用主体に関する誤った前提が混じっていた: ワークフロー文書に「人間が `worktree-new` で開始」と書いていたが、実際は使用者が自然言語で意図を伝え、AI エージェントがワークフローを自律実行する流れ。AI エージェントが規定ワークフローに従うことを明文化しないと、エージェントごとに振る舞いがブレる。

外部状況 (2026 年 5 月時点):

- **GitHub Copilot Code Review** が GA。PR review に LLM ベースで Comment を残す。Copilot サブスク必須、カスタマイズは限定的。
- **PR 自動レビューの自前実装** は CodeRabbit / Greptile / Aider review 等が普及。Copilot にない強みは「repo 固有の規約 / 設計判断を context として渡せる」点。
- **GitHub Actions の status check** は ruleset の `required_status_checks` で必須化できる。Comment / status check の二チャネル投稿が標準。

## Decision

PR レビューを **二層構成** で実装し、AI エージェント主体ワークフローを `docs/operation.md` に明文化する。

### 二層構成

**一層目: GitHub Copilot Code Review** (有効化案内のみ、自動化対象外)

- 汎用コード品質、bug、セキュリティを native にレビュー。Copilot サブスク使用者が GitHub UI で repo ごとに有効化する。
- ai-ops は repo 設定の自動操作を行わない (使用者判断)。`docs/operation.md` で有効化方法を案内。

**二層目: `ai-ops review-pr`** (新規 subcommand + reusable workflow)

- ai-ops 固有の規約レビューを担当。
- 入力: PR 番号 + repo (default は cwd の origin)。
- Context: PR diff + base ref の AGENTS.md + 全 ADR + (該当 plan があれば) plan.md + harness.toml。
- 判定対象 (例):
  - branch 命名が `<type>/<slug>` か
  - plan の Branch / Worktree / Plan path フィールドと branch 名が一致しているか
  - plan の Outcomes が PR 時点で完成しているか (audit でも検査するが言語的にも確認)
  - propagate PR が宣言した scope (anchor / init / files) を超えていないか
  - tier 宣言と PR 内容が整合しているか (例: Tier A 宣言なのに reviewer 必須を要求していないか)
  - ADR 0010 §Lifecycle 4 (マージ後手順) の前提を破っていないか
- 出力 (二チャネル):
  - PR Comment (詳細を Markdown で投稿、`gh pr comment`)
  - Status check (`ai-ops AI Review` という context で `success` / `failure` / `neutral`、`gh api repos/.../statuses/<sha>`)
- LLM プロバイダ: Anthropic Claude (default) または OpenAI。`ANTHROPIC_API_KEY` または `OPENAI_API_KEY` を GitHub Secrets で受ける。両方無ければ `neutral` を投稿して exit 0 (skip)。
- API 呼び出しは `gh` CLI 経由 (既存 `propagate.py` / `report.py` パターン踏襲)。
- ローカル実行サポート: `ai-ops review-pr --pr <N> [--dry-run]` で開発時にも回せる。

### Tier 別必須化

`templates/artifacts/rulesets/tier-{a,b,c}.json` を拡張:

- **Tier A**: AI レビュー任意 (Comment 投稿はするが status check は ruleset 対象外)。trunk-based 個人ツールの開発速度を維持。
- **Tier B**: AI レビュー必須 status check (`ai-ops AI Review`)。
- **Tier C**: AI レビュー必須 + 人間レビュー必須 (既存)。

### AI エージェント主体ワークフローの明文化

`docs/operation.md` に以下を追加。

1. 「AI エージェントが従うワークフロー」(14 ステップ図、人間介入は意図伝達 / Confirm / Tier C 最終承認の 3 点)。
2. 責任分界表を 3 列に再構成: AI エージェント自動 / scheduled cron 自動 / 人間判断。
3. 「PR レビュー (二層構成)」セクション: 一層目の有効化案内、二層目の挙動と Tier 別必須化。

これにより「人間が手を動かす」前提でなく「AI エージェントが規定ワークフローを実行する」前提で全体が組み立てられる。

### 配布

- `templates/artifacts/.github/workflows/ai-ops.yml` に `review` job を追加。
- 新 reusable workflow `tekitounix/ai-ops/.github/workflows/managed-project-review.yml`。
- `setup-ci-workflow` は変更なし (caller workflow が新 job を持つだけなので templates の更新で配布される)。
- `setup-ruleset` は ruleset JSON を読むので、template 更新だけで Tier B / C の必須化が伝わる。

## Consequences

肯定的:

- Tier A / B でも AI レビュー層が入るので、人間レビューに頼らずに規約遵守を機械的に担保できる。
- Copilot Code Review (汎用) と `ai-ops review-pr` (規約特化) が役割分担できる。重複しない。
- AI エージェントが従うワークフローが文書化され、エージェント間 (Claude Code / Codex / Cursor) のブレが減る。
- ruleset で Tier 別に必須化レベルを変えられるので、開発速度を犠牲にしない。

否定的:

- LLM API コストが発生 (Anthropic / OpenAI)。週次 cron + on-PR で月数十ドル想定。Secrets 管理が必要。
- LLM の誤検知リスク。`failure` 判定だけ status check を fail にし、`neutral` で skip 可能にして緩衝。
- ai-ops 自身のメンテナンス対象が増える (review.py + reusable workflow + ADR + テスト)。

スコープ外 (将来検討):

- GitHub Copilot Cloud Coding Agent (Issue → autonomous PR、Pro+ plan 必須) は v1 では対応しない。
- レビュー結果のフィードバックループ (誤検知を学習する) は将来の改善候補。今は単発レビューのみ。
- 多言語 LLM プロバイダ (Gemini / DeepSeek 等) は追加要望が出たら拡張。

## 関連

- ADR 0009: workflow tier
- ADR 0010: worktree workflow
- ADR 0011: GitHub-native ecosystem operation
- 外部: GitHub Copilot Code Review GA (2025 Q4)、Repository Rulesets GA (2025 Q3)、`gh api repos/.../statuses` REST endpoint。

## Amendment 2026-05-03 (PR δ)

本 ADR 本文中の `ai-ops setup-ci-workflow` 等は執筆時点の subcommand 名。PR α (2026-05-03) で `ai-ops setup {ci,codeowners,ruleset}` に統合された (旧名は 1 リリース alias)。本 ADR の Decision 自体には影響なし。

## Amendment 2026-05-03 (PR ζ): 強制 → 補助 + 3 層構造

PR ε までの設計は「全 PR に external review (`ai-ops review-pr`) を強制」だったが、根本的な問い直し: AI 駆動で AI エージェントが作業しているのに、context 限定の external (AGENTS.md + ADR + diff) を「正本」にするのは情報損失。external review は本来「セカンドオピニオン」であるべき。

### 新 3 層構造

1. **Self-review (必須・無料・context 完全)**: PR 提出前にエージェント自身が変更を読み返し規約遵守を確認する。エージェントの context (作業中の試行錯誤、Brief、Decision Log) が最大の情報源。
2. **External review (条件付き・有料・context 限定)**: エージェントが「セカンドオピニオン要」と判断したら呼ぶ。`ai-ops review-pr --pr <N> --model auto` で PR 規模 / label に基づき haiku / sonnet / opus を選ぶ。
3. **Human review (Tier C 強制)**: 既存。

### CI workflow の role 変更

- ai-ops 自身 / Tier A: default off、label `review:request` で trigger
- Tier B: default on、label `review:skip` で個別 opt-out
- Tier C: 強制

### Cost 制御 (`harness.toml::[review]`)

`enabled` / `monthly_usd_limit` / `per_pr_usd_limit` / `default_model` / `skip_label_patterns` / `skip_path_patterns` / `on_label` を 1 section に集約 (`[review_budget]` は backward compat alias)。env var `AI_OPS_REVIEW_BUDGET_USD_MONTH` / `AI_OPS_REVIEW_ENABLED` で override 可。

### model 選定 heuristic (`--model auto`)

- "security" / "critical" label OR diff > 5000 lines → opus
- "docs" / "style" / "chore" label AND diff < 500 lines → haiku
- それ以外 → sonnet (default_model 指定時はそれ)

### Self-review の機械強制

`.github/PULL_REQUEST_TEMPLATE.md` に `## Self-review` section を含めることで、エージェントが PR description を埋める時に自然に self-review checklist を踏むようにする。
