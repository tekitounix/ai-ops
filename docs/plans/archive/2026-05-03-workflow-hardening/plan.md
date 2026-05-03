# Workflow Hardening

Branch: `chore/workflow-hardening`
Worktree: `../ai-ops.workflow-hardening/`

## Purpose / Big Picture

Step 1 (docs language policy) を進める中で、ai-ops 自身のワークフローに 3 つの構造的な穴が露呈した。

1. **AGENTS.md が肥大化している**: Subcommands リスト (43-68 行、24 コマンドの詳細説明) は `ai-ops --help` で機械的に取れる情報を重複保持している。AGENTS.md は AI agent が起動毎に必読するファイルなので、ロードコストが高い。Lifecycle 内の sub-flow リストも `docs/operation.md` の Sub-flows table と完全重複。
2. **`gh pr merge --delete-branch` が効かず stale branch が残り続けている**: PR #2、#3 の両方でリモート枝が削除されず、毎回手動で `git push origin --delete <branch>` する状況。原因は repository 設定 `deleteBranchOnMerge: false`。
3. **plan archive の手順が標準化されていない**: PR merge 後、`docs/plans/<slug>/` を `docs/plans/archive/YYYY-MM-DD-<slug>/` に移すコミットを別途手動で main に push している。`worktree-cleanup` は「archive 済み」を要求するが、archive する手段は明文化されていない。

本 plan は 3 つの是正を 1 PR で行う。

1. AGENTS.md スリム化: Subcommands 詳細を削除し、`docs/operation.md` と `ai-ops --help` への pointer に置き換える。Lifecycle の sub-flow 列挙も同様。
2. Repository 設定変更: `deleteBranchOnMerge: true` に設定し、operation guide に「マージ後の確認手順」を明記する。
3. ADR 0010 と `docs/operation.md` に「マージ → main pull → archive コミット → push → worktree-cleanup」の順序を明文化。

## Progress

- [x] (2026-05-03 02:15Z) Initial plan drafted.
- [x] (2026-05-03 02:18Z) Repository 設定 `deleteBranchOnMerge: true` 適用 (`gh repo edit --delete-branch-on-merge`)。
- [x] (2026-05-03 02:25Z) AGENTS.md スリム化 (152 → 109 行、43 行 / 28% 削減)。Subcommands 詳細リスト除去 + Lifecycle の sub-flow リスト除去 → `docs/operation.md` と `ai-ops --help` への pointer に置換。
- [x] (2026-05-03 02:28Z) ADR 0010 Lifecycle 4 と operation.md worktree section に「マージ後の手順 (必ず順番通りに)」を追記。`--delete-branch` fallback と Tier A / B / C の archive 経路を明文化。
- [x] (2026-05-03 02:30Z) `python -m ai_ops check` 全パス、pytest 59 件 PASS。
- [ ] PR 作成、CI 通過、merge、archive、worktree-cleanup。

## Surprises & Discoveries

- (作業中に追記)

## Decision Log

- Decision: archive 自動化は本 plan では行わない。手順の明文化のみ。
  Rationale: `worktree-cleanup` に `--archive-plan` を追加して archive コミットまで自動化したいが、archive コミットを直接 main に push するのは ai-ops (Tier A) では OK でも Tier B 以上のプロジェクトでは禁止される (PR 経由必須)。tier ごとに分岐する CLI は複雑で、本 plan のスコープ外。手順を明文化して規律で守る方が単純。将来 tier 自動判定して archive PR を出す機能は別 plan で検討。
  Date/Author: 2026-05-03 / Claude.

- Decision: `deleteBranchOnMerge` をリポジトリ設定で true にする (gh CLI の `--delete-branch` フラグだけでは不確実)。
  Rationale: `gh pr merge --delete-branch` は API で deleteRef を呼ぶが、PR #2 / #3 の両方で stale branch が残った事実から、CLI フラグだけでは reliable ではないことが分かっている。GitHub 側のリポジトリ設定 `Automatically delete head branches` を有効化すれば、CLI のフラグに依存せず、Web UI からのマージや scheduled action からのマージでも常に削除される。
  Date/Author: 2026-05-03 / Claude.

- Decision: AGENTS.md の Subcommands 詳細リストは完全削除する (短縮ではなく)。
  Rationale: 中間案 (要約版を残す) は重複の温存。`docs/operation.md` の "CLI クイックリファレンス" が目的別グループ化された一覧を提供しており、flag 全部入りは `ai-ops --help` で取得できる。AGENTS.md には「CLI 一覧は operation.md と --help を見よ」の 1 行で足りる。
  Date/Author: 2026-05-03 / Claude.

## Outcomes & Retrospective

ship したもの:

1. リポジトリ設定 `deleteBranchOnMerge: true` を有効化 (`gh repo edit tekitounix/ai-ops --delete-branch-on-merge`)。`--delete-branch` フラグに依存せず、Web UI / scheduled action からのマージでも常に branch が削除される。
2. AGENTS.md を 152 → 109 行に短縮。Subcommands の 24 行詳細リストを完全削除し、`docs/operation.md` の "CLI クイックリファレンス" + `ai-ops --help` へ委譲。Lifecycle の sub-flow 列挙も `docs/operation.md` に集約。AI agent が起動毎に必読する AGENTS.md のロードコストが約 28% 軽減。
3. ADR 0010 Lifecycle 4 を改訂し、archive 手順 (Tier A は直 push、Tier B / C は archive PR)、`--delete-branch` の取りこぼし fallback、`worktree-cleanup` が両信号を要求する理由を明文化。
4. `docs/operation.md` worktree section に「マージ後の手順 (必ず順番通りに)」5 ステップを追加。エージェントが手順を毎回再発明しない。

残課題: なし。本 PR 自身がマージされた瞬間に「`deleteBranchOnMerge: true` で stale branch が残らない」ことを実地検証する。

今後の plan へのフィードバック: 「契約 (規約 / 設定) は明文化すると同時にツール / 設定で強制する」。`gh pr merge --delete-branch` フラグだけに頼っていた間、リポジトリ設定が `false` のまま気付かれず、PR #2 / #3 で連続して stale branch が残った。設定 + フラグ + 確認手順の 3 重化が realistic。

## Improvement Candidates

(作業中に追記)

## Context and Orientation

- AGENTS.md (152 行) の現状: §Workspace、§Lifecycle、§Plans、Subcommands、§Operation Model、§Safety、§Natural language、§Multi-agent、§Checks、§See Also。Subcommands は 24 行 (43-68)、Lifecycle 内 sub-flow リストは 8 行 (24-32)。
- `docs/operation.md` の現状: マスター運用ガイド。"目的別 sub-flow" 表 + "CLI クイックリファレンス" を持つ。
- `docs/decisions/0010-worktree-workflow.md`: 1:1:1 binding と `worktree-new` / `worktree-cleanup` の規約。archive 手順の明文化は無し。
- リポジトリ設定 `deleteBranchOnMerge`: 現状 `false`。`gh repo edit --delete-branch-on-merge` で `true` にできる。

## Plan of Work

1. **リポジトリ設定変更**: `gh repo edit tekitounix/ai-ops --delete-branch-on-merge`。
2. **AGENTS.md スリム化**:
   - Subcommands リスト (43-68 行) を削除し、「CLI 一覧は `docs/operation.md` の "CLI クイックリファレンス" と `ai-ops --help` を参照」の 1-2 行に置き換える。
   - Lifecycle セクションの sub-flow リストを「sub-flow 一覧と選び方は `docs/operation.md` を参照」に置き換える。
   - `migrate` flag、`new --nix` flag、Reproducibility tools、AI 重複 invocation の節は AGENTS.md 固有の契約として残す。
3. **ADR 0010 への追記**: "Plan archive lifecycle" セクションを追加。手順を明文化:
   ```
   PR merge → main を pull → docs/plans/<slug>/ を docs/plans/archive/YYYY-MM-DD-<slug>/ に git mv
   → archive コミット → push → ai-ops worktree-cleanup
   ```
   Tier 別の archive 経路 (Tier A は直 push、Tier B+ は archive PR) を明記。
4. **`docs/operation.md` への追記**: worktree-based parallel work セクションに「マージ後の手順 (branch 削除確認 + plan archive)」を追加。
5. **検証**: `python -m ai_ops check` で全パス確認。

## Concrete Steps

```sh
# 1. repository 設定変更
gh repo edit tekitounix/ai-ops --delete-branch-on-merge

# 2-4. ファイル編集 (Edit ツール)
$EDITOR AGENTS.md
$EDITOR docs/decisions/0010-worktree-workflow.md
$EDITOR docs/operation.md

# 5. 検証
python -m ai_ops check

# 6. push + PR
git add -A
git commit -m "chore(workflow): slim AGENTS.md + document archive lifecycle + enable auto branch deletion"
git push -u origin chore/workflow-hardening
gh pr create --title "..." --body "..."

# 7. merge 後 (delete-branch-on-merge が true なので branch は自動削除されるはず)
gh pr merge <N> --squash
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops
git pull
git mv docs/plans/workflow-hardening docs/plans/archive/2026-05-03-workflow-hardening
git commit -m "chore(plans): archive workflow-hardening plan"
git push
python -m ai_ops worktree-cleanup --auto

# 8. 確認: stale branch が無いこと
git ls-remote --heads origin
```

## Validation and Acceptance

- `python -m ai_ops audit lifecycle` exit 0。
- `python -m ai_ops check` exit 0。
- AGENTS.md 行数が 30+ 行短縮されている (現在 152 → 目標 110-120 行)。
- `gh repo view --json deleteBranchOnMerge` が `true` を返す。
- merge 後、`git ls-remote --heads origin` に `chore/workflow-hardening` が残っていない (今回が動作確認の機会)。
- ADR 0010 に "Plan archive lifecycle" セクションがある。

## Idempotence and Recovery

- リポジトリ設定変更は冪等 (再適用しても同じ状態)。元に戻すには `gh repo edit tekitounix/ai-ops --delete-branch-on-merge=false`。
- 各ファイル編集は git revert 可能。
- archive コミットは独立しており、PR の中身に影響しない。

## Artifacts and Notes

- PR URL: TBD
- 動作確認: 本 PR のマージで stale branch 残らないことを確認 → これが Step 2 の最終 acceptance test になる。

## Interfaces and Dependencies

- AGENTS.md: 公開契約。スリム化は破壊的に見えるが、内容は `docs/operation.md` に集約済みなので情報損失はない。
- ADR 0010: 既存。section 追加のみ。
- `docs/operation.md`: 既存。worktree section に手順追加のみ。
- リポジトリ設定: GitHub の `deleteBranchOnMerge`。public な可視変更は無し。
