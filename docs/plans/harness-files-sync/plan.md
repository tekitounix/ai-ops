# harness-files-sync 反映機構

増分シリーズ第三弾。`anchor-sync-propagation` と `init-harness-propagation` で SHA アンカーと初期 manifest 配置は届くようになった。残る未達領域の最大のものが file content drift で、`umipal` と `mi_share.ai-ops-setup` で観測されている。本プランは propagate-files を追加してこれを解消する。

## Purpose / Big Picture

各管理プロジェクトの `.ai-ops/harness.toml` の `[harness_files]` ハッシュが、実際の default branch 上のファイル内容と乖離している状態を解消する仕組みを追加する。

セマンティクス: ファイルの **内容 (AGENTS.md の本文など) は user 側が canonical**。manifest の `[harness_files]` ハッシュは「ai-ops audit が検出した時点の状態の記録」に過ぎない。よって drift があった場合、解消方法は「ファイル内容を ai-ops 側に合わせる」ではなく「manifest ハッシュを実ファイルに合わせる」が正しい(これは `migrate --update-harness` がやっていることの PR 版)。

完了後、harness file drift の項目(modified / missing / extra)があるプロジェクトに対して、`[harness_files]` を refresh する PR が自動生成される。マージすれば `audit harness` の drift が消える。

## Progress

- [x] (2026-05-02 09:45Z) プラン作成。anchor-sync + init-harness と同じパターンで propagate-files を設計。
- [ ] `ai_ops/propagate.py` に `_replace_harness_files_section` ヘルパーを追加(TOML の他セクション・コメントを保護)。
- [ ] `FilesSyncTarget` dataclass + `list_files_sync_targets` + `files_sync_one` + `run_propagate_files` を追加。
- [ ] CLI に `propagate-files` サブコマンド追加。
- [ ] tests に focused test 4 件以上(section 置換、preservation 回帰、targets 抽出、dry-run)。
- [ ] `python -m ai_ops check` + commit + push + CI watch。
- [ ] 実 use: `propagate-files --dry-run --all` で対象が umipal / mi_share.ai-ops-setup 等で出ることを確認。
- [ ] Verify / Adopt 完了時に archive。

## Surprises & Discoveries

- Observation: `[harness_files]` の semantic は「ai-ops が canonical だと考えるハッシュ」ではなく「project が前回の sync 時点で持っていたハッシュ」。よって drift 解消は user 側ファイルへの合わせ込み(manifest 更新)であって、ファイル内容の上書きではない。
  Evidence: `ai_ops/audit/harness.py:detect_drift` の比較ロジックは「manifest の hash vs 実ファイルの hash」だけで、「ai-ops 側にこの内容があるはず」という比較はしていない。manifest は purely 「last sync state」を記録する。
  Implication: propagate-files は anchor-sync よりさらに無害。ファイル内容そのものに触れず、manifest の hash table だけを更新する。

- Observation: anchor-sync は `_bump_anchor_in_manifest_text` で 2 行だけを regex 置換することで他セクション・コメントを保護した。同じパターンを `[harness_files]` セクション全体の置換に拡張できる。
  Evidence: `ai_ops/propagate.py:_bump_anchor_in_manifest_text`。
  Implication: `(?ms)^\[harness_files\][^\[]*` のような regex でセクション全体を抽出・置換すれば、`[project_checks]` 等の他セクションは触れない。

## Decision Log

- Decision: ファイル内容そのものは触らない。`[harness_files]` セクションの **ハッシュテーブルだけ** を default branch の実ファイル内容に合わせて refresh する。
  Rationale: manifest は recording 用、user の手書き AGENTS.md などは project canonical。ai-ops から prescriptive に上書きする設計はそもそも誤り。
  Date/Author: 2026-05-02 / Codex

- Decision: ハッシュ計算には worktree 内の(= origin/<default-branch> から checkout した)ファイル内容を使う。user の作業中コピーは使わない。
  Rationale: anchor-sync と同じ「default branch のスナップショットを真とする」原則。user の uncommitted edits を意図せず PR に乗せるリスクをゼロにする。
  Date/Author: 2026-05-02 / Codex

- Decision: `[harness_files]` セクションを置換する際、`ai_ops_sha` / `last_sync` / 他セクション(`[project_checks]` など)/ コメントは一切触らない。anchor-sync の `_bump_anchor_in_manifest_text` と同じ「ターゲットだけ regex で部分置換」アプローチ。
  Rationale: umipal の destructive PR 事故と同じ轍を踏まない。
  Date/Author: 2026-05-02 / Codex

- Decision: drift の `missing` (manifest にあって disk に無い) は manifest からその entry を削除、`extra` (disk にあって manifest に無い) は entry 追加、`modified` は hash 更新。3 種類すべて 1 つの PR で解決。
  Rationale: drift はセットで発生することが多い(例: ファイルを deprecate した時 missing と extra が同時に出る)。一括解消が user の review 負荷を下げる。
  Date/Author: 2026-05-02 / Codex

- Decision: ブランチ命名は `ai-ops/files-sync-<short-sha>` (`<short-sha>` は ai-ops HEAD)。
  Rationale: anchor-sync (`ai-ops/anchor-sync-<sha>`) と init (`ai-ops/init-harness-<sha>`) と同じ命名規約に揃える。
  Date/Author: 2026-05-02 / Codex

- Decision: per-project confirmation を維持。`--all` 実行時も各プロジェクトで Y/n 確認(harness overwrite なので Operation Model 準拠)。
  Rationale: anchor-sync / init-harness と同じ方針。
  Date/Author: 2026-05-02 / Codex

- Decision: anchor-sync 同様、worktree 経由で隔離。`worktree_root` パラメータでテストから差し替え可能(Nix sandbox 互換性)。
  Rationale: 既存パターンの踏襲。
  Date/Author: 2026-05-02 / Codex

## Outcomes & Retrospective

TBD。

## Improvement Candidates

### `propagate-all` 統合コマンド

- Observation: `propagate-anchor`、`propagate-init`、`propagate-files` を順に走らせる場面が多そう。`propagate --all-types` のように一括実行する shorthand があれば user 体験が良い。
- Evidence: 本プランで 3 種類目の propagator が揃う。
- Recommended adoption target: `deferred`
- Confirmation needed: no — 既存サブコマンドを呼ぶだけのラッパー。
- Verification: 実 use で「3 つを順に呼ぶ手間」がペインになったら追加検討。
- Disposition: deferred — 当面は個別コマンドで運用、需要が見えたら統合。

### ファイル内容そのものの伝播

- Observation: 本プランは hash refresh のみ。ai-ops の canonical な policy 文書(`docs/ai-first-lifecycle.md` 等)の本文改訂を managed projects に届ける仕組みは未実装。
- Evidence: 本プランの Purpose / Decision Log。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — 各 project の独自カスタマイズを尊重しつつ更新提案する設計が複雑。
- Verification: ai-ops の docs 改訂が実 use で「届かなくて困る」状況になったら本格設計。
- Disposition: deferred — 現状の audit 検出 + chat route の「align this project」プロンプトで足りている。

### 手動 hash 編集の検出

- Observation: user が手で `[harness_files]` の hash を書き換えた場合、propagate-files は新しい hash で「上書き」してしまう(user の意図的編集を消す)。
- Evidence: 設計上の theoretical concern。
- Recommended adoption target: `deferred`
- Confirmation needed: no — 実害が出てから設計検討。
- Verification: そういう運用が観測されるかどうか。
- Disposition: deferred — manifest の hash 値は本来 user が手で編集する性質のものではない(machine-managed)ため、想定外のケース。

## Context and Orientation

- `ai_ops/propagate.py` — 既存 `_bump_anchor_in_manifest_text` パターンの拡張。
- `ai_ops/audit/harness.py:detect_drift` — file drift の正確な検出ロジック。
- `ai_ops/audit/harness.py:HARNESS_MANIFEST` / `DEFAULT_HARNESS_FILES` — 検出スコープ。

## Plan of Work

1. `ai_ops/propagate.py` に `_replace_harness_files_section(text, new_files)` ヘルパー追加。`(?ms)^\[harness_files\][^\[]*` regex で既存セクションを抽出 → 新エントリで置換。セクションが無い場合は append。

2. `FilesSyncTarget(dataclass)` を追加。fields: `project_path`, `default_branch`, `repo_full_name`, `drift: HarnessDrift`(対象 drift)。

3. `list_files_sync_targets(ai_ops_root, project_paths=None)` 追加:
   - 各 managed project に対して
   - `gh_repo_metadata` で default branch 取得 + `git fetch origin <default>`
   - `_harness_toml_on_branch(project, "origin/<default>")` で manifest 存在確認
   - default branch 上のファイルから `detect_drift` 相当を計算(working copy ではなく remote tracked snapshot を使うため、git ls-tree などで対応)
   - `missing/modified/extra` のいずれかがあれば target に追加

4. `files_sync_one(target, *, dry_run, worktree_root)` 追加:
   - worktree 作成(branch from origin/<default>)
   - worktree 内のファイルから新 `[harness_files]` 計算
   - manifest text を `_replace_harness_files_section` で更新
   - commit + push + `gh pr create`
   - try/finally で worktree クリーンアップ

5. `run_propagate_files(*, ai_ops_root, project, all_projects, dry_run)` 追加。

6. `ai_ops/cli.py` に `propagate-files` サブコマンド + `handle_propagate_files` ハンドラ追加。

7. `ai_ops/audit/lifecycle.py` の `README_CLAIMED_SUBCOMMANDS` に `propagate-files` 追加。

8. `tests/test_propagate.py` に focused test 4 件以上:
   - section 置換が他のセクション・コメントを保護する
   - missing/modified/extra すべてのケースで PR 内容が正しい
   - dry-run で副作用ゼロ
   - target 抽出で drift 無しプロジェクトはスキップ

9. `AGENTS.md` の subcommand 一覧と `README.md` に `propagate-files` を追記。

10. `python -m ai_ops check` 通過、commit + push、CI watch。

11. 実 use 確認: `propagate-files --dry-run --all` で umipal / mi_share.ai-ops-setup が出ることを確認、actual run で PR 作成 → review → merge。

## Concrete Steps

```sh
python -m pytest tests/test_propagate.py
python -m ai_ops audit lifecycle
python -m ai_ops propagate-files --dry-run --all
python -m ai_ops check
git diff --check
```

## Validation and Acceptance

### Machine-checkable

- `_replace_harness_files_section` がコメント・他セクションを保持する(テスト)。
- `list_files_sync_targets` が `missing/modified/extra` の少なくとも 1 つを持つプロジェクトを返す。
- CLI subcommand `propagate-files` が `--help` に応答する。
- `python -m ai_ops check` 通過、CI 全ジョブ green。

### Human-reviewable

- 実 use の `propagate-files --dry-run --all` で、umipal / mi_share.ai-ops-setup 等の file drift プロジェクトが対象として表示される。
- 生成された PR の diff が `[harness_files]` セクションのみで、他コンテンツ無変更。

## Out of Scope

- ファイル内容そのものの propagation(別話題)
- `harness_files` 以外のセクション(`project_checks` など)の同期
- `ai_ops_sha` の同時 bump(別 propagate-anchor の責務)
- DEFAULT_HARNESS_FILES に含まれない追加ファイルの自動検出
- 自動 merge

## Idempotence and Recovery

- 同一 SHA の PR が open 済み → skip
- worktree は try/finally でクリーンアップ
- drift 解消後の再実行は no-op(target list が空)

## Artifacts and Notes

実 use 時の期待対象(2026-05-02 時点):
- umipal: `modified=1` (AGENTS.md)
- mi_share.ai-ops-setup: `modified=1`

## Interfaces and Dependencies

- 新サブコマンド `ai-ops propagate-files`
- 既存依存(`gh`、worktree path)
- 各 GitHub プロジェクトに `ai-ops/files-sync-<sha>` ブランチ + PR
