# ai-ops 改善の自動反映機構

この ExecPlan は作業中に更新する living document です。`Progress`、`Surprises & Discoveries`、`Decision Log`、`Outcomes & Retrospective`、`Improvement Candidates` を作業の進行に合わせて更新します。

Plan path: `docs/plans/automated-propagation/plan.md`。採用後の archive path: `docs/plans/archive/YYYY-MM-DD-automated-propagation/`。

## Purpose / Big Picture

直前の `policy-drift-detection` plan(コミット `2d2a7bf`)で、ai-ops から各管理プロジェクトへのずれを検出する仕組みは入りました。しかし「検出」と「反映」は別物です。今は人間が定期的に `ai-ops audit projects` を思い出して走らせない限り、検出結果は誰の目にも入りません。各プロジェクトに対する反映の起動は完全に人間任せで、結果として「ai-ops を改善しても各プロジェクトには伝わらない」状態が続いています。

この plan の目的は、検出から反映までを摩擦なく回すための仕組みを ai-ops に追加することです。具体的には三層構造:

- 第一層: ai-ops 側に PR 駆動の反映サブコマンドを追加する。各管理プロジェクトに対して、ずれを修正するコミットを別ブランチに乗せて push し、`gh pr create` で PR を自動生成する。ユーザーは PR を見てマージするだけ。
- 第二層: 各プロジェクトの GitHub Actions に「ai-ops audit harness --strict」を走らせるワークフローを追加する。人間が見逃しても CI が止める。
- 第三層: ユーザー任意で、ローカルに launchd LaunchAgent をインストールし、週一で監査を走らせて macOS 通知を出す。

完了後は、ai-ops を改善するたびに各管理プロジェクトに PR が届き、ユーザーは自分のタイミングでレビューしてマージするだけ、という Renovate / Dependabot 相当の運用になります。

## Progress

- [x] (2026-05-02 06:20Z) 初版 plan を作成。三層構造(PR 駆動・CI・通知)と Decision Log 8 件をロック。
- [ ] AGENTS.md Safety を「絶対禁止」から「明示的な確認を経れば許可」に書き換える(`bootstrap` の運用と整合させる)。
- [ ] `ai_ops/propagate.py` 新規追加: `_detect_propagation_targets()` と `_create_drift_pr()` を実装。
- [ ] `ai_ops/cli.py` に `propagate` サブコマンドを追加。`--all` / `--project <path>` / `--dry-run` をサポート。
- [ ] CI ワークフローテンプレート `templates/artifacts/ai-ops-drift.yml` を新規追加。`ai-ops propagate` がこれを各プロジェクトに配置する。
- [ ] `ai_ops/notifier.py` 新規追加: `install_notifier()` と `uninstall_notifier()` を実装。
- [ ] `ai-ops install-notifier` / `uninstall-notifier` サブコマンドを追加。
- [ ] `tests/test_propagate.py` と `tests/test_notifier.py` に focused test を追加。
- [ ] `docs/realignment.md` と `docs/projects-audit.md` に新サブコマンドの位置付けを追記。
- [ ] `README.md` の Quick start に「PR が来たらレビューしてマージするだけ」の運用を追記。
- [ ] `python -m ai_ops check` で全テスト通過、`git diff --check` クリーン、commit + push。
- [ ] Verify / Adopt 完了時、この plan を `docs/plans/archive/2026-05-02-automated-propagation/` に archive。

## Surprises & Discoveries

- Observation: AGENTS.md Safety の「OS scheduler を install しない」「環境ファイルを変更しない」という絶対禁止は、ai-ops の `bootstrap` コマンドが既に nix / direnv / ghq を install している運用と論理的に矛盾している。
  Evidence: `ai-ops bootstrap` の挙動と `AGENTS.md` Safety 節。`bootstrap` は明示的なユーザー確認のもとで install を行うが、Safety 節はそれを「禁止」と書いている。
  Implication: Safety 節の表現が古い。本質は「silent な変更を禁ず」であって「明示的な確認を経た install を禁ず」ではない。書き換えが必要。

- Observation: 既に 7 管理プロジェクトのうち 6 つに作業途中の状態があり、AGENTS.md などへの直接書き込みは衝突リスクがある。
  Evidence: 直前の Discovery(umipal 30+ 修正、mi_share 16 ファイル、audio-dsp-docs 58 修正、fx-llm-research 91 ファイル)。
  Implication: 反映は別ブランチに乗せて PR を開く形にすれば、現在の作業中ブランチや作業中ファイルには一切干渉しない。`git worktree add` を使えば、ユーザーの作業ディレクトリすら触らずに済む。

- Observation: `gh` CLI が AGENTS.md tier 1 ツールとして既にインストール対象になっている。
  Evidence: `AGENTS.md` の `bootstrap` 説明 「git / ghq / direnv / jq / gh / nix at tier 1」。
  Implication: PR 自動生成に外部 GitHub App や bot は不要。`gh pr create` を直接呼べば済む。

- Observation: ai-ops 自身に既に `audit projects` の JSON 出力がある(`--json` フラグ)。propagate はこの出力を読むだけで対象を判定できる。
  Evidence: `ai_ops/audit/projects.py:474-524` の `run_projects_audit()`。
  Implication: 既存の検出ロジックを再実装する必要はない。propagate は audit を呼んで JSON を解釈するレイヤーとして実装できる。

## Decision Log

- Decision: 反映方式は **PR 駆動** とする。直接 main へのコミットや force push はしない。各プロジェクトの main に変更を入れるのはユーザーがマージしたときに限る。
  Rationale: ユーザーの判断を必ず経由する設計。各プロジェクト固有の事情(独自カスタマイズや延期理由)を ai-ops が一律に上書きしない。Renovate / Dependabot と同じ業界標準パターン。
  Date/Author: 2026-05-02 / Codex

- Decision: 各プロジェクトでの作業は `git worktree add` を使って別ディレクトリで実行する。元の作業ディレクトリと作業中ブランチには一切触れない。
  Rationale: 6 管理プロジェクトすべてに作業途中の状態があった現実に合わせる。worktree なら現在の状態を完全に保ったまま、ai-ops 側の修正を別の作業空間で乗せられる。
  Date/Author: 2026-05-02 / Codex

- Decision: PR ブランチ命名規約を `ai-ops/<change-id>` で固定する。例: `ai-ops/policy-drift-20260502`、`ai-ops/harness-sync-20260502`。
  Rationale: ユーザーが PR 一覧を見たときに ai-ops 由来と判別しやすい。同じ projection から複数 PR が来ても重複しない。
  Date/Author: 2026-05-02 / Codex

- Decision: per-project confirmation を維持する。ただし `--all` 実行時は対象一覧を事前提示し、ユーザーの一回の許可で全件処理を進める方式を許す(Operation Model の「複数 step を 1 confirmation で済ませる」例外節に該当)。
  Rationale: Operation Model の精神(ユーザーが必ず確認する)を満たしつつ、6 件の確認を 6 回に分けない。`bootstrap` が複数ツールの install 一覧を一度に提示して一度の確認で進めるのと同じパターン。
  Date/Author: 2026-05-02 / Codex

- Decision: CI 統合は **opt-in**(`ai-ops propagate` の選択肢の一つ)。各プロジェクトに既存 CI がある場合は重複を避ける検出を入れる。
  Rationale: プロジェクトによっては GitHub Actions を使っていない(GitLab CI、CircleCI、CI なし、など)。一律の押し付けは避ける。
  Date/Author: 2026-05-02 / Codex

- Decision: ローカル通知層(launchd LaunchAgent)も **opt-in**。`ai-ops install-notifier` の明示的な実行が必要。`uninstall-notifier` でいつでも削除可能。
  Rationale: 通知の頻度や種類はユーザーの好みに依存する。デフォルトで install しない。明示的に install するときも、生成する plist の中身を表示してから書き込む。
  Date/Author: 2026-05-02 / Codex

- Decision: AGENTS.md Safety 節を書き換える。「絶対禁止」から「明示的な Propose → Confirm → Execute を経れば許可」へ。`bootstrap` の運用と整合させる。
  Rationale: 現在の Safety 節は `bootstrap` の挙動と論理的に矛盾している。書き換えで矛盾を解消し、`propagate` と `install-notifier` の運用を明示的に許可された形にする。同時に「silent な変更は禁ず」の本質は強化する。
  Date/Author: 2026-05-02 / Codex

- Decision: 外部 GitHub App、自前 bot infrastructure、ホスト型サービスへの依存は導入しない。`gh` CLI のみで完結させる。
  Rationale: ai-ops は repo-local に閉じた CLI で運用される。外部 infrastructure は維持コストと依存リスクが大きい。`gh` は既に tier 1 ツール。
  Date/Author: 2026-05-02 / Codex

## Outcomes & Retrospective

**Superseded** — 着手前のセルフ監査で複数の重大な未決事項が判明したため、本プランは実装せず、増分の小プラン群に分割して置き換える。

判明した重大な未決事項:

1. `propagate` がずれの種類ごとに何を書き換えるかが未定義(設計の核心が空)。`stale` で user の active plan を自動編集するのか、`harness modified` で user の編集を巻き戻すのか、など根幹の挙動が未確定。
2. CI の `pip install ai-ops` が動かない(PyPI 未公開)。`pip install git+url` または `nix run` への切り替えが必要。
3. CI ワークフローが `audit harness --strict` だけで policy drift を見ない。policy drift の単一プロジェクト検査コマンドが ai-ops に未実装で、新規実装が必要。
4. per-project confirmation と batch 確認の解釈が緩い。AGENTS.md は project-specific harness overwrite を per-project 必須として明示列挙しており、`bootstrap` の precedent を流用する論拠は弱い。
5. 失敗時のクリーンアップ(worktree、ローカルブランチ)が手動指示になっている。
6. PR body 構造未定義、ブランチ base ref 未指定、GitHub 前提が暗黙、realignment との関係未整理、Safety 緩和の具体要件が広すぎる、隔離保証のテストが手動 — 中程度の問題が多数。

**置き換え方針(増分小プラン群):**

- `anchor-sync-propagation`: 最小ユニット。`harness.toml` の `ai_ops_sha` 更新 PR だけを対象とする。user content には一切触れない。
- (次の段階) `ci-workflow-propagation`: GitHub Actions 配置 PR 専用。配布経路問題を先に解く必要があるため、anchor-sync が動いてから着手。
- (次の段階) `single-project-policy-audit`: CI 用に必要な「単一プロジェクトの policy drift 検査」コマンド。
- (将来) `notifier-installation`: 第三層、独立性が高いので最後。

このプランで企てた三層構造の方向性自体は妥当だが、一つのプランに詰め込みすぎた。各層を独立した小プランで増分実装し、各段階で挙動を確認してから次へ進める。

shipped: 0 件(本プランは superseded)。
本プラン執筆と監査により得られた成果: ai-ops 自体への自動反映機構の設計上の制約が明文化されたこと。次のプランはこの制約を出発点として書ける。

## Improvement Candidates

### ai-ops 自身の自動更新

- Observation: `ai-ops` 自体のバージョン更新は今回の scope 外。各プロジェクトに反映する仕組みは作るが、ai-ops 自体を最新に保つ仕組みは別話題。
- Evidence: 本 plan の Out of Scope。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — `ai-ops` の自動更新は `nix` / `pip` / `pipx` / `uv` のどの経路で配布されているかに依存する。
- Verification: ai-ops のリリース頻度が増えて手動更新が摩擦になったら検討。
- Disposition: deferred — 現状リリース頻度は低く、`bootstrap` / `update` の手動実行で足りる。

### 中央集権ダッシュボード

- Observation: 全管理プロジェクトのずれ状況を一覧表示する web UI / static page を作る案もあるが、`audit projects` のターミナル出力で十分。
- Evidence: 本 plan の Out of Scope。
- Recommended adoption target: `rejected`
- Confirmation needed: no — 過剰設計。
- Verification: n/a
- Disposition: rejected — ターミナル + PR で目視できれば足りる。Web UI の維持コストに見合わない。

### Slack / Discord / メール通知

- Observation: macOS 通知だけでなく、Slack や Discord や メールに通知を送る案もある。今回は scope 外。
- Evidence: 本 plan の Out of Scope。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — チーム運用に発展した場合に検討する。
- Verification: 単独ユーザー運用から複数人運用に切り替わったタイミングで再評価。
- Disposition: deferred — 現状単独ユーザー運用、macOS 通知で十分。

### 自動マージ

- Observation: 開いた PR を自動マージする仕組み(GitHub の auto-merge 機能、merge queue など)もあるが、人間レビューを残すのが本 plan の本質。
- Evidence: 本 plan Decision Log の「PR 駆動」決定理由。
- Recommended adoption target: `rejected`
- Confirmation needed: no — 設計理念に反する。
- Verification: n/a
- Disposition: rejected — レビュー無しのマージは Operation Model の精神に反する。

### CI ワークフローテンプレートのバージョン管理

- Observation: 各プロジェクトに配置した `.github/workflows/ai-ops-drift.yml` を後から更新する仕組み(例: workflow 自体の version pin と更新通知)も将来必要になる可能性がある。
- Evidence: 本 plan で CI 統合を入れた直後の自然な拡張。
- Recommended adoption target: `deferred`
- Confirmation needed: no — `propagate` の追加機能として後から入れられる。
- Verification: workflow を 2 回以上更新する必要が出たら検討。
- Disposition: deferred — 初版は静的なテンプレートで十分。

## Context and Orientation

現在の relevant artifacts:

- `ai_ops/audit/projects.py` — `audit projects` の本体。`policy_drift` / `harness_drift` シグナルを既に持つ。`propagate` はここの JSON 出力を入力として使う。
- `ai_ops/audit/_canonical.py` — canonical schema 定数。propagate がプロジェクトに適用すべき修正の基準。
- `ai_ops/audit/harness.py` — harness drift 検出と manifest 操作。propagate は `_ai_ops_head_sha()` を使って anchor 更新を行う。
- `ai_ops/bootstrap.py` — 既存の install 系コマンド。propagate / install-notifier の実装パターンの参考。
- `docs/realignment.md` / `docs/projects-audit.md` — propagate の位置付けを追記する対象。
- `templates/artifacts/` — 既存のテンプレート(flake.nix.minimal、renovate.json 等)。CI ワークフローテンプレートを追加する場所。

参照済みの設計原則:

- AGENTS.md Operation Model: Propose → Confirm → Execute、batch approval は事前提示で例外的に可。
- AGENTS.md Safety: silent な変更を禁ず(改訂後)。
- ADR 0008: 大きな external workflow framework は退ける。
- 直前の policy-drift-detection plan: 検出のみ、反映は人間判断。本 plan はその「人間判断」を「PR レビュー」に置き換える発展形。

## Plan of Work

1. AGENTS.md Safety 節を改訂する。「OS scheduler を install しない」「環境ファイルを変更しない」を「silent な変更を禁ず、明示的な Propose → Confirm → Execute を経た install / 変更は許可」に書き換える。`bootstrap` の運用と整合させる。

2. `ai_ops/propagate.py` を新規追加する。中身は次の関数群:
   - `_detect_propagation_targets(audit_json) -> list[Target]`: `audit projects` の JSON 出力を読み、ずれがあるプロジェクトと修正内容を列挙する。
   - `_apply_drift_fix_in_worktree(target) -> Path`: `git worktree add` で別ディレクトリを作り、`ai-ops/<change-id>` ブランチで修正をコミットする。worktree のパスを返す。
   - `_create_drift_pr(target, worktree_path) -> str`: `gh pr create` で PR を開き、URL を返す。
   - `run_propagate(*, all=True, project=None, dry_run=False) -> int`: 上記をオーケストレーションする。`--dry-run` では実行内容を表示するだけ。

3. `ai_ops/cli.py` に `propagate` サブコマンドを追加する。`--all` / `--project <path>` / `--dry-run` をサポート。`--all` は対象一覧を表示してから一度の確認で全件進める。

4. `templates/artifacts/ai-ops-drift.yml` を新規追加する。`pip install ai-ops` → `ai-ops audit harness --strict` を PR で走らせる GitHub Actions ワークフロー。

5. `propagate` の修正種類に「CI ワークフロー追加」を含める。各プロジェクトに `.github/workflows/ai-ops-drift.yml` が無ければ、配置する PR を立てる。既存ワークフローがあれば skip する。

6. `ai_ops/notifier.py` を新規追加する。中身:
   - `_generate_launchagent_plist(audit_command, schedule) -> str`: launchd 用 plist を生成する。
   - `install_notifier(*, dry_run=False) -> int`: plist の中身を表示し、ユーザー確認を取り、`~/Library/LaunchAgents/` に書き込んで `launchctl load` する。
   - `uninstall_notifier() -> int`: `launchctl unload` して plist を削除する。

7. `ai_ops/cli.py` に `install-notifier` / `uninstall-notifier` サブコマンドを追加する。

8. `tests/test_propagate.py` を新規追加する。focused test 5 件以上:
   - drift 無しのプロジェクト → 何もしない
   - drift ありのプロジェクト → worktree 作成 + ブランチ作成 + コミット + (mock の) `gh pr create` 呼び出し
   - 既存ワークフローが GitHub Actions 以外 → CI 追加を skip
   - `--dry-run` → 副作用ゼロで実行内容を表示
   - `--all` で複数プロジェクトを順次処理

9. `tests/test_notifier.py` を新規追加する。focused test 3 件以上:
   - plist 生成内容の検証
   - install/uninstall の副作用が `~/Library/LaunchAgents/` に限定されること
   - `dry_run` で実際の launchctl 呼び出しが起きないこと

10. `docs/realignment.md` の Phase 3 に「`ai-ops propagate --project <path>` で PR を立てる選択肢を提示」を追記する。

11. `docs/projects-audit.md` の Phase 4 verify に「propagate 後の `audit projects` 再実行で確認」を追記する。

12. `README.md` の Quick start に第 4 のプロンプト「`ai-ops propagate --all` を走らせて、届いた PR を順にレビューしてマージする」を追記する。

13. `python -m ai_ops check` で全テスト通過を確認、`git diff --check` クリーン、commit + push。

## Concrete Steps

repository root から:

```sh
git status --short --branch
```

Expected: 本 plan ファイル以外に unrelated local changes が無い。

実装後:

```sh
python -m pytest tests/test_propagate.py tests/test_notifier.py tests/test_audit.py
python -m ai_ops audit lifecycle
python -m ai_ops propagate --dry-run --all
python -m ai_ops check
git diff --check
```

Expected: 全テスト通過、`propagate --dry-run` で各管理プロジェクトの予定された PR 内容が表示される、副作用ゼロ。

`propagate --all` の実 use(ユーザー確認の上で):

```sh
python -m ai_ops propagate --all
```

Expected: 対象プロジェクト一覧が表示され、ユーザー確認の後、各プロジェクトに worktree 経由で PR が立つ。元の作業ディレクトリと作業中ブランチには一切触れない。

## Validation and Acceptance

### Machine-checkable

- `ai_ops/propagate.py` と `ai_ops/notifier.py` が存在し、`ai_ops/cli.py` に `propagate` / `install-notifier` / `uninstall-notifier` サブコマンドが追加されている。
- `templates/artifacts/ai-ops-drift.yml` が存在し、`pip install ai-ops` → `ai-ops audit harness --strict` を実行する GitHub Actions ワークフローとして valid。
- `tests/test_propagate.py` と `tests/test_notifier.py` の全テストが pass する。
- `python -m ai_ops check` PASS / FAIL = 0 / 0、`git diff --check` クリーン。
- `python -m ai_ops propagate --dry-run --all` が副作用ゼロで実行内容を表示する。
- `AGENTS.md` Safety 節が改訂され、「明示的な Propose → Confirm → Execute を経た install / 変更は許可」と明示されている。

### Human-reviewable

- `propagate --all` が PR を立てる挙動が、各管理プロジェクトの作業中ブランチや作業中ファイルに一切干渉しないこと(worktree 隔離が機能していること)を実 use で確認。
- `install-notifier` が plist の中身を表示してから書き込むこと、`uninstall-notifier` で完全に削除されることを実 use で確認。
- AGENTS.md Safety 節の改訂が `bootstrap` の運用と論理的に整合していること。

fail した場合は、どの criteria がどの理由で fail したかをこの plan の `Outcomes & Retrospective` に記録する。

## Out of Scope

この pass で意図的に触らないもの(各 Improvement Candidate に対応):

- ai-ops 自身の自動更新(`ai-ops update --self` のようなセルフアップデート機構)
- 中央集権ダッシュボード(web UI、static status page)
- 外部 GitHub App、自前 bot infrastructure、ホスト型サービス
- Slack / Discord / メール通知(macOS 通知のみ)
- 開いた PR の自動マージ(常に人間レビューを介する)
- CI ワークフロー自体のバージョン管理(初版は静的テンプレート)
- Linux / Windows 用の通知実装(初版は macOS の launchd のみ)
- ローカル状態の複数マシン間同期

## Idempotence and Recovery

`propagate` の各操作はべき等性を持たせる:

- 同じ修正の PR が既に open なら、新しく立てずに既存 PR を更新する(または skip する)。
- worktree の作成は同名ディレクトリがあれば skip する(既存 worktree を使う)。
- worktree は `propagate` 完了時に削除する。失敗時は手動で `git worktree remove --force <path>` で復旧できる。

`install-notifier` は plist が既に存在すれば内容を比較し、変化があれば置き換える前に diff を表示する。`uninstall-notifier` は冪等で、何もない状態でも安全に呼べる。

AGENTS.md Safety 節の改訂は通常の Git diff review で完全に reversible。

## Artifacts and Notes

直前 plan の引き継ぎ事項:

- `docs/plans/policy-drift-detection/plan.md` — 検出機構を ship した plan。本 plan はその発展形。
- `docs/plans/self-improvement-loop/plan.md` — Improvement Candidates schema を入れた plan。本 plan の対象になる canonical schema の出処。
- 直前 Discovery 結果: 7 管理プロジェクトのうち 6 つに作業途中の状態。worktree ベースの設計はこの現実への対応。

`audit projects --json` の現状(2026-05-02 時点):

- P0: umipal(sec + harness drift + policy stale)
- P1: mi_share / audio-dsp-docs / fastener-research / fx-llm-research / note-md
- P2: ai-ops 自身、knx3、validation 4 件

`propagate --all` 実装後の期待値: P0/P1 計 6 件のプロジェクトに、それぞれ修正内容に応じた PR が立つ。

## Interfaces and Dependencies

この plan は以下に影響しうる:

- ai-ops CLI の subcommand 一覧(`propagate`、`install-notifier`、`uninstall-notifier` 追加)
- AGENTS.md Safety 節の表現(絶対禁止 → 確認を経れば許可)
- 各管理プロジェクトに開かれる PR(別ブランチ、main には自動マージしない)
- 各管理プロジェクトの `.github/workflows/` への opt-in 配置
- `~/Library/LaunchAgents/` への opt-in 配置(macOS 限定、ユーザー確認必須)

新規 runtime dependency: 既に tier 1 で扱われている `gh` CLI に依存する形になる。`gh` 未インストール環境では `propagate` は明確なエラーで terminate する(silent fail はしない)。
