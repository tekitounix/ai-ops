# worktree workflow + plan binding

ADR 0010 を実装するプラン。worktree directory layout、Branch/Worktree binding、`worktree-new` / `worktree-cleanup` ヘルパー、plan template 拡張、関連 docs 更新を扱う。

Plan path: `docs/plans/worktree-workflow/plan.md`。採用後の archive path: `docs/plans/archive/2026-05-02-worktree-workflow/`。

Branch: `n/a` (本プランは ADR 0010 自体の dogfood には間に合わなかったので main 上で実施)
Worktree: `n/a` (同上)

## Purpose / Big Picture

ADR 0010 で定義した sibling worktree layout、1:1:1 binding、ライフサイクル ヘルパーを実装し、ai-ops CLI / docs / templates に統合する。完了後、次回以降の non-trivial 作業は `ai-ops worktree-new <slug>` で開始 → worktree 内で進行 → plan archive + `ai-ops worktree-cleanup` で完結、というフローが使えるようになる。

ADR 0009 の Tier B/C「feature branch + PR」表現も、本 ADR (0010) を参照することで「trunk-based + short-lived branch + worktree per parallel task」と読み解けるようになる。

## Progress

- [x] (2026-05-02 17:08Z) ADR 0010 起票、本プラン作成。Web 調査結果 (incident.io / MindStudio / agentinterviews / stacking.dev / trunk-based survey) を反映。
- [ ] `templates/plan.md` に Branch / Worktree fields を追加。`build_promoted_plan` も同期。
- [ ] `ai_ops/worktree.py` 新規:
  - `WorktreeSpec` dataclass (slug, branch_type, base_branch)
  - `compute_worktree_path(repo_root, slug) -> Path` (sibling pattern)
  - `compute_branch_name(slug, branch_type) -> str`
  - `create_worktree_with_plan(spec, repo_root, dry_run=False) -> tuple[Path, Path]`
  - `list_worktrees(repo_root) -> list[WorktreeInfo]`
  - `find_cleanable_worktrees(repo_root, dry_run=False) -> list[WorktreeInfo]` (PR merged + plan archived の両方を満たすもの)
  - `cleanup_worktree(info, dry_run=False) -> tuple[bool, str]`
- [ ] `ai_ops/cli.py` に `worktree-new <slug>` / `worktree-cleanup` サブコマンド追加。
- [ ] `tests/test_worktree.py` 新規:
  - sibling path 計算
  - branch 名計算 (default `feat/`, fix/chore/docs/refactor)
  - worktree 作成 dry-run
  - cleanable 検出 (mocked gh + plan path)
- [ ] `docs/self-operation.md` に「worktree-based parallel work」section 追加(ai-ops 自身の作業も worktree-new で開始することを推奨)。
- [ ] `docs/realignment.md` Phase 3 に「per-scope の execute は worktree-new で隔離して実行する選択肢」を追記。
- [ ] `AGENTS.md` の Plans section に「worktree workflow は ADR 0010 + worktree-new/cleanup を参照」を 1 行追加。
- [ ] `README.md` のサブコマンド表に worktree-new / worktree-cleanup 追加。
- [ ] `ai_ops/audit/lifecycle.py` の README_CLAIMED_SUBCOMMANDS と REQUIRED_FILES を更新。
- [ ] `python -m ai_ops check` 通過、commit + push、CI watch。
- [ ] Verify / Adopt 完了時に archive。
- [ ] (dogfood 別 session): 次の非自明な作業を `ai-ops worktree-new` で開始してフローを実 use 検証。

## Surprises & Discoveries

- Observation: incident.io の実 pattern は「全 Claude Code session を worktree」で隔離する高い defaults を採用していた。他社の MindStudio パターンや agentinterviews は「parallel が必要なときだけ worktree」のより穏やかな defaults。
  Evidence: 調査メモ。
  Implication: ai-ops の defaults は穏やかな方を採用する(自動でなく opt-in、`worktree-new <slug>` を明示的に叩く)。理由: solo dev の場面で全 session を worktree にすると context 管理コストが上がる。

- Observation: agentinterviews パターンは複数 agent が同 plan を共有して並走する形(`specs/<feature>.md` 1 つに対して `trees/<feature>-{1,2,3}/` で N agent)。これは 1 plan : 1 agent ではない。
  Evidence: 調査メモ。
  Implication: 本 ADR の「1:1:1 binding」は default だが、multi-agent parallel evaluation の場合は「1 plan : N worktree」も許容する余地がある(Improvement Candidate に記録)。

- Observation: incident.io が直面した「local resource (DB, port, dependencies)」のボトルネックは ai-ops 内では発生しにくい(Python CLI で重い dev-server を伴わない)。
  Evidence: 調査メモ。ai-ops の構造。
  Implication: per-worktree port/db assignment 等の自動化は scope 外。

- Observation: `umipal` の `mi_share.repo-restructure/` のような既存 sibling worktree は、ghq list -p に独立 entry として出る(`ghq list` は worktree とリポジトリを区別しない)。
  Evidence: 過去の dry-run 出力。
  Implication: `ai-ops audit projects` が同じ remote を指す複数 worktree を別 project として数える点は要注意(detection only、現状は許容)。

## Decision Log

- Decision: worktree directory layout は **sibling pattern** (`<repo-parent>/<repo-name>.<slug>/`) を default とする。
  Rationale: 既存の `umipal` / `mi_share` で de facto 採用されているパターン。MindStudio の Claude Code 推奨パターンとも一致。`~/ghq/` 配下に並ぶことで `ghq cd` で navigate 可能。grouped pattern (`~/.cache/...`) は機械内部用 (propagate-*) のみに維持。
  Date/Author: 2026-05-02 / Codex

- Decision: branch 命名は `<type>/<slug>` (type ∈ feat/fix/chore/docs/refactor、default `feat`)。`<slug>` は plan slug に揃える。
  Rationale: conventional commits の type semantics と整合。slug 一致で plan ↔ branch ↔ worktree の binding が自動的に成立。
  Date/Author: 2026-05-02 / Codex

- Decision: `worktree-cleanup` は **user 確認** がデフォルト、`--auto` で省略可能。merged + archived の両方を満たす worktree のみ cleanup 候補。
  Rationale: Safety、特にローカル worktree の rm は復旧不能。「PR merged」だけでは plan が active かもしれない、「plan archived」だけでは branch がまだ未マージかもしれない。両方の signal を要求することで誤削除を防ぐ。
  Date/Author: 2026-05-02 / Codex

- Decision: 1 plan ↔ 1 worktree の binding は **default**、ただし「1 plan : N worktree」(parallel agent evaluation 等) も Improvement Candidate として deferred 許容。
  Rationale: 多くの場合 1:1 で足りる。N parallel evaluation は専用パターンとして将来拡張。
  Date/Author: 2026-05-02 / Codex

- Decision: 3〜5 worktree per repo の上限は audit signal で INFO 表示するが、enforce しない。
  Rationale: research の practical limit に基づく。enforce すると user の判断を奪う。
  Date/Author: 2026-05-02 / Codex

- Decision: ADR 0009 (tier system) は本 ADR と並立。superseding にしない。0009 の Tier B/C 表現は本 ADR を併読することで「trunk-based + short-lived branch + worktree per parallel task」と理解する。
  Rationale: tier 定義そのものは valid。worktree workflow の追加情報を 0010 として並列に持つ方が読み手に親切。
  Date/Author: 2026-05-02 / Codex

- Decision: dogfood (ai-ops 自身のこの作業を worktree-new で実施) は本プランでは行わない。次回の非自明作業から適用。
  Rationale: 既に main 上で進行中の作業を強引に worktree に切り替えるのは artificial。実装完了後の使用 evidence は次の作業 cycle で集める。
  Date/Author: 2026-05-02 / Codex

## Outcomes & Retrospective

Shipped (commit d329e8c):

- ADR 0010 (`docs/decisions/0010-worktree-workflow.md`)
- ADR 0009 cross-reference 追加(long-lived branches は Tier D acceptance、Tier B norm でない旨を明示)
- `templates/plan.md` + `build_promoted_plan` に Branch / Worktree fields 追加(schema-consistency test 通過)
- `ai_ops/worktree.py` 新規(WorktreeSpec / WorktreeInfo / compute_worktree_path / compute_branch_name / create_worktree_with_plan / list_worktrees / find_cleanable_worktrees / cleanup_worktree)
- `ai-ops worktree-new <slug>` および `ai-ops worktree-cleanup` サブコマンド
- lifecycle audit の REQUIRED_FILES と README_CLAIMED_SUBCOMMANDS 更新
- `docs/self-operation.md`、`docs/realignment.md`、`AGENTS.md`、`README.md` の docs 統合
- tests: `tests/test_worktree.py` 10 件(path/branch 計算、dry-run 副作用ゼロ、実作成、refusal cases、cleanable 検出は両 signal 必須、real cleanup、list_worktrees parsing)

Verification:
- `python -m ai_ops check` PASS、CI 全 5 ジョブ green
- 92 → 102 tests pass(worktree 10 件追加)

What remains / future evidence:
- 本プラン自体は main 上で実施(dogfood なし)。次の非自明な作業を `ai-ops worktree-new <slug>` で開始してフローを実 use 検証する。
- `worktree-cleanup` の merged + archived の AND 検出は機械テスト済みだが、実 use での誤判定リスクは observed ベースで再評価。

What should change in future plans:
- ADR 起票 → plan → 実装の三段並走パターンが今回も機能した。trunk-based の業界 best practice を取り入れるなら、今後の non-trivial 作業は worktree で進めて main を更にクリーンに保つ運用を試す。

## Improvement Candidates

### multi-agent parallel evaluation pattern

- Observation: agentinterviews が示した「1 plan : N worktree」(N 個の Claude / Codex / Gemini agent が同 spec を並列実装、結果を比較選択) は強力な pattern だが、本 ADR では default 1:1 binding に絞った。
- Evidence: 調査メモ、`trees/<feature>-{1..N}/` パターン。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — 専用 subcommand (`ai-ops parallel-spec <slug> --agents N`) の追加が必要。
- Verification: ai-ops 自身の何らかの実装で「複数 agent 結果を比較したい」需要が出たら検討。
- Disposition: deferred — 当面 1:1 で運用、需要が見えたら別 plan で拡張。

### auto-cleanup hook on PR merge

- Observation: PR が merged された瞬間に対応 worktree を自動削除するフック(post-merge GitHub Action) は技術的に可能。
- Evidence: ADR 0010 の Out of scope。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — destructive operation の自動化、user の確認を奪う。
- Verification: 手動 `worktree-cleanup` の頻度が問題になったら検討。
- Disposition: deferred — Safety が優先、user driven cleanup を維持。

### per-worktree dev-server orchestration

- Observation: incident.io が直面した「複数 worktree 間で port/db conflict」を ai-ops が自動解決する仕組み(ephemeral CI 環境等)。
- Evidence: 調査メモ。
- Recommended adoption target: `rejected`
- Confirmation needed: no — ai-ops の scope 外。
- Verification: n/a
- Disposition: rejected — ai-ops は CLI tool であり、dev environment orchestrator ではない。

### stacked PR adoption

- Observation: Tier B/C で gh-stack / Graphite を recommend する別 ADR (0011) を起こす。
- Evidence: 調査メモ、stacking workflow の業界普及。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — managed project owner の判断、ADR 化の上で。
- Verification: 1 つでも managed project が「stacked PR を使いたい」と言ったら別 ADR + plan で進める。
- Disposition: deferred — 現状の単独 PR per task で十分機能している。

### merge queue adoption

- Observation: GitHub merge queue を Tier C で recommend する別 ADR。
- Evidence: 調査メモ。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — high PR volume が前提、現状の ai-ops では当てはまらない。
- Verification: ai-ops or any managed project の PR 量が「daily multiple」になったら検討。
- Disposition: deferred。

### jujutsu (jj) integration

- Observation: jj は git compatible で個人/小チーム production-ready。anonymous branch がデフォルトで trunk-based + Gerrit-style に親和的。
- Evidence: 調査メモ。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — ツール選定変更、user の好み次第。
- Verification: user が「jj を試したい」と言ったら整理。ai-ops の propagator 系は git に依存しているので互換性検証要。
- Disposition: deferred — 当面 git 前提で運用。

## Context and Orientation

- `templates/plan.md` — Branch / Worktree fields の追加対象。`ai_ops/lifecycle/plans.py:build_promoted_plan` も同期。
- `ai_ops/cli.py` — 新サブコマンド 2 個追加。
- `ai_ops/worktree.py` — 新 module。
- `docs/decisions/0009-git-workflow-tiers.md` — 本 ADR との関係を明示するため、0010 への "see also" 追記を最後にやる。
- `docs/self-operation.md` / `docs/realignment.md` — 運用 docs に worktree pattern を統合。

## Plan of Work

1. `templates/plan.md` に Branch / Worktree fields を追加。
2. `ai_ops/lifecycle/plans.py:build_promoted_plan` の生成テキストにも同 fields を追加(schema consistency test が pass し続けるよう)。
3. `ai_ops/worktree.py` 新規実装。
4. `ai_ops/cli.py` に `worktree-new` / `worktree-cleanup` ハンドラ追加。
5. `ai_ops/audit/lifecycle.py` の README_CLAIMED_SUBCOMMANDS に `worktree-new` / `worktree-cleanup` 追加、REQUIRED_FILES に `ai_ops/worktree.py` 追加。
6. tests 追加。
7. docs 更新 (self-operation、realignment、AGENTS、README、ADR 0009 の See Also に 0010 を追記)。
8. `python -m ai_ops check` 通過、commit + push、CI watch。
9. archive。

## Concrete Steps

```sh
python -m pytest tests/test_worktree.py tests/test_audit.py
python -m ai_ops audit lifecycle
python -m ai_ops worktree-new --help
python -m ai_ops worktree-cleanup --help
python -m ai_ops check
git diff --check
```

## Validation and Acceptance

### Machine-checkable

- `ai_ops/worktree.py` が存在し、`compute_worktree_path` / `compute_branch_name` / `create_worktree_with_plan` / `find_cleanable_worktrees` を export。
- CLI に `worktree-new <slug>` と `worktree-cleanup` が追加されている(`--help` に応答)。
- `templates/plan.md` に `Branch:` `Worktree:` 行が含まれる。
- `build_promoted_plan` の出力にも同 fields が含まれる(schema consistency test pass)。
- `tests/test_worktree.py` の全テストが pass する。
- `python -m ai_ops check` PASS、CI 全ジョブ green。

### Human-reviewable

- ADR 0010 が worktree pattern + binding + lifecycle を明確に説明している。
- `docs/self-operation.md` に worktree usage の guidance がある。
- `docs/realignment.md` Phase 3 に worktree-new での隔離実行の選択肢が記載されている。

## Out of Scope

- multi-agent parallel evaluation pattern (1 plan : N worktree)
- auto-cleanup hook on PR merge
- per-worktree dev-server orchestration
- stacked PR adoption (別 ADR)
- merge queue adoption (別 ADR)
- jujutsu (jj) adoption

## Idempotence and Recovery

- `worktree-new` は worktree path や branch が既存なら error で停止(上書きしない)。
- `worktree-cleanup` は user 確認デフォルト、`--auto` でも merged + archived の両 signal が揃ったものだけ削除。
- plan template の field 追加は backward compatible(既存 plan は変更不要、新規だけ field 入り)。

## Artifacts and Notes

外部調査結果(2026-05-02):
- trunk-based development の DORA elite performer データ (182× / 127×)
- worktree が AI coding agent の load-bearing 機能化 (Q1 2026)
- 主要 layout 2 patterns (sibling / grouped)
- 3〜5 worktree per repo の practical limit
- incident.io / MindStudio / agentinterviews の実 pattern

## Interfaces and Dependencies

- 新サブコマンド `ai-ops worktree-new`, `ai-ops worktree-cleanup`
- `templates/plan.md` の schema 変更(後方互換、新 field optional)
- `gh` CLI 依存(cleanup での PR 状態確認のため、optional fallback あり)
