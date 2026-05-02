# init-harness 反映機構

増分シリーズ第二弾。anchor-sync の実 use 検証で「13 プロジェクト中、anchor-sync の対象は 0 件」と判明し、その最大原因が `.ai-ops/harness.toml` の untracked 状態(4 プロジェクト)であることが分かった。本プランはそれを解消する propagate-init を追加する。

## Purpose / Big Picture

各管理プロジェクトに `.ai-ops/harness.toml` がディスク上に存在するが、まだ git で tracked されていない状態を解消する仕組みを追加する。具体的には:

- 対象: `.ai-ops/harness.toml` がワーキングツリーに存在し、untracked であり、TOML として valid な HarnessManifest 形式であるプロジェクト
- 動作: worktree を default branch から切り、user のワーキングコピーから `.ai-ops/harness.toml` を読み取り、worktree に複製してコミット、別ブランチに push、PR 作成
- user のワーキングコピーは一切触らない(読み取りのみ、worktree 隔離)

完了後、4 プロジェクトの harness が PR 経由で tracked になる。マージ後は anchor-sync の対象になり、ai-ops 改善が PR 経由で反映され続ける状態に到達する。

## Progress

- [x] (2026-05-02 07:44Z) プラン作成。anchor-sync の実 use 結果から bottleneck を特定。
- [ ] `ai_ops/propagate.py` に `_list_init_targets()` と `init_one()` を追加。
- [ ] `ai_ops/cli.py` に `propagate-init` サブコマンドを追加。
- [ ] `tests/test_propagate.py` に init 系テストを追加。
- [ ] `python -m ai_ops check` 通過、commit + push。
- [ ] 実 use 確認: `propagate-init --dry-run --all` で対象 4 件が列挙される。
- [ ] Verify / Adopt 完了時に archive。

## Surprises & Discoveries

- Observation: anchor-sync の実 use 結果(直前のプラン完了時)から、untracked manifest が 4 プロジェクトと判明。最も大きな bottleneck カテゴリ。
  Evidence: `python -m ai_ops propagate-anchor --dry-run --all` の skip 出力。
  Implication: untracked 解消が最初に取り組むべき問題。

- Observation: `.ai-ops/harness.toml` を含む `.ai-ops/` ディレクトリには、将来的に他のファイル(notes.md など)も追加される可能性がある。
  Evidence: 現在は harness.toml のみだが、`docs/decisions/` のような将来的拡張余地。
  Implication: propagate-init は **harness.toml のみ** を対象にする。`.ai-ops/` 全体を git add すると意図しないファイルが入る可能性がある。

## Decision Log

- Decision: 対象は `.ai-ops/harness.toml` 単独。`.ai-ops/` ディレクトリの他のファイルは触らない。
  Rationale: 将来 `.ai-ops/` 配下に他のファイルが追加された時、それが prop-init で意図せず commit されるのを避ける。明示的に harness.toml だけを対象とする。
  Date/Author: 2026-05-02 / Codex

- Decision: コミット前に `HarnessManifest.from_toml()` で valid 性を verify する。invalid なら skip し理由を表示。
  Rationale: 不完全な手書きの draft が誤って commit されないようにする safeguard。
  Date/Author: 2026-05-02 / Codex

- Decision: ブランチ命名は `ai-ops/init-harness-<short-sha>`(short-sha は ai-ops HEAD の 7 桁)。
  Rationale: anchor-sync の `ai-ops/anchor-sync-<short-sha>` 命名と整合。種別が判別できる。
  Date/Author: 2026-05-02 / Codex

- Decision: `.ai-ops/harness.toml` が default branch に既に存在するプロジェクトは対象外(既に tracked、init 不要)。
  Rationale: anchor-sync の bug fix で同じ check を入れた。propagate-init は逆向きの check(default branch に存在しない場合のみ対象)。
  Date/Author: 2026-05-02 / Codex

- Decision: anchor-sync と同じ worktree 隔離パターン、try/finally cleanup、per-project confirmation を踏襲する。
  Rationale: 一貫性のため。anchor-sync で安全性が検証済みのパターンを再利用する。
  Date/Author: 2026-05-02 / Codex

## Outcomes & Retrospective

Shipped (commits 85cba98 / 7dd5591 / その後 71fa9b2 で sandbox 互換):

- `ai_ops/propagate.py` の init-harness 機構: `.ai-ops/harness.toml` がローカル disk にあるが untracked なプロジェクトに対して、worktree 隔離 + manifest commit + push + PR 作成を行う
- `ai-ops propagate-init` サブコマンド(`--all` / `--project` / `--dry-run`)
- レビューで判明した重要な改善: 当初 `init_one` が capture した user 作業コピーの `ai_ops_sha` をそのまま記録していたため、merge 直後に古い anchor になる問題があり、`init_one` が current ai-ops HEAD に bump してから commit するよう修正(7dd5591)

実 use 結果:
- audio-dsp-docs / fastener-research / fx-llm-research の 3 プロジェクトに init PR を作成、すべて merge 済み
- 元の 4 番目候補(mi_share)は manifest が feature branch にしか無かったため init 対象外と判定された(branch 切り替えなしで commit できないため)

What remains:
- mi_share 系の repo (mi_share, mi_share.ai-ops-setup, mi_share.repo-restructure) で `.ai-ops/harness.toml` を default branch にマージする作業は user 側に残る(merge 完了後 anchor-sync が動き始める)。

What should change in future plans:
- captured manifest と current state の境界に注意。「local の状態をそのまま PR に乗せる」と「current canonical 状態に合わせて PR を作る」は別物で、後者の方が普通は user の意図に合う(init-harness では後者が正解だった)。

## Improvement Candidates

### migrate コマンドが harness を auto-commit する

- Observation: untracked harness の根本原因は `ai-ops migrate` が AI agent にプロンプトを渡すだけで、agent 側が manifest を作成・コミットするかは agent 任せ。auto-commit する仕組みがない。
- Evidence: `ai_ops/lifecycle/migration.py` を grep した結果、harness を write/commit する箇所は無し。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — migration の挙動を変えると既存のフローに影響する。
- Verification: 新規 migrate の度に untracked harness が発生するか観察。発生するなら本対策を進める。
- Disposition: deferred — 既存 4 件は本プランで解消、将来発生は別途対応。

### .ai-ops/ 配下の他ファイル(将来追加されるもの)の扱い

- Observation: 現在 `.ai-ops/` には harness.toml のみだが、将来 notes.md などが追加された時の扱いが未定義。
- Evidence: 本プラン Decision Log。
- Recommended adoption target: `deferred`
- Confirmation needed: no — 将来の拡張時に決める。
- Verification: `.ai-ops/` 配下に新しいファイル種別が追加された時に再評価。
- Disposition: deferred。

## Context and Orientation

- `ai_ops/propagate.py` — 既存の anchor-sync 実装。本プランは同 module を拡張する。
- `ai_ops/audit/harness.py` — `HarnessManifest` schema、`HARNESS_MANIFEST` 定数。
- `ai_ops/cli.py` — subcommand 追加場所。

## Plan of Work

1. `ai_ops/propagate.py` に新規:
   - `InitHarnessTarget` dataclass
   - `_list_init_targets(ai_ops_root)`: worktree に `.ai-ops/harness.toml` があり、tracked でなく、default branch にも存在しない、valid なプロジェクトを列挙。
   - `init_one(target, dry_run)`: worktree 作成 → user の harness.toml を複製 → コミット → push → PR。

2. `ai_ops/cli.py` に `propagate-init` 追加。`--all` / `--project` / `--dry-run`。

3. `tests/test_propagate.py` に init 系テスト 4 件以上:
   - tracked manifest あり → 対象外
   - untracked manifest あり、default branch に無し → 対象
   - invalid TOML → skip
   - dry-run で副作用ゼロ

4. `python -m ai_ops check` 通過、commit + push。

5. 実 use 確認 + archive。

## Concrete Steps

```sh
python -m pytest tests/test_propagate.py
python -m ai_ops propagate-init --dry-run --all
python -m ai_ops check
git diff --check
```

## Validation and Acceptance

### Machine-checkable

- `ai_ops/propagate.py` に `_list_init_targets()` と `init_one()` が定義されている。
- `ai_ops/cli.py` に `propagate-init` サブコマンドが追加されている。
- `tests/test_propagate.py` の全テストが pass する。
- `python -m ai_ops check` PASS / FAIL = 0 / 0、`git diff --check` クリーン。

### Human-reviewable

- `propagate-init --dry-run --all` 実行時、untracked-manifest 4 件が対象として列挙される。
- 既に tracked または default branch にあるプロジェクトは「skip」と表示される。

## Out of Scope

- `.ai-ops/` 配下の harness.toml 以外のファイル commit
- harness.toml の自動生成(既に user が用意している前提)
- migrate の auto-commit 化(別 Improvement Candidate)
- file content sync(別プラン: harness-files-sync)

## Idempotence and Recovery

- 同じ `<short-sha>` の PR 既存 → skip
- worktree は try/finally で削除
- 全体は冪等

## Artifacts and Notes

直前の `propagate-anchor --dry-run --all` 出力の untracked manifest 件数: 4 件
- mi_share、audio-dsp-docs、fastener-research、fx-llm-research

## Interfaces and Dependencies

- 新サブコマンド `ai-ops propagate-init`
- 既存と同じ依存(`gh`、worktree 隔離パス `~/.cache/ai-ops/worktrees/`)
