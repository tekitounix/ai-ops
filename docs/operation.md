# ai-ops 運用ガイド

ai-ops の運用全体を理解するためのマスター入口である。まずこの文書を読み、必要に応じて各 deep-dive へ進む。

## ai-ops とは何か

ai-ops は、AI コーディングエージェント (Claude Code、Codex、Cursor など) に対して、複数プロジェクトを横断する共通の運用台本を repo にコミットして提供する仕組みである。台本の中身は、新規プロジェクトの立ち上げ、既存プロジェクトの取り込み、監査、変更の伝播。各プロジェクトは tier に応じた git ワークフロー規約 (ADR 0009) を持ち、並行作業は plan と 1:1:1 で結びついた sibling worktree で行い (ADR 0010)、ai-ops 自身の改善は GitHub-native な PR / Issue を経由して管理対象プロジェクトへ届く (ADR 0011)。通知の中心は使用者の GitHub Notifications。

## ライフサイクル

非自明な作業は次のフローを通る。

```text
Intake → Discovery → Brief → Proposal → Confirm → Agent Execute → Verify → Adopt
```

エージェントは状況を読み (Discovery)、プロジェクト固有の判断を Brief にまとめ、使用者が確認した後にはじめて通常のツールでファイルを変更する。各フェーズの詳細と Fact / Inference / Risk 分類は [`docs/ai-first-lifecycle.md`](ai-first-lifecycle.md) を参照。

## 目的別 sub-flow

| やりたいこと | 使う sub-flow | doc |
|---|---|---|
| 新規プロジェクトを始める | `ai-ops new` → Brief → 実行 | [`ai-first-lifecycle.md`](ai-first-lifecycle.md) |
| 既存プロジェクトを ai-ops 配下に取り込む | `ai-ops migrate <path>` → Brief → 実行 | [`project-addition-and-migration.md`](project-addition-and-migration.md) |
| 管理中プロジェクトの drift を修正 | `align this project` プロンプト → Brief → 実行 | [`realignment.md`](realignment.md) |
| repo を `~/ghq/...` 配下へ移動 | Phase 1 read-only Discovery → relocation Brief → 実行 | [`project-relocation.md`](project-relocation.md) |
| ghq 管理下の全プロジェクトを一括監査 | `audit my projects` プロンプト → 優先度ソート表 → 個別 sub-flow | [`projects-audit.md`](projects-audit.md) |
| ai-ops の改善を管理対象プロジェクトへ反映 | `propagate-anchor` / `propagate-init` / `propagate-files` → 各プロジェクトに PR | (CLI 一覧参照) |
| ai-ops 自身の作業を運用 | self-check + plans + ADR | [`self-operation.md`](self-operation.md) |

各 sub-flow は同じライフサイクル (Discovery → Brief → Confirm → Execute) を辿る。違いは scope と入口条件のみ。

## AI エージェントが従うワークフロー

ai-ops の運用の主体は AI エージェント (Claude Code、Codex、Cursor 等)。使用者は自然言語で「これをやって」「これを作って」「これを考えて」と意図を伝え、エージェントは下記のワークフローを自律実行する。

```text
[使用者: 自然言語で意図を伝える]
   │
   ▼
[AI エージェント: 規定ワークフローを自律実行]
   │
   ├─ ① Discovery (read-only) — repo / cwd を読む
   ├─ ② Brief 起草 — Fact / Inference / Risk / 推奨を構造化
   ├─ ③ 使用者に Confirm を求める  ★人間介入①
   │     (destructive / 環境変更 / 視認性変更 / 横断的編集 / harness 上書き / relocation 等)
   ├─ ④ ai-ops worktree-new <slug> — branch + worktree + plan skeleton
   ├─ ⑤ 作業実行 + plan を living document として更新
   │     (Progress / Surprises / Decision Log / Outcomes / Improvement Candidates)
   ├─ ⑥ ai-ops check で機械検査 (lifecycle / harness / security / nix / pytest)
   ├─ ⑦ commit + push + gh pr create
   ├─ ⑧ CI 待ち — managed-project-check.yml + ai-ops check
   ├─ ⑨ AI レビュー待ち — Copilot Code Review + ai-ops review-pr (ADR 0012)
   ├─ ⑩ Tier C なら人間レビュー待ち  ★人間介入② (Tier C のみ)
   ├─ ⑪ merge (Tier 別 ruleset が必須 status check を強制)
   ├─ ⑫ git pull + git mv で plan archive + push
   ├─ ⑬ ai-ops worktree-cleanup
   └─ ⑭ 使用者に完了報告
```

並行して **ai-ops repo の scheduled cron** が AI エージェントの介入なしに動く: `ecosystem-watch.yml` が週次で drift 検出 → Issue / sub-issue を open / update / close、`propagate-cron.yml` が週次で `propagate-* --auto-yes` → 各管理対象に PR 起票 → 上記ワークフローの入口に流れ込む、Renovate が `flake.lock` の定期 PR を生成。

**人間 (使用者) が介入する 3 点**:

1. **Confirm** — エージェントが Brief を出した時。destructive / 視認性 / 環境変更などの操作前。
2. **Tier C 最終レビュー** — PR の最終承認。CODEOWNERS + ruleset で強制される。
3. **AI レビュー request changes 時の対処判断** — 続行 / 修正 / override の判断。

それ以外 — branch 命名、worktree 作成、plan 更新、PR 起票、archive、cleanup、伝播 — はすべて AI エージェントまたは scheduled cron が自律実行する。

## 5 つの戦略 (Git / ghq / GitHub / Nix / plan)

ai-ops は以下のツールを「使うことが前提」として運用全体を組み立てている。各戦略は単独の ADR で詳細化されているが、ここでは横串で 1 文ずつ示す。

### Git 戦略

- **ブランチ命名**: `<type>/<slug>` (`feat` / `fix` / `chore` / `docs` / `refactor`)。短命ブランチ、PR 経由マージ、push 後の rebase は避ける。
- **マージ戦略**: squash merge を default。merge commit / rebase merge はプロジェクトごとに選択可だが、history は線形を志向。
- **Worktree**: 1 plan : 1 branch : 1 worktree の binding (ADR 0010)。sibling 配置 `<repo-parent>/<repo-name>.<slug>/`。1 repo あたり 3〜5 worktree が上限。
- **削除と archive**: マージ後の手順は本ドキュメントの「マージ後の手順」section + ADR 0010 §Lifecycle 4 を参照。
- **Hooks**: `--no-verify` で skip しない (ADR 0003)。pre-commit / pre-push を活用するが ai-ops は default では install しない (使用者責任)。

### ghq 戦略

- **配置**: 全 Git リポジトリは `~/ghq/<host>/<owner>/<repo>/` に置く (AGENTS.md §Workspace)。`~/work/` や `~/Documents/` 等の ad-hoc 配置は P0 drift。
- **enumerate**: `ghq list -p` で全プロジェクトをリストする canonical 経路。`ai-ops audit projects` はこれを walk する。
- **External / own の区別**: 自分の repo は `~/ghq/github.com/$(git config --get ghq.user)/<repo>/`、他者の repo は `~/ghq/<host>/<org>/<repo>/`。

### GitHub 戦略 (ADR 0011)

- **Visibility**: `gh repo create --public` は明示的な使用者確認が必須 (AGENTS.md §Safety)。
- **Tier 別 Ruleset**: `ai-ops setup-ruleset --tier {A,B,C}` で適用。Tier B 以上は PR 必須、Tier C は reviewer 必須 + signed commits + merge queue。
- **CODEOWNERS**: `ai-ops setup-codeowners` で ai-ops 関連変更をプロジェクト所有者にルーティング。
- **Repository 設定**: `Automatically delete head branches` を有効化 (`gh repo edit --delete-branch-on-merge`)。マージで branch が自動削除される。
- **Actions の 2 種**:
  - 各管理対象プロジェクト側に薄い caller workflow `.github/workflows/ai-ops.yml` (`ai-ops setup-ci-workflow`)。これが ai-ops の reusable `managed-project-check.yml` を呼び、PR と schedule で `audit harness --strict` を走らせる。
  - ai-ops 側に scheduled workflow `ecosystem-watch.yml` / `propagate-cron.yml`。週次 cron で全プロジェクトを監査し、Issue / sub-issue / 伝播 PR を自動生成。
- **通知**: 使用者の GitHub Notifications を中心通知チャネルとして活用。Issue / sub-issue / PR が標準 UI 経由で届く。

### Nix 戦略 (ADR 0005)

- **位置付け**: optional reproducibility layer。Tier 1 ツールに含まれるが install は使用者確認が必須 (AGENTS.md §Operation Model)。
- **採用判定**: Stage A / B / C rubric で AI が機械判定 (`auto`)。または `--nix devshell|apps|full|none` で明示。
- **Stack 別テンプレート**: `templates/artifacts/flake.nix.{minimal,node,python,xmake}` を `migrate --retrofit-nix` で導入。
- **更新**: Renovate (`templates/artifacts/renovate.json` + `update-flake-lock.yml`) が `flake.lock` の月次 / 週次 PR を自動生成。

### plan / ADR 戦略 (ADR 0006 / 0008)

- **Plan**: 非自明な作業は `docs/plans/<slug>/plan.md` に置き、`templates/plan.md` の canonical schema (12 section) に従う。`Branch` / `Worktree` / `Plan path` を冒頭に明記し、`Progress` / `Surprises & Discoveries` / `Decision Log` / `Outcomes & Retrospective` / `Improvement Candidates` を作業中に更新する。
- **Outcomes 完成は PR 前に必須**: `audit lifecycle` Phase 9 が「Progress 完了 AND Outcomes が TBD」を **FAIL** として返す。`ai-ops check` が CI で必須なら、Outcomes 未更新の PR は merge できない。
- **Archive**: マージ後 `git mv docs/plans/<slug> docs/plans/archive/YYYY-MM-DD-<slug>` でアーカイブ。`worktree-cleanup` は「PR merged + plan archived」の両信号が揃った worktree のみ削除する。
- **ADR**: load-bearing decision のみ `docs/decisions/NNNN-<slug>.md`。改廃時は新 ADR で superseded 情報を記録 (削除しない)。

### 責任分界 (AI エージェント自動 / scheduled cron 自動 / 人間判断)

「AI エージェント自動」は使用者の指示を受けて起動するエージェントが自律的に行う。「scheduled cron 自動」は ai-ops repo の GitHub Actions が定刻で起動し、誰の指示も介さずに動く。「人間判断」は使用者本人の判断と承認を要する。

| 領域 | AI エージェント自動 | scheduled cron 自動 | 人間判断 |
|---|---|---|---|
| **Git ブランチ** | `worktree-new` で作成、命名 (`<type>/<slug>`)、`worktree-cleanup` で削除 | `deleteBranchOnMerge: true` がマージ後に削除 | conflict 解消、rebase 判断 |
| **Git アーカイブ** | `git mv` で archive コミット → push (Tier A) または archive PR (Tier B/C) | `audit lifecycle` Phase 9 で Outcomes TBD を FAIL 検出 | (なし。エージェントが自律実行) |
| **Git Hooks** | (ai-ops は install しない) | (なし) | 使用者責任で pre-commit / pre-push を導入。`--no-verify` 禁止 |
| **ghq 配置** | 新規 repo を `~/ghq/<host>/<owner>/<repo>/` に作る | `audit projects` が DRIFT を P0 として検出 | `~/work/` 等からの relocation 承認 (各 Step ごと) |
| **ghq enumerate** | `audit projects` / `audit nix --report` で walk | (なし。エージェントが起動) | (なし) |
| **GitHub PR** | `gh pr create` で開設 | (なし。merge は人間 or エージェント) | PR 説明文確認、Tier C は最終承認 |
| **GitHub Issue / sub-issue** | (なし。中央 dashboard は cron が管理) | `ecosystem-watch.yml` が週次で open / update / close | Issue triage、誤検知時の close 判断 |
| **GitHub Ruleset** | `setup-ruleset --tier {A,B,C}` で `gh api` 経由適用 | (適用後は GitHub 側で常時強制) | Tier 宣言 (`harness.toml::workflow_tier`)、例外承認 |
| **GitHub CODEOWNERS** | `setup-codeowners` で初回配置 | (なし) | owner 追加 / 削除の手動編集 |
| **GitHub propagation** | (使用者が cwd で `propagate-*` を呼ぶ場合) | `propagate-cron.yml` が週次で `propagate-* --auto-yes` → PR 起票 | 各プロジェクトでの PR レビュー / merge |
| **PR レビュー (一層目)** | (なし) | GitHub Copilot Code Review が PR で自動実行 (有効化された repo のみ) | request changes 時の対処 |
| **PR レビュー (二層目、ADR 0012)** | `ai-ops review-pr --pr <N>` をローカル実行可 | `managed-project-review.yml` が PR で自動実行 | request changes 時の対処、override 判断 |
| **Nix flake 採用** | `migrate --retrofit-nix` でテンプレート導入 (使用者確認後) | `audit nix` が gap 検出 | Stage 判定の override、`--nix none` の justification |
| **Nix flake.lock 更新** | (なし) | Renovate (`update-flake-lock.yml`) が定期 PR 生成 | PR レビュー / merge |
| **Plan 作成** | `worktree-new` が canonical schema を seed、Purpose / Decision Log / Outcomes を記述 | (なし) | Outcomes の最終確認 (エージェントが書いたものをレビュー) |
| **Plan 完成検査** | (なし。ローカル / CI で `ai-ops check` を回す) | `ai-ops check` が CI で実行 (Outcomes TBD = FAIL、archive-ready = WARN、stale 30 日 = WARN) | Improvement Candidates の triage、disposition 判断 |
| **ADR 作成** | 新 ADR 起草 (使用者の Confirm 後) | (なし) | Propose → Confirm → Execute の Confirm |
| **言語ポリシー** | (エージェントが日本語で書く) | `audit lifecycle` Phase 11 が日本語比率 < 0.10 で FAIL | 翻訳判断、英語 / 日本語の使い分け |
| **Secret 検査** | (エージェントが commit 前に確認) | `audit security` が CI で実行、`gitleaks` (任意 install) | secret らしいファイルの除外判定 |

## ワークフロー tier (ADR 0009)

各管理対象プロジェクトは `.ai-ops/harness.toml::workflow_tier` で 4 段階の tier を宣言する。tier は期待される git 運用規範を決め、ai-ops は監査するが強制はしない。

- **Tier A — 軽量**: trunk-based、main への直接 push 可、CI は green 必須。ai-ops 自身、knx3 系の個人ツールなど。
- **Tier B — 管理**: feature branch + PR 必須、ブランチ保護あり。mi_share、audio-dsp-docs など。
- **Tier C — 本番 / 公開**: 上記に加えてレビュー承認、署名コミット、merge queue を要求。
- **Tier D — スパイク / 研究**: 何でもあり (long-lived branch も許容)。umipal phase-a、fx-llm-research など。

宣言が無い場合は D (最も寛容) として扱う。監査の `tier_violations` 信号は、宣言と実態が乖離した時に立つ。詳細定義と検出ルールは [ADR 0009](decisions/0009-git-workflow-tiers.md)。

## worktree ベース並行作業 (ADR 0010)

非自明な作業 (複数コミット、並行ストリーム、plan を要する任意の作業) では、次の 1:1:1 を維持する。

- **plan** 1 つ (`docs/plans/<slug>/plan.md`)
- **branch** 1 つ (`<type>/<slug>`、`<type>` は `feat`/`fix`/`chore`/`docs`/`refactor`)
- **worktree** 1 つ (`<repo-parent>/<repo-name>.<slug>/`、sibling 配置)

`ai-ops worktree-new <slug>` で 3 点セットを一気に作成し、canonical テンプレートから plan の skeleton を seed する。`ai-ops worktree-cleanup` は「PR がマージ済み AND plan が archive 済み」の両方が成立した worktree のみ削除する (安全のため両信号必須)。実用上の上限は 1 repo あたり 3〜5 worktree。詳しい規約は [ADR 0010](decisions/0010-worktree-workflow.md)。

### マージ後の手順 (必ず順番通りに)

1. PR をマージする (`gh pr merge <N> --squash`)。リポジトリ設定 `Automatically delete head branches` が有効ならリモートブランチは自動削除される。
2. プライマリ worktree (`main`) で `git pull --ff-only` してマージ結果を取り込む。
3. `git fetch --prune origin && git ls-remote --heads origin` でリモートブランチが消えていることを確認する。残っていたら `git push origin --delete <branch>` で除去 (`gh pr merge --delete-branch` のフラグだけでは取りこぼす実例があるため、リポジトリ設定 + 確認の二重化が必要)。
4. plan を archive する: `git mv docs/plans/<slug> docs/plans/archive/YYYY-MM-DD-<slug>` → `git commit -m "chore(plans): archive <slug> plan"` → push。Tier A (ai-ops 自身) は直接 `main` に push し、Tier B / C は archive 用に PR を 1 つ立ててマージする。
5. `ai-ops worktree-cleanup` (任意で `--auto`) で worktree を削除する。CLI は「PR merged + plan archived」の両方を信号として要求するので、ステップ 4 を飛ばすと cleanup 対象にならない。

## GitHub-native エコシステム運用 (ADR 0011)

ai-ops の主たる使用者向け表面は、ローカル CLI ではなく **GitHub Issues + sub-issues + Projects v2 ボード + scheduled Actions + Repository Rulesets + CODEOWNERS** である。drift 状況や伝播作業は使用者の既存の GitHub Notifications に乗る。

3 層構成。

1. **ai-ops repo がスケジュール workflow を回す** (`.github/workflows/ecosystem-watch.yml`、`propagate-cron.yml`)
   - 週次 cron で管理対象プロジェクトを監査 → 中央の "Ecosystem" 親 issue 配下に sub-issue を open / update / close
   - 週次 cron で `propagate-* --auto-yes` を実行 → 各管理対象プロジェクトに PR を open
2. **各管理対象プロジェクトに薄い caller workflow を配置** (`.github/workflows/ai-ops.yml`、opt-in は `ai-ops setup-ci-workflow`)。これは ai-ops 側の reusable `managed-project-check.yml` を呼び、PR と schedule で `audit harness --strict` を走らせる。Tier B 以上では Repository Ruleset により必須ステータスチェックになる。
3. **CODEOWNERS で ai-ops 関連変更をプロジェクト所有者にルーティング** (`ai-ops setup-codeowners`)。tier 別 ruleset (`ai-ops setup-ruleset --tier {A,B,C}`) で tier 規範を強制する。

drift 検出はローカルでもスケジュール GitHub Actions でも回り、結果は標準的な GitHub UI に Issue / sub-issue / PR として現れる。設計と setup フローの詳細は [ADR 0011](decisions/0011-github-native-operation.md)。

## PR レビュー (二層構成、ADR 0012)

機械検査 (CI) と人間レビュー (Tier C のみ強制) の間に AI レビュー層を二層挟む。

**一層目: GitHub Copilot Code Review**

- 汎用コード品質、bug、セキュリティを native レビュー。Copilot サブスク使用者が GitHub UI の repo Settings から有効化する。
- ai-ops は repo 設定の自動操作を行わない。各使用者が「この repo で有効化するか」を判断する。

**二層目: `ai-ops review-pr`** (新規)

- ai-ops 固有の規約レビュー。PR diff + 該当 repo の AGENTS.md + 全 ADR + harness.toml + (該当 plan があれば) plan.md を context として LLM に渡し、規約遵守を言語的に判定する。
- 出力は二チャネル: PR Comment (詳細を Markdown で投稿) と GitHub status check (`ai-ops AI Review` という context で `success` / `failure` / `neutral`)。
- `failure` のみ merge を止める。`neutral` は API キー未設定 / レビュー対象外などのスキップ状態。
- LLM プロバイダ: Anthropic Claude (`ANTHROPIC_API_KEY`) または OpenAI (`OPENAI_API_KEY`)。両方 secrets に無い場合は `neutral` を返して exit 0 (CI を壊さない)。
- 各管理対象プロジェクトでは reusable workflow `managed-project-review.yml` が `.github/workflows/ai-ops.yml` の `review` job から呼ばれて自動実行。ローカル開発時は `ai-ops review-pr --pr <N> --dry-run` で挙動確認できる。

**Tier 別必須化**:

- Tier A: `ai-ops AI Review` を必須にしない (Comment 投稿のみ、ruleset 対象外)。trunk-based 個人ツールの開発速度を維持。
- Tier B: `ai-ops AI Review` を必須 status check に追加 (`templates/artifacts/rulesets/tier-b.json`)。
- Tier C: `ai-ops AI Review` + 人間レビュー両方必須 (既存 ruleset に追加、`templates/artifacts/rulesets/tier-c.json`)。

詳細設計と決定事項は [ADR 0012](decisions/0012-pr-ai-review.md) を参照。

## plan 駆動実行 (ADR 0008)

非自明な作業は `docs/plans/<slug>/plan.md` で追跡する (canonical schema は [`templates/plan.md`](../templates/plan.md))。必須 section は Purpose / Big Picture、Progress、Surprises & Discoveries、Decision Log、Outcomes & Retrospective、Improvement Candidates、Context、Plan of Work、Concrete Steps、Validation and Acceptance、Idempotence、Artifacts、Interfaces。

plan は living document として、作業中に Progress / Surprises / Decision Log / Outcomes を更新し続ける。完了後 (Verify / Adopt 後) は `docs/plans/archive/YYYY-MM-DD-<slug>/` へ移動する。Progress 完了後も active ディレクトリに残った plan は lifecycle audit が WARN を出す。schema と採用ルールの詳細は [ADR 0008](decisions/0008-plan-persistence.md)。

## Improvement Capture ループ

各 plan は `Improvement Candidates` section を持つ。実行中の学びは `Recommended adoption target` (`current-plan` / `durable-doc` / `adr` / `template` / `audit` / `harness` / `test` / `deferred` / `rejected`) と `Disposition` (`open` / `adopted` / `deferred` / `rejected` / `superseded`) を付けて記録する。横断的または破壊的な adopt は Propose → Confirm → Execute を通す。詳細は [`self-operation.md`](self-operation.md) と [`ai-first-lifecycle.md`](ai-first-lifecycle.md)。

## CLI クイックリファレンス (目的別)

flag 全部入りの正本リストは [`AGENTS.md`](../AGENTS.md) の Subcommands、または [`README.md`](../README.md) の CLI 表を参照。

**セットアップ**
- `ai-ops new <name> --purpose "..."` — 新規プロジェクトの Brief
- `ai-ops migrate <path>` — 既存プロジェクトを ai-ops 配下に取り込み
- `ai-ops bootstrap` / `ai-ops update` — tier 1/2 ツールの install / 更新

**監査**
- `ai-ops audit projects` — ghq 管理下の全プロジェクトを一括監査 (priority + sub-flow を出力)
- `ai-ops audit harness` — `.ai-ops/harness.toml` と実ファイルの drift
- `ai-ops audit nix` — Nix 採用 gap
- `ai-ops audit security` — secret 名称スキャン
- `ai-ops audit lifecycle` — ai-ops 自身の self-audit
- `ai-ops check` — 上記すべて + pytest

**並行作業 (ADR 0010)**
- `ai-ops worktree-new <slug>` — branch + worktree + plan skeleton を作成
- `ai-ops worktree-cleanup` — PR merged + plan archived の worktree を削除

**ai-ops 改善の伝播 (ADR 0011)**
- `ai-ops propagate-anchor` — 管理対象プロジェクトの `ai_ops_sha` を bump
- `ai-ops propagate-init` — 未追跡 manifest を commit
- `ai-ops propagate-files` — `[harness_files]` ハッシュを refresh
- すべて CI / スケジュール実行向けに `--auto-yes` を受け付ける

**GitHub-native エコシステム setup (ADR 0011)**
- `ai-ops setup-ci-workflow --project PATH` — drift-check workflow を追加する PR
- `ai-ops setup-codeowners --project PATH` — CODEOWNERS routing を追加する PR
- `ai-ops setup-ruleset --project PATH --tier {A,B,C}` — Repository Ruleset を適用
- `ai-ops report-drift` — 監査結果を Issue / sub-issue ライフサイクルに翻訳 (ecosystem-watch workflow から呼ばれる)

## さらに読む

トピック別:

- **AI エージェント契約と横断ポリシー** → [`AGENTS.md`](../AGENTS.md)
- **ライフサイクル deep-dive** → [`ai-first-lifecycle.md`](ai-first-lifecycle.md)
- **マルチプロジェクト監査 playbook** → [`projects-audit.md`](projects-audit.md)
- **drift 修正** → [`realignment.md`](realignment.md)
- **物理的な relocation (`~/work/...` → `~/ghq/...`)** → [`project-relocation.md`](project-relocation.md)
- **ai-ops 自身の運用** → [`self-operation.md`](self-operation.md)

設計判断 (ADR) 別:

- [0001 AGENTS.md primary](decisions/0001-agents-md-as-primary.md)
- [0002 Portability first](decisions/0002-portability-first.md)
- [0003 Deletion policy](decisions/0003-deletion-policy.md)
- [0004 Secrets management](decisions/0004-secrets-management.md)
- [0005 Nix optional reproducibility layer](decisions/0005-nix-optional-reproducibility-layer.md)
- [0006 AI-first project lifecycle](decisions/0006-ai-first-project-lifecycle.md)
- [0007 Python canonical CLI](decisions/0007-python-canonical-cli.md)
- [0008 Plan persistence](decisions/0008-plan-persistence.md)
- [0009 Git workflow tiers](decisions/0009-git-workflow-tiers.md)
- [0010 Worktree workflow](decisions/0010-worktree-workflow.md)
- [0011 GitHub-native ecosystem operation](decisions/0011-github-native-operation.md)
- [0012 PR AI review (two-layer)](decisions/0012-pr-ai-review.md)
