# PR AI Review (二層構成)

Branch: `feat/pr-ai-review`
Worktree: `../ai-ops.pr-ai-review/`

## Purpose / Big Picture

現状、PR のレビューは以下の構成。

- **CI** (`ai-ops check` / `managed-project-check.yml`): 機械的な検査 (audit、pytest)。Tier B 以上で必須 status check。
- **人間レビュー**: Tier C のみ強制。Tier A / B は「誰も読まないままマージ」が起きうる。

これでは AGENTS.md / ADR に書かれた契約 (`Branch` / `Worktree` 命名、plan の Outcomes 完成、ADR 0010 §Lifecycle 4 遵守、harness 整合性、tier 妥当性等) を機械検査だけではカバーしきれず、人間レビュー強制も Tier C しかない。

本 plan は AI レビュー層を二層で追加する。

1. **一層目: GitHub Copilot Code Review** — 汎用コード品質、bug、セキュリティ。GitHub native。設定は使用者が行う (本 plan の対象外、運用ガイドで案内する)。
2. **二層目: `ai-ops review-pr`** — ai-ops 固有規約のレビュー。AGENTS.md / 全 ADR / harness.toml / 該当 plan を context として LLM に渡し、PR diff が規約に違反していないか、tier に整合しているか、propagate PR が anchor 以外を変更していないかを言語的に判定。Comment 投稿 + status check 反映。

加えて、AI エージェントが従うワークフローを `docs/operation.md` に明文化する。「人間が PR を起こす」ではなく「AI エージェントが規定ワークフローを自律実行し、人間は意図伝達 / Confirm / Tier C 最終承認の 3 点だけ介入する」を明示。

## Progress

- [x] (2026-05-03 03:30Z) Initial plan drafted.
- [x] (2026-05-03 03:35Z) ADR 0012 起草 (Context / Decision / Consequences、Decision Log を反映)。
- [x] (2026-05-03 03:55Z) `ai_ops/review.py` 実装 (PRContext / ReviewResult / gather_context / review_with_llm / post_pr_comment / post_status_check / run_review_pr)、`ai_ops/cli.py` に subparser + handler 追加。
- [x] (2026-05-03 04:00Z) `.github/workflows/managed-project-review.yml` 作成、`templates/artifacts/.github/workflows/ai-ops.yml` に `review` job 追加。
- [x] (2026-05-03 04:02Z) `templates/artifacts/rulesets/tier-{b,c}.json` に `ai-ops AI Review` を必須 status check として追加。Tier A は変更なし。
- [x] (2026-05-03 04:10Z) `docs/operation.md` 改訂: 「AI エージェントが従うワークフロー」section (14 ステップ + 人間介入 3 点)、責任分界表を 3 列に再構成、「PR レビュー (二層構成)」section 新設、ADR 一覧に 0012 追加。
- [x] (2026-05-03 04:12Z) AGENTS.md §Lifecycle and CLI に 14 ステップ + 3 列責任分界 + 二層レビューを明示。`ai_ops/audit/lifecycle.py` の `REQUIRED_FILES` に `docs/decisions/0012-pr-ai-review.md` / `.github/workflows/managed-project-review.yml` / `ai_ops/review.py` を追加、`README_CLAIMED_SUBCOMMANDS` に `review-pr` を追加。
- [x] (2026-05-03 04:15Z) `tests/test_review.py` 追加 (17 件 PASS): parse_response × 5 / review_with_llm × 3 / gather_context × 3 / run_review_pr × 4 / detect_plan_path × 2。
- [x] (2026-05-03 04:18Z) `python -m ai_ops check` 全パス確認 (PASS 54 / WARN 0 / FAIL 0、pytest 77 件 PASS)。
- [ ] PR 作成、CI 通過、merge、archive、worktree-cleanup。

## Surprises & Discoveries

- (作業中に追記)

## Decision Log

- Decision: LLM プロバイダは Anthropic Claude (default) と OpenAI を両方サポートする。
  Rationale: ai-ops 自身は特定ベンダーロックインを避ける方針 (ADR 0007)。Claude を default にするのは AGENTS.md と一貫した運用が確立しているため。`ANTHROPIC_API_KEY` または `OPENAI_API_KEY` を GitHub Secrets で受け、両方なければ skip (status check は neutral)。
  Date/Author: 2026-05-03 / Claude.

- Decision: `ai-ops review-pr` は GitHub API を `gh` CLI 経由で呼ぶ (`subprocess`)。
  Rationale: 既存の `propagate.py` / `report.py` が `gh` 経由で API を呼んでいる pattern を踏襲。direct REST 呼び出しは認証 / rate limit 管理の負担を増やす。`gh` は ai-ops の Tier 1 必須ツール。
  Date/Author: 2026-05-03 / Claude.

- Decision: AI レビュー結果は「PR Comment + status check」の 2 チャネルで返す。status check の context は `ai-ops AI Review`。
  Rationale: Comment だけでは ruleset で必須化できない。status check だけでは内容が見えない。両方出すことで、Comment で詳細を読み、ruleset で merge を止められる。
  Date/Author: 2026-05-03 / Claude.

- Decision: status check は「success / failure / neutral」の 3 状態。`failure` のみマージを止める。
  Rationale: AI は誤検知する。誤検知で merge を止めるのは害が大きい。明確に問題ありとした時だけ止める。`neutral` は API キーが無い / レビュー不要 (docs only PR) などの場合。
  Date/Author: 2026-05-03 / Claude.

- Decision: Tier 別必須化 — Tier A は AI レビュー任意 (Comment のみ)、Tier B は AI レビュー必須 status check、Tier C は AI レビュー + 人間レビュー両方必須。
  Rationale: Tier A は trunk-based 個人ツールなので、AI レビューが request changes でも override 可能でないと開発が止まる。Tier B は管理対象なのでブロック必須。Tier C は本番 / 公開なので二重チェック。
  Date/Author: 2026-05-03 / Claude.

- Decision: 本 PR では Copilot Code Review の有効化自体は行わない。`docs/operation.md` で「使用者が GitHub 設定で有効化する」と案内するに留める。
  Rationale: Copilot Code Review の有効化は repo 単位の GitHub UI 操作で、ai-ops が自動化すべき範囲ではない。各使用者が判断する事項。
  Date/Author: 2026-05-03 / Claude.

## Outcomes & Retrospective

ship したもの:

1. **ADR 0012** — PR 自動レビューの二層構成 (Copilot Code Review + `ai-ops review-pr`) + AI エージェント主体ワークフローを公式決定として記録。
2. **`ai-ops review-pr`** — PR diff + AGENTS.md + 全 ADR + harness.toml + 該当 plan を context として LLM (Anthropic / OpenAI) に渡し、ai-ops 固有規約への適合を言語的に判定。Comment + status check の二チャネルで結果を返す。`gh` CLI 経由で GitHub API を呼び (既存パターン踏襲)、API キー未設定時は `neutral` を返して CI を壊さない。
3. **reusable workflow `managed-project-review.yml`** — 各管理対象プロジェクトの `.github/workflows/ai-ops.yml` から `secrets: inherit` で呼ばれ、`ai-ops review-pr --pr <N>` を実行。
4. **Tier 別 ruleset 拡張** — `tier-b.json` / `tier-c.json` の `required_status_checks` に `ai-ops AI Review` を追加。Tier A は変更なし (個人ツールの開発速度維持)。
5. **`docs/operation.md` 改訂** — 「AI エージェントが従うワークフロー」14 ステップ図 + 人間介入 3 点を明文化、責任分界表を 3 列 (AI エージェント自動 / scheduled cron 自動 / 人間判断) に再構成、「PR レビュー (二層構成)」section 新設。
6. **lifecycle audit 拡張** — 新 ADR / workflow / module / subcommand を `REQUIRED_FILES` と `README_CLAIMED_SUBCOMMANDS` に登録し、drift を検出可能にした。
7. **テスト 17 件追加** — `parse_llm_response` の境界、API キーなし時のスキップ、context 組立、dry-run の挙動、投稿経路を網羅。実 API / `gh` を呼ばずに mock で完結。

残課題: なし。Copilot Code Review の有効化案内は ADR / operation.md に記述済み (各使用者の判断事項)。実 PR で `ai-ops review-pr` を動かす実地検証は本 PR のマージ後に scheduled / on-PR で行われる。

今後の plan へのフィードバック: 「人間が手を動かす」前提で書かれていた箇所を、明示的に「AI エージェントが規定ワークフローを自律実行する」前提に書き換える必要があった。今後の plan やドキュメント追記でも、主語を曖昧にせず「使用者 / AI エージェント / scheduled cron / GitHub」のどれが動くかを明記する。

## Improvement Candidates

(作業中に追記)

## Context and Orientation

- 既存 CI: `.github/workflows/ci.yml` (ai-ops 自身)、`.github/workflows/managed-project-check.yml` (reusable)、各管理対象 `.github/workflows/ai-ops.yml` (caller、`templates/artifacts/.github/workflows/ai-ops.yml` から配布)。
- 既存 ruleset: `templates/artifacts/rulesets/tier-{a,b,c}.json`。`required_status_checks` で `check` を必須化している。
- 既存 propagate / report: `ai_ops/propagate.py`、`ai_ops/report.py` が `gh` CLI 経由で GitHub API を呼ぶ pattern。
- 既存 audit lifecycle: `REQUIRED_FILES` と `README_CLAIMED_SUBCOMMANDS` で必須ファイル / コマンドを宣言。新ファイルとコマンドは追加する。
- AGENTS.md (Step 2 で 109 行に短縮済み): §Lifecycle and CLI に operation.md への pointer。

## Plan of Work

1. **ADR 0012 起草** (`docs/decisions/0012-pr-ai-review.md`): Context、Decision、Consequences。Decision Log の各項目を ADR にも反映。
2. **`ai-ops review-pr` subcommand**:
   - 入力: `--pr <N>` (PR number) または `--repo OWNER/NAME --pr <N>`。dry-run flag。
   - 動作: `gh pr view <N> --json` で PR メタ + diff、`gh api` で base ref の AGENTS.md / ADRs / harness.toml を取得、LLM に渡す。
   - 出力: `gh pr comment <N> --body` で Comment、`gh api repos/.../statuses/<sha>` で status check 投稿。
   - 実装場所: `ai_ops/review.py` (新規)、`ai_ops/cli.py` に subparser 追加。
3. **`managed-project-review.yml` reusable workflow** (`.github/workflows/`): 各管理対象の `.github/workflows/ai-ops.yml` から呼ばれる。`ai-ops review-pr --pr ${{ github.event.pull_request.number }}` を実行。`secrets: inherit` で API キーを受ける。
4. **`templates/artifacts/.github/workflows/ai-ops.yml`** 拡張: `review` job を追加 (caller workflow に既に `check` job があるので並列追加)。
5. **`templates/artifacts/rulesets/tier-{a,b,c}.json`** 拡張: Tier B / C で `ai-ops AI Review` を `required_status_checks` に追加。Tier A は変更なし。
6. **`docs/operation.md` 改訂**:
   - 新セクション「AI エージェントが従うワークフロー」(14 ステップ図 + 人間介入 3 点)。既存「マージ後の手順」をこの中に統合。
   - 責任分界表を 3 列 (AI エージェント自動 / scheduled cron 自動 / 人間判断) に再構成。
   - 「PR レビュー (二層構成)」section を新設し、Copilot 有効化案内 + `ai-ops review-pr` の挙動説明。
7. **AGENTS.md** §Lifecycle and CLI: operation.md の追加 section への pointer 1 行追記。
8. **`ai_ops/audit/lifecycle.py`**: `REQUIRED_FILES` に新ファイル追加、`README_CLAIMED_SUBCOMMANDS` に `review-pr` 追加。
9. **テスト** (`tests/test_review.py` 新規):
   - `gh` を mock。LLM API も mock (httpx 経由)。
   - PR 取得 → context 組立 → LLM 応答 parse → Comment / status check 投稿、を end-to-end で検証。
   - `--dry-run` で実際の Comment 投稿が起きないこと。
   - API キーが無い時に neutral status を投稿すること。
10. **検証**: `python -m ai_ops check` 全パス。

## Concrete Steps

```sh
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops.pr-ai-review

# 1. ADR
$EDITOR docs/decisions/0012-pr-ai-review.md

# 2. CLI 実装
$EDITOR ai_ops/review.py
$EDITOR ai_ops/cli.py

# 3-5. workflow + ruleset + caller 拡張
$EDITOR .github/workflows/managed-project-review.yml
$EDITOR templates/artifacts/.github/workflows/ai-ops.yml
$EDITOR templates/artifacts/rulesets/tier-b.json
$EDITOR templates/artifacts/rulesets/tier-c.json

# 6-8. docs + audit
$EDITOR docs/operation.md
$EDITOR AGENTS.md
$EDITOR ai_ops/audit/lifecycle.py

# 9. test
$EDITOR tests/test_review.py
python -m pytest tests/test_review.py -v

# 10. 検証
python -m ai_ops check
```

## Validation and Acceptance

- `python -m ai_ops audit lifecycle` exit 0、新 REQUIRED_FILES が check される。
- `python -m ai_ops review-pr --help` が動く (README claim verification を通る)。
- `tests/test_review.py` 全 PASS。
- `python -m ai_ops check` exit 0、pytest 全パス。
- `docs/operation.md` に「AI エージェントが従うワークフロー」section + 3 列責任分界表 + 二層レビュー section が存在。
- ADR 0012 が `docs/decisions/0012-pr-ai-review.md` に存在。
- 本 plan の Outcomes & Retrospective を埋めた状態で PR を出す (audit FAIL を起こさない)。

## Idempotence and Recovery

- LLM への呼び出しは外部副作用なし (PR Comment と status check は GitHub 上の操作だが、`--dry-run` で skip 可能)。
- ruleset 拡張は冪等 (`setup-ruleset` 自身が upsert)。
- 各ファイル変更は git revert 可能。

## Artifacts and Notes

- PR URL: TBD
- 本 PR の merge で「`ai-ops review-pr` が ai-ops repo 自身の PR にも適用される」ことを実地検証する (ai-ops 側の PR で `ai-ops review-pr --pr <N>` を Action で動かす)。

## Interfaces and Dependencies

- 新 CLI: `ai-ops review-pr [--pr N] [--repo OWNER/NAME] [--dry-run]`
- 新 reusable workflow: `tekitounix/ai-ops/.github/workflows/managed-project-review.yml@<ref>`
- 新 ADR: `docs/decisions/0012-pr-ai-review.md`
- 既存依存: `gh` (Tier 1)、`ANTHROPIC_API_KEY` または `OPENAI_API_KEY` (GitHub Secrets)
- ruleset 拡張: tier-b.json / tier-c.json に必須 status check 追加 (tier-a.json は変更なし)
