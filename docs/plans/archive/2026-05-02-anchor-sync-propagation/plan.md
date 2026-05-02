# anchor-sync 反映機構(最小単位)

この ExecPlan は作業中に更新する living document です。

Plan path: `docs/plans/anchor-sync-propagation/plan.md`。採用後の archive path: `docs/plans/archive/YYYY-MM-DD-anchor-sync-propagation/`。

## Purpose / Big Picture

直前の `automated-propagation` プランをセルフ監査した結果、一気に三層を作るのは未決事項が多すぎて危険と判明し、増分の小プラン群に分割する方針に切り替えた。本プランはその第一弾で、最小ユニットだけを対象とする。

具体的には: 各管理プロジェクトの `.ai-ops/harness.toml` 内の `ai_ops_sha` フィールド(ai-ops のどのコミットに同期されているかを示すアンカー)を、現在の ai-ops HEAD に揃える PR を自動生成する仕組みを ai-ops に追加する。修正対象は `harness.toml` の `ai_ops_sha` と `last_sync` の二行だけで、user の作成物(`AGENTS.md`、`README.md`、active plans、source code)には一切触れない。

完了後は、ai-ops を改善しても各プロジェクトのアンカーが古いままになる(= harness drift の `ai_ops_sha_drift = true` が永続化する)状態を、PR 一回マージで解消できる。これが PR 駆動反映の最小可能版で、挙動が確認できれば次の段階(CI 配置、ファイル同期など)に拡張できる。

## Progress

- [x] (2026-05-02 06:50Z) 本プラン作成。`automated-propagation` の監査結果を起点に、最小スコープに絞り込んだ。
- [ ] `ai_ops/propagate.py` 新規追加: `_anchor_sync_targets()` と `_create_anchor_sync_pr()` を実装。
- [ ] `ai_ops/cli.py` に `propagate-anchor` サブコマンドを追加(`--all` / `--project <path>` / `--dry-run`)。
- [ ] `tests/test_propagate.py` 新規: 6 件以上の focused test。
- [ ] `python -m ai_ops check` 通過、`git diff --check` クリーン、commit + push。
- [ ] 実 use 確認: `propagate-anchor --dry-run --all` で対象プロジェクトと予定 PR が表示される。
- [ ] Verify / Adopt 完了時、本プランを archive に移動。

## Surprises & Discoveries

- Observation: `harness.toml` のフィールドは `ai_ops_sha`、`last_sync`、`[harness_files]` の 3 つだけ。`ai_ops_sha` は文字列で、形式チェックも 40 桁 hex 程度しか必要ない。
  Evidence: `ai_ops/audit/harness.py:42-66` の `HarnessManifest` schema。
  Implication: 「`ai_ops_sha` を現在の HEAD に書き換えて、`last_sync` を現在時刻に更新する」だけで完結する。touch する key は 2 個だけ。

- Observation: `harness.toml` 自体が untracked のプロジェクト(fastener-research のような)では、PR を立てられない。
  Evidence: 直前の Discovery で fastener-research の `.ai-ops/` 全体が untracked であることが判明。
  Implication: anchor-sync は「`harness.toml` が既に commit 済みのプロジェクト」だけを対象とする。untracked のプロジェクトは別途 user に「commit してくれ」と通知する形 skip する。

- Observation: `audit projects` の JSON 出力には `policy_drift` / `harness_drift` シグナルはあるが、「`ai_ops_sha` が古いだけ」かそれとも「ファイル内容も drift しているか」を区別する細かい情報は出ない。
  Evidence: `ai_ops/audit/projects.py:394-412` の `signals_to_dict()`。
  Implication: anchor-sync は audit 結果に頼らず、`harness.py:detect_drift()` を直接呼んで `ai_ops_sha_drift` だけを見る。`drift.modified` や `drift.missing` がある場合、anchor 更新だけでは不十分(ファイル内容が違うので)なので、anchor-sync は実行せず、別の小プランの担当に回す。

## Decision Log

- Decision: 修正対象は `.ai-ops/harness.toml` の `ai_ops_sha` と `last_sync` の二フィールドのみ。`[harness_files]` ハッシュテーブルは触らない。
  Rationale: ハッシュテーブルを更新するということは「ファイル内容を新しい canonical に揃えた」と主張することで、その作業はファイル内容の同期(別プラン)と必ずセットになる。anchor-sync 単独で `[harness_files]` を触ると、内容と manifest が乖離した状態を生む。
  Date/Author: 2026-05-02 / Codex

- Decision: `ai_ops_sha_drift` のみが drift シグナルで、`drift.missing` / `drift.modified` / `drift.extra` のいずれかが出ているプロジェクトは anchor-sync の対象外とする(skip)。
  Rationale: ファイル内容が違っているのに anchor だけ進めると「内容は古いまま、アンカーは新しい」状態になり、harness audit の信頼性が壊れる。これらは別プラン(ファイル同期)で扱う。
  Date/Author: 2026-05-02 / Codex

- Decision: `harness.toml` 自体が untracked のプロジェクトは対象外(skip)。エラーメッセージで「先に harness.toml を commit してください」と表示する。
  Rationale: PR は commit 済みのファイルに対してしか立てられない。untracked のものを勝手に git add するのは user 意図への介入。
  Date/Author: 2026-05-02 / Codex

- Decision: `git worktree` を使ってプロジェクト本体の作業ディレクトリには触れない。worktree 配置先は `~/.cache/ai-ops/worktrees/<project>-<branch>/` とする。
  Rationale: 各プロジェクトの本体ディレクトリには user の作業中ファイルがある。worktree なら本体に一切触れず、別ディレクトリで commit + push できる。`~/.cache/` 以下なら user の作業空間を汚さない。
  Date/Author: 2026-05-02 / Codex

- Decision: ブランチ命名は `ai-ops/anchor-sync-<short-sha>`(例: `ai-ops/anchor-sync-2d2a7bf`)。base ref はデフォルトブランチ(`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`)。
  Rationale: 命名で「ai-ops 由来」「anchor-sync 種類」「対象 sha」が判別できる。base はデフォルトブランチ固定で、user が作業中の feature branch に介入しない。
  Date/Author: 2026-05-02 / Codex

- Decision: 同じ `<short-sha>` の PR が既に open または closed で存在する場合は skip(冪等性)。force-push もしない。
  Rationale: 二重実行で同じ PR を重複作成しない。closed の同名 PR があれば「以前却下された」と判断できる情報なので、再作成しない。
  Date/Author: 2026-05-02 / Codex

- Decision: `--dry-run` はネットワーク呼び出しゼロ、ファイル書き込みゼロ、worktree 作成ゼロ。対象一覧と各 PR の予定内容(タイトル、body、変更行)を stdout に出すだけ。
  Rationale: 実 use 前に user が安心して挙動を確認できる。`bootstrap --dry-run` と同じパターン。
  Date/Author: 2026-05-02 / Codex

- Decision: 失敗時は worktree とローカルブランチを `try/finally` で必ず削除する。push 失敗・PR 作成失敗・どこで失敗しても、user の `git worktree list` に残骸が残らない。
  Rationale: 監査で挙げた重大な指摘の一つ。ユーザーに後始末を押し付けないことを実装上の保証とする。
  Date/Author: 2026-05-02 / Codex

- Decision: GitHub 以外のホスティング(GitLab、BitBucket 等)のプロジェクトは skip する。`gh repo view` が失敗するプロジェクトは「対象外」と明確に表示する。
  Rationale: `gh` CLI は GitHub 専用。silent fail せず、対象外であることを明示する。
  Date/Author: 2026-05-02 / Codex

- Decision: per-project confirmation を維持する。`--all` で複数プロジェクトを処理する場合も、各プロジェクトごとに「Y/n」を求める形にする(`bootstrap` の precedent ではなく、AGENTS.md の「project-specific harness overwrite は per-project 必須」を遵守)。
  Rationale: AGENTS.md Operation Model で project-specific harness overwrite は明示的に per-project confirmation 必須として列挙されている。`bootstrap` は ai-ops 自身のマシンへの install で別カテゴリ。本プランは別 repo の harness を触るので、precedent 流用は無理筋(これは `automated-propagation` の監査で発見された誤り)。
  Date/Author: 2026-05-02 / Codex

## Outcomes & Retrospective

Shipped (commits 7268c9c / d8453fc / f8d4cb8 / ef4f505 / 71fa9b2):

- `ai_ops/propagate.py` の anchor-sync 機構(worktree 隔離 + try/finally cleanup + per-project confirmation)
- `ai-ops propagate-anchor` サブコマンド(`--all` / `--project` / `--dry-run`)
- バグ修正 3 連発で実 use evidence を蓄積:
  - default branch 上の manifest 確認が必要(local HEAD では不十分、d8453fc)
  - `ai_ops_sha` だけ bump、`HarnessManifest.from_toml/to_toml` round-trip で他セクション・コメントが消える destructive bug を発見、regex-based text edit に置換(ef4f505)
  - 改行保持 regex の greedy 問題で空行が消える bug 修正(f3c7f09 — files-sync と共通)
  - Nix sandbox CI 互換のため `_ai_ops_head_sha` mock + `worktree_root` パラメータ追加(71fa9b2)

実 use 結果:
- audio-dsp-docs / fastener-research / fx-llm-research に 4 件の anchor-sync PR を作成、3 件は merge 済み(`f8d4cb8` で sync された状態)
- umipal #19 は umipal の audit ジョブ(Renode hardware compliance、20+ 分)待ちで pending、ai-ops 側からは加速不可

What remains:
- ai-ops の HEAD はその後 `f3c7f09` → `71fa9b2` → `3bf812d` → `d1b9a91` → `d329e8c` と進んだので、merged 3 project は再度 anchor-sync 候補(rsy=no)。次の運用 cycle で propagate-anchor を再ラン予定。

What should change in future plans:
- 「local 状態と remote 状態の semantic 区別」は最初から設計に明示する。今回は detector が local 起点だったため merge 直後の audit 出力が user に「propagate not done」と誤認させた。`remote_anchor_synced` signal の追加(別 plan f8d4cb8)で解消したが、最初から両 view を持つべきだった。

## Improvement Candidates

### policy_drift 種別ごとの修正コマンド群

- Observation: 本プランは `ai_ops_sha` バンプだけを扱うが、実際には `harness modified file` の同期、`policy stale` の plan schema 追加、`no-anchor` の初期化、CI ワークフロー配置、など複数の修正カテゴリが必要。
- Evidence: `automated-propagation` プランの監査結果。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — 各カテゴリで「user 作成物を触るか否か」が異なり、設計判断が必要。
- Verification: anchor-sync が安定動作したら、次のカテゴリ(`ci-workflow-propagation`)を別プランで起こす。
- Disposition: deferred — anchor-sync 完了後に着手。

### CI 配布経路の確定

- Observation: 各プロジェクトの CI で ai-ops を install する経路(`pip install git+url` か `nix run` か)が未確定。CI 配置プランより前に決める必要がある。
- Evidence: `automated-propagation` プランの監査で発覚。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — pyproject.toml に publish 設定を追加するか、git+url 前提で進めるかの選択。
- Verification: `ci-workflow-propagation` プランの前に、ADR か小プランで配布経路を確定する。
- Disposition: deferred — anchor-sync 完了後、`ci-workflow-propagation` に取りかかる前に決める。

### 単一プロジェクトの policy drift 検査コマンド

- Observation: `audit projects` は `ghq list -p` を歩く設計なので、CI 環境(単一 repo)で使えない。CI 用の単一プロジェクト検査コマンドが別途必要。
- Evidence: `automated-propagation` プランの監査で発覚。
- Recommended adoption target: `deferred`
- Confirmation needed: no — 単純な API 追加。
- Verification: `ci-workflow-propagation` プランで CI ワークフローを書く時に必要になる。
- Disposition: deferred — `ci-workflow-propagation` プランの一部として実装する。

### worktree 配置先の戦略

- Observation: 本プランは `~/.cache/ai-ops/worktrees/` に置くと決めたが、user 環境で `XDG_CACHE_HOME` が設定されている場合や macOS の `~/Library/Caches/` 慣例との整合性は検討していない。
- Evidence: 本プラン Decision Log。
- Recommended adoption target: `deferred`
- Confirmation needed: no — 配置先変更は後から差し替え可能。
- Verification: 実 use で問題が出れば変更検討。
- Disposition: deferred — 初版は `~/.cache/ai-ops/worktrees/` で十分、必要なら後で `XDG_CACHE_HOME` 対応。

## Context and Orientation

現在の relevant artifacts:

- `ai_ops/audit/harness.py` — `HarnessManifest` schema、`detect_drift()`、`_ai_ops_head_sha()`。本プランの中核 API。
- `ai_ops/audit/projects.py` — `audit projects` の JSON 出力。本プランは直接呼ばないが対象判定の参考にする。
- `ai_ops/audit/_canonical.py` — canonical schema 定数。本プランでは使わない。
- `ai_ops/bootstrap.py` — install 系の subcommand 実装パターンの参考。
- `gh` CLI — PR 作成と repo メタデータ取得に使用。

参照済み設計原則:

- AGENTS.md Operation Model: project-specific harness overwrite は per-project confirmation 必須。
- AGENTS.md Safety: silent な変更を禁ず、明示的な確認を経た操作は許可(自己改善ループにより既に前提化)。
- ADR 0008: 大きな external workflow framework を退ける。本プランも内部実装に閉じる。

## Plan of Work

1. `ai_ops/propagate.py` を新規追加する。中身は次の関数群:
   - `_list_anchor_sync_targets() -> list[Target]`: `ghq list -p` を歩き、各管理プロジェクトについて `harness.toml` を読み、(a) 存在する、(b) tracked、(c) `ai_ops_sha_drift` のみで `missing/modified/extra` がない、(d) GitHub にホストされている、を満たすものだけを Target として返す。
   - `_anchor_sync_one(target, ai_ops_head_sha, dry_run) -> Result`: 指定 Target について worktree を作り、`harness.toml` の `ai_ops_sha` と `last_sync` を更新するコミットを `ai-ops/anchor-sync-<short-sha>` ブランチに乗せ、push し、`gh pr create` で PR を立てる。dry_run なら全部 stdout に出すだけ。
   - `run_propagate_anchor(*, all, project, dry_run) -> int`: 上記をオーケストレーションする。`--all` 時は対象一覧を表示してから per-project に Y/n を求める。

2. `ai_ops/cli.py` に `propagate-anchor` サブコマンドを追加する。`--all` / `--project <path>` / `--dry-run` をサポート。

3. `tests/test_propagate.py` を新規追加する。focused test 6 件以上:
   - `harness.toml` 無しのプロジェクト → Target に含まれない
   - `harness.toml` untracked → Target に含まれない
   - `ai_ops_sha_drift` のみあり → Target に含まれる
   - `modified` ファイルあり → Target に含まれない(別プランの担当)
   - `--dry-run` → 副作用ゼロ、stdout に予定内容
   - 失敗時 worktree クリーンアップ → try/finally で削除されること

4. `python -m ai_ops check` で全テスト通過を確認、`git diff --check` クリーン、commit + push。

5. 実 use で `propagate-anchor --dry-run --all` を流し、対象プロジェクトと予定 PR が想定通り表示されることを確認。

## Concrete Steps

```sh
git status --short --branch  # クリーンな状態から始める
```

実装後:

```sh
python -m pytest tests/test_propagate.py tests/test_audit.py
python -m ai_ops audit lifecycle
python -m ai_ops propagate-anchor --dry-run --all
python -m ai_ops check
git diff --check
```

実 use 確認(user 確認の上で):

```sh
python -m ai_ops propagate-anchor --all
```

各プロジェクトで Y/n を求められ、Y で worktree → commit → push → PR 作成。各プロジェクトの本体作業ディレクトリには触れない。

## Validation and Acceptance

### Machine-checkable

- `ai_ops/propagate.py` が存在し、`_list_anchor_sync_targets()`、`_anchor_sync_one()`、`run_propagate_anchor()` が定義されている。
- `ai_ops/cli.py` に `propagate-anchor` サブコマンドが追加されている。
- `tests/test_propagate.py` の全テストが pass する(focused 6 件以上)。
- `python -m ai_ops check` PASS / FAIL = 0 / 0、`git diff --check` クリーン。
- `python -m ai_ops propagate-anchor --dry-run --all` が副作用ゼロで実行される。
- `propagate-anchor` の動作中に worktree が `~/.cache/ai-ops/worktrees/` に作られ、完了時(成功・失敗どちらも)に削除される(機械テストで `~/.cache/ai-ops/worktrees/` の中身が空に戻ることを確認)。

### Human-reviewable

- `propagate-anchor --dry-run --all` の出力が、ずれているプロジェクトと予定 PR の中身を分かりやすく表示している。
- 対象外のプロジェクト(GitHub 以外、`harness.toml` 無し / untracked、`modified` ファイルあり)が、それぞれ理由付きで「skip」と表示される(silent ではない)。

## Out of Scope

本プランで意図的に触らないもの:

- `[harness_files]` ハッシュテーブルの更新(別プラン: `harness-files-sync`)
- ファイル内容の同期(`AGENTS.md` の本文を canonical に合わせる、など)
- CI ワークフロー配置(別プラン: `ci-workflow-propagation`)
- policy drift の修正(active plans への section 追加など、user 作成物への介入)
- ローカル通知(別プラン: `notifier-installation`)
- AGENTS.md Safety 緩和(別プラン: 必要になった時点で)
- GitHub 以外のホスティング対応
- 同時並行実行(複数プロジェクトを並列に処理する)
- PR の自動マージ
- 自動 rebase / conflict 解決

## Idempotence and Recovery

- 同じ `<short-sha>` の PR が既に存在(open / closed どちらも)→ skip。
- worktree が既に存在 → 警告して skip(削除はしない、user の意図不明なため)。
- push 失敗 / PR 作成失敗 → worktree とローカルブランチを `try/finally` で削除。
- 全体は冪等で、何度走らせても同じ結果(ai-ops HEAD が変わらなければ何も起きない)。

## Artifacts and Notes

`ghq list -p` 配下で本プラン対象になりそうなプロジェクト(直前 Discovery 時点):

- mi_share、umipal、audio-dsp-docs、fx-llm-research — managed、`harness.toml` あり、ただし modified file の有無は再確認必要
- fastener-research — `.ai-ops/` 全体が untracked、対象外(skip 表示)
- note-md — unmanaged、対象外
- ai-ops 自身 — mgd=src、対象外

`ai_ops_sha_drift` だけの状態のプロジェクト数は、本プラン実装後の `propagate-anchor --dry-run --all` で確定する。

## Interfaces and Dependencies

- 新サブコマンド `ai-ops propagate-anchor` 追加
- `gh` CLI に依存(既に tier 1)
- worktree 配置先 `~/.cache/ai-ops/worktrees/`(新規ディレクトリ作成、user 確認なしで OK = 一般的なキャッシュ位置)
- 各 GitHub プロジェクトに `ai-ops/anchor-sync-<sha>` 命名のブランチが push される
- 各 GitHub プロジェクトに PR が立つ(main へのマージは user 判断、自動マージしない)
