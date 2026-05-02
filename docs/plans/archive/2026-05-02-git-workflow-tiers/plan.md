# git workflow tier 宣言と検出機構

ADR 0009 を実装するプラン。tier 定義は ADR 側、本プランは harness schema 拡張、audit signal 追加、ai-ops 自身の Tier A 宣言、関連 docs 更新までを担当。

## Purpose / Big Picture

ADR 0009 で定義した 4 tier (A/B/C/D) を、各 managed project が `.ai-ops/harness.toml` に宣言できるようにし、`ai-ops audit projects` がその tier に対する違反を検出表示するようにする。

完了後:
- `harness.toml` に optional な `workflow_tier` field が認識される(欠落時は `"D"` デフォルト)
- `audit projects` の出力に tier が表示される
- tier 違反(Tier A の long-lived branch、Tier B/C の main 直接 push 等)が WARN として出る
- ai-ops 自身が `workflow_tier = "A"` を declare(dogfood)
- realignment.md / projects-audit.md に tier の議論が組み込まれる

実 enforcement(branch protection 強制等)はスコープ外。Detection-only。

## Progress

- [x] (2026-05-02 15:59Z) ADR 0009 起票、本プラン作成。
- [ ] `HarnessManifest` schema に `workflow_tier: str = "D"` field 追加。`from_toml` / `to_toml` 対応。
- [ ] tier 違反 detector 実装(`ai_ops/audit/workflow.py` 新規):
  - `_detect_tier_violations(project, tier, default_branch) -> list[str]`
  - Tier A: long-lived branch detection
  - Tier B/C: direct-push-to-main detection
  - 共通: manifest-not-on-default detection(既存ロジックを再利用)
- [ ] `ProjectSignals` に `workflow_tier: str` と `tier_violations: list[str]` 追加。
- [ ] `audit projects` table に新 column (`tier`) を追加、`tier_violations` は JSON のみで surface。
- [ ] severity 計算: tier 違反は P1(harness drift と同等扱い)に escalate。
- [ ] ai-ops 自身に `.ai-ops/harness.toml` を作成、`workflow_tier = "A"` を declare。
- [ ] `docs/realignment.md` Phase 2 Brief 構造に「workflow_tier 宣言の提案」step を追加。
- [ ] `docs/projects-audit.md` の signal 表に `workflow_tier` と `tier_violations` を追記。
- [ ] `docs/ai-first-lifecycle.md` または `templates/project-brief.md` に「workflow tier の選択」section を追加(新規 project 用)。
- [ ] tests: schema、detector、audit signal、ai-ops self-tier declaration をカバー。
- [ ] `python -m ai_ops check` 通過、commit + push、CI watch。

## Surprises & Discoveries

- Observation: ai-ops 自身は `mgd == "src"` で `harness.toml` を持たない設計だったが、Tier A を dogfood として declare するなら、自分用の harness.toml を持ってもよい(あるいは tier 宣言を別経路で持つ)。
  Evidence: `audit/projects.py:_is_ai_ops_repo` と `mgd="src"` の扱い。
  Implication: 選択肢: (a) ai-ops も `harness.toml` を持つ(管理者と被管理者の二重ロール)、(b) 別ファイル `.ai-ops/workflow.toml` を作る、(c) ai-ops の `AGENTS.md` 内に declare、(d) audit 側にハードコードで「ai-ops は Tier A」。
  Decision: (a)。harness.toml を ai-ops 自身も持つ。`mgd="src"` の場合は audit が「自身の管理対象でもある」と解釈する形に拡張。これが tier 宣言と他 signal の一貫性を最大化する。

- Observation: tier 違反検出のうち「Tier B/C で direct-push-to-main 検出」は `gh api repos/.../commits` を呼ぶ必要があり、network + rate limit のリスクがある。
  Evidence: `gh api` の使用パターン。GitHub の primary rate limit は 60 req/hr (unauthenticated) / 5000 req/hr (authenticated)。authenticated 前提なら 1 audit run あたり数十 commit 確認は問題ないが、毎 audit でやるとキャッシュなしでは無駄。
  Implication: Tier B/C 検出は最近 30 日の commits だけスキャンする時間窓制限を入れる。または `--check-tier-violations` flag で opt-in 化。

- Observation: Tier D は実質「detection 無効」だが、user に「あなたのプロジェクトは Tier D なので manifest を default branch にマージしないと propagation が動かない」と知らせる INFO は出すべき。
  Evidence: umipal の `propagate-anchor` が「manifest absent on origin/master」で skip した実例。
  Implication: Tier D の場合に限って「propagation 制限」INFO を出す。WARN ではない(declared 通りの挙動なので)。

## Decision Log

- Decision: `HarnessManifest.workflow_tier` のデフォルトは `"D"`(最も permissive)。欠落時の互換性のため。
  Rationale: 既存 6 managed projects はすべて tier 宣言なしで動いているので、これらが ship 直後に「P1 escalation」されるのを避ける。明示宣言が真の運用変更を示す。
  Date/Author: 2026-05-02 / Codex

- Decision: ai-ops 自身も `.ai-ops/harness.toml` を持ち、`workflow_tier = "A"` を declare する。`_is_ai_ops_repo` の判定は変えず、`mgd="src"` のままだが、harness.toml の有無で tier 検出を可能にする。
  Rationale: dogfood の最大化。tier 宣言の declarative 性を ai-ops 自身でも貫く。
  Date/Author: 2026-05-02 / Codex

- Decision: tier 違反検出のうち、network call が必要なもの(direct-push-to-main、PR-without-review)は `--check-tier-violations` flag で opt-in。デフォルトの `audit projects` は network なしで完結する signal のみ。
  Rationale: audit projects は cron / CI から走らせる前提なので、デフォルトは fast + offline-friendly に保つ。深い tier 検査は手動 trigger。
  Date/Author: 2026-05-02 / Codex

- Decision: tier 違反は `severity` を P1 にエスカレートする(`harness_drift` と同等)。`policy_drift` と並列の signal として扱う。
  Rationale: tier 違反は「project owner が宣言した規範からの逸脱」なので、harness drift と同じく中重要度。P0 まで上げると security との混同になる。
  Date/Author: 2026-05-02 / Codex

- Decision: tier の値は `propagate-*` の auto-PR では絶対に変更しない。user が realignment を経て手動で declare/変更する。
  Rationale: tier は user judgment。mechanical sync の対象外。Operation Model の精神。
  Date/Author: 2026-05-02 / Codex

- Decision: `realignment.md` Phase 2 Brief の P0 doc-only セクションに「workflow_tier 宣言の提案」を追加する。Phase 1 Discovery で Tier 推定根拠(public/private、recent commits、contributor count)を集める。
  Rationale: 既存の realignment フローに溶け込ませる。新規 subcommand を作らない方針(propagate-* で 3 つも増えたので追加は控える)。
  Date/Author: 2026-05-02 / Codex

## Outcomes & Retrospective

TBD。

## Improvement Candidates

### tier-aware propagation の優先度付け

- Observation: 同じ ai-ops 改善に対して、Tier C プロジェクトの propagation と Tier D プロジェクトの propagation を同列に扱っているが、本来は Tier C/B のほうを先に処理すべきかもしれない。
- Evidence: 本 ADR で tier を declare する仕組みが入る → 利用可能な signal が増える。
- Recommended adoption target: `deferred`
- Confirmation needed: no — sort logic 変更のみ。
- Verification: 実 use で「Tier D の noise で重要 project を見逃す」状況が発生したら検討。
- Disposition: deferred — 当面は priority sort のみで足りる。

### tier 違反の自動修復 PR

- Observation: 「Tier A 宣言だが long-lived branch あり」のような違反に対して、自動修復(branch を rebase + squash + delete)するは技術的には可能だが destructive 過ぎる。
- Evidence: 本 ADR の「Detection only」方針。
- Recommended adoption target: `rejected`
- Confirmation needed: no — 設計理念に反する。
- Verification: n/a
- Disposition: rejected — Detection が user に judgment を促す形を維持。

### `setup-workflow --tier <X>` automation

- Observation: GitHub branch protection rule や PR template を tier に応じて配置する automation。本プランで重いとして見送ったもの。
- Evidence: ADR 0009 の Out of scope。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — GitHub API 経由の設定変更は user 承認必須。
- Verification: 複数 user が「tier B にしたいが branch protection 設定が面倒」と言うようになったら検討。
- Disposition: deferred — 各 owner が GitHub UI で設定する運用で当面足りる。

### ai-ops 自身の tier upgrade

- Observation: ai-ops 自身を Tier A で declare するが、CI 失敗が 10 commit 連続で気付かれなかった事故を考えると、Tier B(PR + CI 必須)への昇格を考えるべき時期かもしれない。
- Evidence: 本 plan series の reactive 検出事故。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — 運用速度とのトレードオフ。
- Verification: 同種の事故が再発するなら Tier B 昇格、再発しないなら Tier A 継続で OK。
- Disposition: deferred — まず Tier A で declare し、本プラン後の運用で再評価。

### tier 検出の per-commit cache

- Observation: `gh api repos/.../commits` を毎 audit で走らせるのは無駄。前回 audit 以降の commit だけ見る差分検出が望ましい。
- Evidence: 本 ADR の Decision Log で network call 制限を提示済み。
- Recommended adoption target: `deferred`
- Confirmation needed: no — 内部最適化。
- Verification: rate limit に当たる、または audit が遅くなったら検討。
- Disposition: deferred — `--check-tier-violations` opt-in なので頻度は低い。

## Context and Orientation

- `ai_ops/audit/harness.py:HarnessManifest` — schema 拡張対象。
- `ai_ops/audit/projects.py` — 新 signal 追加 + table 拡張対象。
- `docs/realignment.md` — Phase 2 Brief への tier 議論挿入対象。
- `docs/projects-audit.md` — signal 一覧の更新対象。
- `docs/decisions/0009-git-workflow-tiers.md` — 本プランの ADR(同 commit で起票済み)。

## Plan of Work

1. ADR 0009 起票(完了)。
2. `HarnessManifest` schema 拡張: `workflow_tier: str = "D"` field、`from_toml`/`to_toml` 対応、欠落時 default。
3. `_bump_anchor_in_manifest_text` (anchor-sync) と `_replace_harness_files_section` (files-sync) は tier field を touch しないことを既存テストで確認(should already preserve since they target specific fields/sections only)。
4. 新 module `ai_ops/audit/workflow.py`:
   - `detect_tier_violations(project, tier, default_branch, *, deep=False) -> list[str]`
   - 浅い検出: tier+manifest-not-on-default 系
   - deep 検出: gh api 系(`deep=True` で起動)
5. `ProjectSignals` に `workflow_tier: str` と `tier_violations: list[str]` 追加。`signals_to_dict` も対応。
6. `audit projects` の table column に `tier` を追加(3 文字: `A`/`B`/`C`/`D`)。`tier_violations` は JSON 出力のみ。
7. severity 計算: `tier_violations` が non-empty なら P1 escalation 候補に追加(既存条件と OR)。
8. CLI: `audit projects` に `--check-tier-violations` flag 追加(deep detection を opt-in)。
9. ai-ops 自身に `.ai-ops/harness.toml` を作成して commit、`workflow_tier = "A"`。`_is_ai_ops_repo` の挙動は変えない(mgd="src" のまま)。tier だけ拾える形にする。
10. `docs/realignment.md` Phase 2 Brief P0 doc-only セクションに「workflow_tier 宣言提案」追加。Phase 1 Discovery に「tier 推定根拠の収集」を追加。
11. `docs/projects-audit.md` の signal 表に `workflow_tier` と `tier_violations` 追加。
12. `templates/project-brief.md` に「Workflow tier」section 追加(新規 project 用)。
13. `templates/migration-brief.md` も同様に更新。
14. tests:
    - `tests/test_audit.py`: `HarnessManifest.workflow_tier` schema 互換、tier 違反 detector の各 case
    - `tests/test_audit_projects.py`: `ProjectSignals.workflow_tier` 反映、severity escalation
15. `python -m ai_ops check` 通過、commit + push、CI watch。
16. 完了後本プランを archive。

## Concrete Steps

```sh
python -m pytest tests/test_audit.py tests/test_audit_projects.py
python -m ai_ops audit lifecycle
python -m ai_ops audit projects --json | jq '.[] | {project, workflow_tier, tier_violations}'
python -m ai_ops check
git diff --check
```

## Validation and Acceptance

### Machine-checkable

- `HarnessManifest` instances with no `workflow_tier` field round-trip via `from_toml`/`to_toml` without error and surface as `"D"`.
- `audit projects --json` includes `workflow_tier` and `tier_violations` fields for all projects.
- `_detect_tier_violations` returns expected violations for synthetic tier+state combinations (test).
- ai-ops 自身の `audit projects --json` 出力に `workflow_tier=A` が含まれる。
- `python -m ai_ops check` PASS、CI green。

### Human-reviewable

- ADR 0009 が tier 定義 + 検出方針 + reflection mechanism を明確に説明している。
- `realignment.md` の Phase 2 が tier 宣言提案を含む。

## Out of Scope

- `setup-workflow --tier <X>` 自動化(branch protection rule 設定等)
- tier 違反の自動修復 PR
- tier-aware propagation 優先度付け
- per-tier CI template
- squash/rebase/merge 戦略の標準化
- cross-machine workflow sync

## Idempotence and Recovery

- schema 追加は後方互換(欠落時 default `"D"`)。
- audit 出力の column 追加は既存 user の jq 等パーシングと互換(JSON でのみ新 field、column は末尾追加)。
- ai-ops 自身の `.ai-ops/harness.toml` 追加は単純な新ファイル commit、reversible。

## Artifacts and Notes

ADR 0009: `docs/decisions/0009-git-workflow-tiers.md`(本プラン commit と同時)

各 managed project の tier 暫定推定(Discovery 観察ベース、user judgment で変わる):

- ai-ops 自身: A
- knx3: A(personal tool)
- mi_share: B(propagate-* と user PR が並走)
- audio-dsp-docs: B
- fastener-research: A or B(ほぼ未活動)
- fx-llm-research: D(active research、長期 spike)
- umipal: D(phase-a spike が長期、後で Tier B に昇格?)
- note-md: A(personal tool)

これらは declare 時に user が再判断する。

## Interfaces and Dependencies

- `harness.toml` schema 1 field 追加(後方互換)
- `audit projects --json` schema に 2 field 追加(後方互換)
- `audit projects` table に 1 column 追加
- `audit projects` に opt-in flag `--check-tier-violations` 追加
- ai-ops 自身に `.ai-ops/harness.toml` 新規追加
