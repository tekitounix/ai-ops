# GitHub-native ecosystem operation

ADR 0011 を実装するプラン。ai-ops の運用全体を GitHub Issues / Projects v2 / scheduled Actions / reusable workflows / Rulesets / CODEOWNERS の上に再構築する。

Plan path: `docs/plans/github-native-operation/plan.md`。Branch: `feat/github-native-operation`。Worktree: `../ai-ops.github-native-operation/`。

## Purpose / Big Picture

ADR 0011 全 6 move の実装。完了後の到達点:

- ai-ops repo に Project v2 board "Ecosystem" + 各 managed project の parent issue + drift sub-issues
- weekly cron で `ecosystem-watch` が drift 検出 → sub-issue 自動更新 → user の GitHub Notifications に通知
- weekly cron で `propagate-cron` が `propagate-* --auto-yes` 実行 → 各 project に PR 自動配信
- 各 managed project が `.github/workflows/ai-ops.yml`(reusable workflow caller)+ `.github/CODEOWNERS` + `gh api` 適用済み tier ruleset を持つ
- `audit projects` に `has_ai_ops_workflow` / `has_codeowners_routing` / `has_tier_ruleset` signal が追加され、配備状況が一目で分かる
- test project `tekitounix/ai-ops-managed-test` で end-to-end validation 済み

## Progress

- [x] (2026-05-02 17:30Z) ADR 0011 起票、本プラン作成、worktree-new で feat/github-native-operation 隔離環境作成。
- [ ] `--auto-yes` flag を `propagate-anchor` / `propagate-init` / `propagate-files` に追加(CI 実行用、stdin 待ちを skip)
- [ ] `ai_ops/report.py` 新規: `report-drift` サブコマンド(audit projects → sub-issue 操作)
- [ ] `.github/workflows/ecosystem-watch.yml` (ai-ops 自身、weekly + manual)
- [ ] `.github/workflows/propagate-cron.yml` (ai-ops 自身、weekly + manual)
- [ ] `.github/workflows/managed-project-check.yml` (ai-ops 自身、reusable workflow)
- [ ] `templates/artifacts/.github/workflows/ai-ops.yml` (各 project が caller として配置するもの)
- [ ] `templates/artifacts/CODEOWNERS.template`
- [ ] `templates/artifacts/rulesets/{tier-a,tier-b,tier-c}.json`
- [ ] `ai_ops/setup.py` 新規: `setup-ci-workflow` / `setup-codeowners` / `setup-ruleset` ハンドラ
- [ ] CLI 統合: 4 つの新 subcommand 追加(report-drift / setup-ci-workflow / setup-codeowners / setup-ruleset)
- [ ] `ai_ops/audit/projects.py` に 3 signal 追加(has_ai_ops_workflow / has_codeowners_routing / has_tier_ruleset)
- [ ] tests: report、setup、audit signal、--auto-yes 動作
- [ ] lifecycle audit の REQUIRED_FILES + README claims 更新
- [ ] AGENTS.md / README.md / docs (self-operation, realignment, projects-audit) 更新
- [ ] Project v2 board 作成 (`gh project create` 経由、ai-ops repo 内)
- [ ] test project 作成: `gh repo create tekitounix/ai-ops-managed-test --private`
- [ ] test project に対して全 layer を適用、end-to-end 動作確認
- [ ] PR を立てる: `gh pr create` で feat/github-native-operation → main
- [ ] self-review、CI green、merge
- [ ] マージ後 `ai-ops worktree-cleanup` で本 worktree を削除、本プランを archive

## Surprises & Discoveries

- Observation: GitHub の reusable workflow は呼び出し repo に対して限定的なコンテキストしか渡せない(secrets は明示 inheritance、env vars は限定)。
  Evidence: GitHub Actions docs。
  Implication: `managed-project-check.yml` は `tier` を input で受け取り、tier に応じた挙動を内部で分岐。

- Observation: `gh api repos/.../rulesets` POST は ruleset を新規作成、PUT は更新。同名 ruleset の upsert ロジックが必要。
  Evidence: GitHub REST API docs。
  Implication: `setup-ruleset` 内で「同名 ruleset があれば PUT、無ければ POST」を実装。

- Observation: Sub-issue API は GraphQL のみで、REST にはまだ無い。
  Evidence: GitHub Sub-issues docs。
  Implication: `report-drift` の sub-issue 作成は `gh api graphql` で実施。

## Decision Log

- Decision: 全実装を本 worktree (`feat/github-native-operation` branch) で進め、最後に PR としてマージする。
  Rationale: ADR 0010 の dogfood、変更が大きいので self-review の余地を残す。
  Date/Author: 2026-05-02 / Codex

- Decision: test project は `tekitounix/ai-ops-managed-test` private repo を `gh repo create` で新規作成。
  Rationale: 既存 managed project への破壊的テストは禁忌。validation repo (`~/ghq/local/...`) は GitHub に無いため Actions / Issues が試せない。
  Date/Author: 2026-05-02 / Codex

- Decision: `--auto-yes` flag は per-project confirmation を skip するが、その許可は workflow ファイル自体を user が cron で run するという Operation Model 上の "事前提示一括承認" と解釈。
  Rationale: cron で動かす propagate-* はインタラクティブにできない。workflow ファイルの review でユーザーが事前承認したと見做す。
  Date/Author: 2026-05-02 / Codex

- Decision: `setup-ci-workflow` / `setup-codeowners` / `setup-ruleset` は 3 つの個別 subcommand。
  Rationale: 各 setup は独立した粒度の操作で、user が部分採用したい場合がある。
  Date/Author: 2026-05-02 / Codex

- Decision: Sub-issue 作成は GraphQL 経由、parent issue は project 名 + label `ecosystem` で識別。1 project = 1 parent issue。
  Rationale: GraphQL は sub-issue API の唯一の手段。
  Date/Author: 2026-05-02 / Codex

- Decision: ai-ops 自身のバージョン pinning は workflow 内で `@v1` のような major version tag を使う。
  Rationale: 自分自身が source。SHA pinning は別 repo から呼ぶときの厳密化要件。
  Date/Author: 2026-05-02 / Codex

- Decision: Copilot Coding Agent integration は本プランの out of scope。
  Rationale: Pro+ plan 必須かつ user の plan が未確認。optional な enhancement。
  Date/Author: 2026-05-02 / Codex

## Outcomes & Retrospective

TBD。

## Improvement Candidates

### `setup-managed --tier <X>` 統合 helper

- Observation: 3 つの setup-* を順に呼ぶ手間。1 コマンドで全部適用したい。
- Evidence: 本プラン Decision Log。
- Recommended adoption target: `deferred`
- Confirmation needed: no — 既存 helper を呼ぶラッパー。
- Verification: 実 use で「3 つを順に呼ぶ手間」が painful になったら追加。
- Disposition: deferred — まず個別 helper で運用、需要を確認。

### Auto-merge for `propagate-*` PRs

- Observation: Renovate-style auto-merge for trivial drift (例: SHA bump only)。
- Evidence: ADR 0011 の Out of scope。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — auto-merge は test coverage 前提。
- Verification: managed project の PR 量が増えて手動 merge が painful になったら検討。
- Disposition: deferred。

### Copilot Coding Agent integration

- Observation: Issue を Copilot に assign して autonomous PR 生成。
- Evidence: GitHub Copilot Cloud Agent 公式 docs。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — Pro+ plan 必須。
- Verification: user が Pro+ を持っていて、かつ「routine drift remediation を Copilot に任せたい」と判断したら検討。
- Disposition: deferred。

### Webhook-based real-time notification

- Observation: cron は最大 1 週間の遅延。webhook で push base にすればリアルタイム。
- Evidence: GitHub webhook docs。
- Recommended adoption target: `rejected`
- Confirmation needed: no — drift は rarely 時間 critical。
- Verification: n/a
- Disposition: rejected — over-engineering。

## Context and Orientation

- `ai_ops/propagate.py` — `--auto-yes` flag を 3 propagator に追加
- `ai_ops/report.py` (new) — sub-issue lifecycle 管理
- `ai_ops/setup.py` (new) — 3 setup-* helper
- `ai_ops/audit/projects.py` — 3 signal 追加
- `templates/artifacts/.github/workflows/ai-ops.yml` (new)
- `templates/artifacts/CODEOWNERS.template` (new)
- `templates/artifacts/rulesets/*.json` (new)
- `.github/workflows/ecosystem-watch.yml` (new)
- `.github/workflows/propagate-cron.yml` (new)
- `.github/workflows/managed-project-check.yml` (new, reusable)
- ai-ops 自身の Project v2 board (作成は手動 / `gh project create`)
- test project: `tekitounix/ai-ops-managed-test` (新規 private)

## Plan of Work

1. `--auto-yes` flag を `propagate-anchor` / `propagate-init` / `propagate-files` に追加。tests 拡張。
2. `ai_ops/report.py` 実装。
3. `ai_ops/setup.py` 実装。
4. CLI 統合: 4 新 subcommand。
5. `ProjectSignals` に 3 signal 追加。
6. ai-ops 自身の `.github/workflows/` に 3 workflow 追加。
7. `templates/artifacts/` に各 project 用 artifact 配置。
8. tests。
9. docs 更新。
10. test project 作成 + end-to-end 試験。
11. local check + commit + push from worktree branch。
12. PR open、CI watch、self-review + merge。
13. マージ後 worktree cleanup + plan archive。

## Concrete Steps

```sh
# 全作業は worktree 内
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops.github-native-operation

# 実装後
python -m ai_ops check
git diff --check

# test project 作成
gh repo create tekitounix/ai-ops-managed-test --private --add-readme

# end-to-end test
python -m ai_ops setup-ci-workflow --project /tmp/test-clone-of-managed-test/

# PR
git push -u origin feat/github-native-operation
gh pr create --title "feat: GitHub-native ecosystem operation" --body "..."
gh pr checks
gh pr merge --squash --delete-branch
```

## Validation and Acceptance

### Machine-checkable

- 4 新 subcommand が `--help` に応答
- 3 propagator に `--auto-yes` flag が存在
- `ProjectSignals` に 3 新 field
- `.github/workflows/` 3 新 workflow ファイル存在
- `templates/artifacts/` に新 artifact (workflow / CODEOWNERS / ruleset JSON × 3)
- tests 全 pass
- `ai-ops check` PASS、CI 全ジョブ green

### Human-reviewable

- ADR 0011 が現代 GitHub 機能を網羅し、設計理由が明確
- test project に対して 4 setup helper が動作、PR が生成される
- ecosystem-watch が drift を検出し sub-issue を作成する(workflow_dispatch で手動実行で確認)
- propagate-cron が propagate-* を `--auto-yes` で動作させる
- managed-project-check (reusable) が呼び出し側 workflow から正しく動作

## Out of Scope

- Copilot Coding Agent integration
- Auto-merge for propagate-* PRs
- Webhook-based notification
- GitLab / BitBucket support
- Project v2 board の自動構築 (初回手動)
- Custom GitHub App / bot infrastructure

## Idempotence and Recovery

- `report-drift` は同名 sub-issue があれば update、無ければ create、drift 解消で close。再実行可能。
- `setup-*` は worktree-based PR pattern。既存 PR があれば skip。
- ruleset POST/PUT upsert で同名 ruleset 重複生成回避。
- workflow ファイルは upsert(既存があれば skip + diff comment)。

## Artifacts and Notes

(進行中) — test project の URL、生成された Issue 番号、PR URL 等を記録。

## Interfaces and Dependencies

- 新 CLI subcommand × 4
- ai-ops 自身の `.github/workflows/` × 3
- `templates/artifacts/` 増加
- `ProjectSignals` schema 拡張(後方互換、JSON 出力に新 field 追加)
- 各 managed project に 3 種類の artifact が opt-in 配置されうる
- ai-ops repo に "Ecosystem" Project board 作成
- `tekitounix/ai-ops-managed-test` private repo 作成(test 用)
- gh CLI 依存(既存)+ GitHub GraphQL API(sub-issue 用)+ GitHub REST rulesets API
