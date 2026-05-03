# Selective Review (PR ζ)

Branch: `feat/selective-review`
Worktree: `../ai-ops.selective-review/`

## Purpose / Big Picture

ユーザーの根本的な問い直し: 「AI 駆動で AI エージェントが作業するのだから、セルフレビューで済ませた方がコンテキストが十分にあって良い。external API レビューは補助 (セカンドオピニオン) にすべきで、利用判断やモデル選定もエージェントが行うべき」。

現状の設計は **「全 PR を external API でレビュー」= 強制** で、2 つの歪み:
1. エージェント自身が完全な context (作業中の試行錯誤、Brief、Decision Log すべて) を持っているのに、context 限定の external (AGENTS.md + ADR + diff のみ) を「正本」にするのは情報損失。
2. 「AI 駆動」と「外部 AI に refee を頼む」は意味が違う — 後者は「自分では判断しきれない時のセカンドオピニオン」であるべき。

本 PR は AI レビューを **3 層構造** に再設計する:

```
Layer 1: エージェントによるセルフレビュー (必須・無料・context 完全)
Layer 2: 条件付き external review (判断・有料・context 限定、エージェントが呼ぶか決める)
Layer 3: 人間レビュー (Tier C のみ強制)
```

加えて cost 制御 (per-PR / monthly cap、skip pattern、model 選択) を整備し、CI 自動 review の role を「強制」から「optional second opinion」に変える。動作テストは ai-ops 自身 (本 PR で実演) + ai-ops-managed-test (E2E) で行う。

## Progress

- [x] (2026-05-03 12:00Z) Initial plan drafted (selective + self-review-first 設計)。
- [x] (2026-05-03 12:30Z) A+B: `ReviewConfig` dataclass、`_load_review_config` (toml + env、`[review_budget]` legacy backward compat)、`_check_skip_patterns` (label fnmatch + path PurePath.match で `**` 対応)、`_choose_model_auto` (security/critical → opus / docs+small → haiku / else → sonnet)、`review_with_llm` に `model_override` / `pr_labels` 追加、per-PR cap 警告は cost footer 末尾に。
- [x] (2026-05-03 12:35Z) C: docs/operation.md の AI ワークフロー 14 step を 3 層レビュー対応に改訂、§3 層レビュー section + harness.toml [review] schema 例を追加。ADR 0012 に Amendment 2026-05-03 (PR ζ) を追記 (強制→補助、tier 別 default、model heuristic、cost 制御)。
- [x] (2026-05-03 12:38Z) D: `.github/workflows/ci.yml` の `review` job を label trigger 化 (`contains(pull_request.labels.*.name, 'review:request')`)。
- [x] (2026-05-03 12:40Z) E: `.github/PULL_REQUEST_TEMPLATE.md` 新規 (Summary / Self-review checklist / External review needed? / Test plan)。
- [x] (2026-05-03 12:42Z) F: `.ai-ops/harness.toml` に `[review]` block 追加 (enabled / monthly $2 / per_pr $0.15 / sonnet default / skip patterns / on_label)。
- [x] (2026-05-03 12:50Z) G: テスト 8 件追加 + 既存 3 件を新シグネチャ追従 (合計 263 PASS、smoke 2 件 skip)。
- [x] (2026-05-03 12:52Z) H1: `python -m ai_ops check` 全パス。
- [ ] H2: PR 作成 → label `review:request` 付与で external review 実走確認 → merge → auto-archive。
- [ ] I: ai-ops-managed-test で E2E (別 step、本 PR merge 後)。

## Surprises & Discoveries

- (作業中に追記)

## Decision Log

- Decision: 3 層構造 (self → optional external → human Tier C)。external は強制から判断へ。
  Rationale: エージェント自身の context が最大の情報源。external は補助の位置付けが本来。
  Date/Author: 2026-05-03 / Claude.

- Decision: ai-ops 自身の CI review job は default で skip。ローカル / label trigger で呼ぶ。
  Rationale: ai-ops は Tier A、本人が直接エージェントに指示しているので self-review が常に走る。CI で別途 external を強制する必要なし。コスト削減と一致。
  Date/Author: 2026-05-03 / Claude.

- Decision: 管理対象プロジェクトの review job は tier 別で default を変える: A=off, B=on (label で skip 可), C=on (override 不可)。
  Rationale: tier ごとに self-review への信頼度が違う。Tier C は本番なので external + 人間で二重チェック。
  Date/Author: 2026-05-03 / Claude.

- Decision: model 選定はエージェントの判断に委ね、`--model auto` で PR 規模 / label に基づく heuristic を組み込む。
  Rationale: 固定 default は機械的すぎる。エージェントが「この PR は規約 chk 中心 → Haiku」「セキュリティ critical → Opus」と動的選択できる柔軟性が必要。
  Date/Author: 2026-05-03 / Claude.

- Decision: PR template (`.github/PULL_REQUEST_TEMPLATE.md`) で `## Self-review` section を必須化、エージェントが 3-5 行で「規約遵守を自分で確認した観点」を埋める。
  Rationale: self-review を「機械強制」する手段。template が空なら GitHub UI の検証ではないが、エージェントへの強い signal になる。将来 audit で「PR description に Self-review section があるか」を verify する可能性あり。
  Date/Author: 2026-05-03 / Claude.

- Decision: per-PR cap と monthly cap は両方持つ。default は per-PR $0.15 / monthly $2.0。
  Rationale: per-PR は Sonnet 1 PR の暴走防止 (実測 $0.05 → $0.15 で 3× margin)。monthly は累積暴走防止 (月 13 PR 相当)。Opus を使う PR は per-PR $0.50 程度になるので、必要な PR では使用者が cap を一時的に上げる judgment。
  Date/Author: 2026-05-03 / Claude.

## Outcomes & Retrospective

ship したもの (PR ζ):

1. **3 層レビュー** (Self → optional External → Tier C Human) を ADR 0012 amendment + docs/operation.md で正式化。external は強制から「セカンドオピニオン」に再定義。
2. **`harness.toml::[review]` schema**: `enabled` / `monthly_usd_limit` / `per_pr_usd_limit` / `default_model` / `skip_label_patterns` / `skip_path_patterns` / `on_label` を 1 section に集約。`[review_budget]` (PR ε) は backward compat alias で読む。env var (`AI_OPS_REVIEW_BUDGET_USD_MONTH` / `AI_OPS_REVIEW_ENABLED`) で上書き可。
3. **review.py の judgement 拡張**:
   - skip patterns (label = fnmatch、path = `pathlib.PurePath.match` で `**` 対応)
   - model 選定 (`--model` flag + `auto` heuristic: security label/big diff → opus、docs label/small → haiku、else → sonnet)
   - per-PR cap 超過時に cost footer 末尾に警告 (cost 自体は既に発生しているので skip にはしない、次回 cap 見直しを促す)
   - master switch (`enabled = false`) で全 review skip
4. **CI workflow の role 変更**: ai-ops 自身の `.github/workflows/ci.yml` の `review` job を label trigger 化 (default off、`review:request` label 付与時のみ実走)。
5. **PR template** (`.github/PULL_REQUEST_TEMPLATE.md`): Summary / Self-review checklist (5 項目) / External review needed? / Test plan を含む。エージェントが PR description を埋めるとき自然に self-review checklist を踏む。
6. **ai-ops 自身に `[review]` 設定**: `.ai-ops/harness.toml` で sonnet default、月 $2 / PR $0.15 cap、archive plan と lock file は skip。
7. **テスト 11 件追加** (合計 263 件 PASS、smoke 2 件 skip): config 読取 (full block + legacy fallback)、disabled skip、label skip、path skip (全 match / 部分 match)、model auto heuristic 各分岐、_choose_model_auto。

### 設計の本質

| Layer | 主体 | コスト | 強制度 | context |
|---|---|---|---|---|
| Self-review | 作業中エージェント | 0 | 必須 | 完全 (Brief / 試行錯誤 / Decision Log) |
| External | `ai-ops review-pr` | $0.005-0.10/PR | 判断 | 限定 (AGENTS.md + ADR + diff) |
| Human | 使用者 | 0 | Tier C 強制 | 必要に応じて |

「context が完全な」self を一次レビュー、「context は限定だが bias の少ない外部」を二次に置く。ai-ops 自身は Tier A なので external は label trigger のみ → 月数件、コスト < $0.50。

### コスト効果見積もり

| シナリオ | 月コスト |
|---|---|
| 旧設計 (全 PR で external) | $1-2/月 |
| 新設計 (label trigger のみ) | $0.05-0.30/月 (80-95% 削減) |
| 暴走時 (月 100 PR が間違って all label 付き) | $2 で hard cap、それ以上は neutral skip |

### 残課題

- I (E2E in ai-ops-managed-test) は本 PR merge 後の別 step で実施
- model 選定 heuristic は label ベース → 将来 diff content / 規模 をより細かく見る余地
- `audit security` で `[review]` の整合性 (例: `monthly_usd_limit < per_pr_usd_limit` だと矛盾) を検査する余地

### 今後の plan へのフィードバック

- 設計再検討の問い直し (「AI 駆動なら self-review が一次」) は本質的だった。「機能 vs 補助」の関係を見直すと自然な形に収まる。
- 同じ機能を「強制」から「判断」に変えるだけで複雑性は増えず、むしろ「呼ぶべき heuristics」を docs に残せて知識が貯まる。
- `harness.toml` に既存 `[review_budget]` を残しつつ `[review]` を新設、両方読む backward compat は短い regex 1 つで実現。schema 拡張時は既存設定を 1 リリース残すのが basic stance。

## Improvement Candidates

(作業中に追記)

## Context and Orientation

- 既存 `ai_ops/review.py`: PR ε で monthly cap 追加、cost cache 実装済み。`provider` flag は auto/anthropic/openai。
- 既存 CI workflow: ai-ops `.github/workflows/ci.yml` の `review` job は `continue-on-error: true` で常時実行。`templates/artifacts/.github/workflows/ai-ops.yml` の caller workflow も同様。
- `harness.toml`: 既存は `ai_ops_sha`、`workflow_tier`、`[harness_files]`、`[project_checks]`、`[review_budget]` (PR ε で追加)。本 PR では `[review_budget]` を `[review]` に拡張統合。
- `ai_ops/audit/projects.py` の `recommended_tier`: PR γ で追加、PR ε で table 表示。
- AGENTS.md / docs/operation.md: PR α-ε で AI ワークフロー 14 step を明文化済み。
- 既存テスト: `tests/test_review.py` 27 件 + cache / budget テスト。

## Plan of Work

### A. harness.toml::[review] schema 拡張

`[review_budget]` を `[review]` に発展させる:

```toml
[review]
# Master switch — false で全 review を skip (CI / ローカル両方)
enabled = true

# Cost caps
monthly_usd_limit = 2.0
per_pr_usd_limit = 0.15

# Default model (エージェントが --model auto で override 可)
# 候補: claude-haiku-4-5-20251001 / claude-sonnet-4-6 / claude-opus-4-7 / gpt-4o-mini / gpt-4o
default_model = "claude-sonnet-4-6"

# Skip 条件 (どれか一つでも match すれば review を skip)
skip_label_patterns = ["no-review", "skip-ai", "review:skip"]
skip_path_patterns = ["**/*.lock", "docs/plans/archive/**"]

# CI workflow を強制起動するには label をつける
on_label = "review:request"
```

`[review_budget]` (PR ε) は backward-compat のため alias として読む (deprecation 警告)。

### B. review.py の judgement

- `_load_review_config(cwd) → ReviewConfig` を新設、`[review]` を読む。`[review_budget]` も読んで merge (backward compat)。
- `review_with_llm` の冒頭で:
  - `enabled = false` なら neutral skip
  - `_check_skip_patterns(ctx, config)` で skip 判定
  - per-PR cap: 過去の cost cache から「同 PR の前回 cost」を見て、もし cap を超えていたら skip
  - model 選定: `--model` で指定された値 > config の default_model > Sonnet
- `_choose_model_auto(ctx)`: PR 規模 / label に基づく heuristic
  - diff < 500 lines + label に「docs」「style」を含む → haiku
  - diff > 5000 lines or label に「security」「critical」 → opus
  - それ以外 → sonnet

### C. AGENTS.md / docs/operation.md / ADR 0012

AGENTS.md §Lifecycle and CLI に「セルフレビュー必須」を追記。

docs/operation.md の 14 step ワークフロー (Step ⑥ → ⑦ → ⑧ → ⑨) を 3 層レビューに改訂:

```
⑥ ai-ops check (機械検査)
⑦ Self-review: エージェントが規約遵守を自分で確認 (必須)
⑧ External review (条件付き): エージェントが「セカンドオピニオン必要」と判断したら呼ぶ
⑨ commit + PR (Self-review 結果を PR description に含める)
⑩ CI 待ち
⑪ AI レビュー待ち (CI 設定により)
⑫ Tier C 人間レビュー
```

ADR 0012 に Amendment 2026-05-03 (PR ζ): 強制 → 補助の位置付け変更を記録。

### D. CI workflow

`.github/workflows/ci.yml` の `review` job: `if: contains(github.event.pull_request.labels.*.name, 'review:request')` で label trigger 化。

`templates/artifacts/.github/workflows/ai-ops.yml`: `[review].enabled` を harness.toml から読む条件分岐 (これは pip install 後の `ai-ops review-pr` 自身の判断に委ねる、workflow 自体は実行)。

### E. PR template

`.github/PULL_REQUEST_TEMPLATE.md` 新規:

```markdown
## Summary
<1-3 lines>

## Self-review (ADR 0012 / PR ζ)
- [ ] AGENTS.md / 関連 ADR の規約に従っている
- [ ] plan.md の Outcomes が完成している (Progress 完了時)
- [ ] propagate / setup / 横断的編集なら scope を超えていない
- [ ] 関連テストが pass している
- [ ] (security / secret 関連の場合) ADR 0004 5 原則を満たしている

## External review needed?
<yes/no と理由 1 行。yes の場合は label `review:request` を付与>

## Test plan
- [ ] ...
```

### F. ai-ops 自身に harness.toml [review]

`.ai-ops/harness.toml` (もし無ければ新規作成):

```toml
ai_ops_sha = "<latest>"
workflow_tier = "A"

[review]
enabled = true                # CI default は label trigger だが、ローカル呼び出しは可
monthly_usd_limit = 2.0
per_pr_usd_limit = 0.15
default_model = "claude-sonnet-4-6"
skip_label_patterns = ["no-review", "skip-ai", "review:skip"]
skip_path_patterns = ["docs/plans/archive/**", "**/*.lock"]
on_label = "review:request"
```

### G. テスト

- `tests/test_review.py` に 6 件追加: enabled false で skip / skip_label / skip_path / per_pr_cap / model auto / config 読取
- `tests/test_audit.py` の `recommended_tier` 系は影響なし

### H. ai-ops check + PR + merge

検証 → push → PR (本 PR は label `review:request` を付けて external 実走確認) → merge → auto-archive

### I. ai-ops-managed-test E2E

別 step (本 PR とは独立に):
1. `cd ~/ghq/github.com/tekitounix/ai-ops-managed-test`
2. `ai-ops bootstrap --with-secrets --repo tekitounix/ai-ops-managed-test --bw-anthropic-item anthropic-api-key-for-review`
3. `ai-ops setup ci --project . --tier B`
4. `ai-ops setup ruleset --project . --tier B`
5. `ai-ops setup codeowners --project .`
6. 適当な小修正 PR (README に 1 行) → CI で `audit harness` + (label つけたら) review が動くか確認
7. 結果を PR ζ の Outcomes に追記

## Concrete Steps

```sh
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops.selective-review

# A-B. schema + judgement
$EDITOR ai_ops/review.py

# C. docs
$EDITOR AGENTS.md docs/operation.md docs/decisions/0012-pr-ai-review.md

# D. CI workflow
$EDITOR .github/workflows/ci.yml templates/artifacts/.github/workflows/ai-ops.yml

# E. PR template
$EDITOR .github/PULL_REQUEST_TEMPLATE.md

# F. ai-ops self harness
$EDITOR .ai-ops/harness.toml  # 新規

# G. test
$EDITOR tests/test_review.py

# H. 検証 + commit
python -m ai_ops check
git add -A && git commit -m "feat(review): 3-layer review (self + optional external + human) (PR ζ)"
git push -u origin feat/selective-review
gh pr create --label review:request ...

# I. E2E (別セッション)
cd ~/ghq/github.com/tekitounix/ai-ops-managed-test
# ... E2E 手順
```

## Validation and Acceptance

- `python -m ai_ops check` exit 0
- pytest 254 + 新規 6 = 260 PASS
- 本 PR を `review:request` label 付きで開くと CI で external review 実走 (実 cost 確認、cap 内)
- ai-ops `.ai-ops/harness.toml` が存在し `[review]` block を含む
- `.github/PULL_REQUEST_TEMPLATE.md` が存在し Self-review section がある
- ai-ops-managed-test で 1 件の小修正 PR を立てて managed-project-{check,review}.yml が動く

## Idempotence and Recovery

- すべて git revert 可能
- ai-ops 自身の `.ai-ops/harness.toml` 新規作成は破壊的でない
- CI workflow の label trigger 化は backward-compat (label を常時付ければ既存挙動)

## Artifacts and Notes

- PR URL: TBD
- AI レビュー結果: TBD (label trigger で実走予定)
- ai-ops-managed-test の E2E 結果: TBD

## Interfaces and Dependencies

- 新 schema: `harness.toml::[review]` (PR ε の `[review_budget]` を統合、deprecation 警告で alias)
- 新 file: `.github/PULL_REQUEST_TEMPLATE.md`、`.ai-ops/harness.toml` (ai-ops 自身)
- 既存拡張: `ai_ops/review.py`、AGENTS.md、`docs/operation.md`、ADR 0012、CI workflows
- 動作テスト依存: `~/ghq/github.com/tekitounix/ai-ops-managed-test` repo (既存)
