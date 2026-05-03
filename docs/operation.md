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

### 責任分界 (自動 / 手動)

| 領域 | 自動 (ツール / 設定 / scheduled action が常時実行) | 手動 (使用者 / AI エージェントの判断と作業) |
|---|---|---|
| **Git ブランチ** | `worktree-new` で作成、`worktree-cleanup` で削除、`deleteBranchOnMerge: true` でマージ後削除 | branch 名 (`<type>/<slug>`) と plan slug の一致確認、conflict 解消、rebase 判断 |
| **Git アーカイブ** | `audit lifecycle` が active plan の hygiene 検査 (Outcomes TBD は FAIL) | `git mv` での archive コミット (Tier A: 直 push、Tier B/C: archive PR) |
| **Git Hooks** | (ai-ops は install しない) | 使用者責任で pre-commit / pre-push を導入。`--no-verify` 禁止 |
| **ghq 配置** | `audit projects` が DRIFT を P0 として検出 | `~/work/` 等からの relocation (`docs/project-relocation.md` 手順、各 Step ごとに承認) |
| **ghq enumerate** | `ai-ops audit projects` / `audit nix --report` で walk | (なし。常時自動) |
| **GitHub PR** | `gh pr create` で開設、CI 自動実行、`deleteBranchOnMerge` で枝削除 | PR 説明文 / レビュー承認 / squash merge 判断 |
| **GitHub Issue / sub-issue** | `ecosystem-watch.yml` が週次で audit → Issue / sub-issue を open / update / close | Issue triage、close 判断 (誤検知時) |
| **GitHub Ruleset** | `setup-ruleset --tier {A,B,C}` で `gh api` 経由適用、ruleset が PR で必須 check を強制 | Tier 宣言 (`harness.toml::workflow_tier`)、ruleset 例外承認 |
| **GitHub CODEOWNERS** | `setup-codeowners` で初回配置 | owner 追加 / 削除の手動編集 |
| **GitHub propagation** | `propagate-cron.yml` が週次で `propagate-{anchor,init,files} --auto-yes` → 各プロジェクトに PR | 各プロジェクトでの PR レビュー / merge |
| **Nix flake 採用** | `audit nix` が gap 検出、`migrate --retrofit-nix` でテンプレート導入 (使用者確認後) | Stage 判定の override、`--nix none` 選択時の justification 記述 |
| **Nix flake.lock 更新** | Renovate (`update-flake-lock.yml`) が定期 PR 生成 | PR レビュー / merge |
| **Plan 作成** | `worktree-new` が canonical schema を seed | Purpose / Decision Log / Outcomes など中身の記述 |
| **Plan 完成検査** | `audit lifecycle` Phase 9 (Outcomes TBD = FAIL、archive-ready = WARN、stale 30 日 = WARN) | Outcomes 記述、Improvement Candidates の triage と disposition |
| **ADR 作成** | (テンプレート無し。canonical schema は load-bearing decision を要する場合のみ) | 新 ADR 起草 → AGENTS.md Operation Model で Propose → Confirm → Execute |
| **言語ポリシー** | `audit lifecycle` Phase 11 (`docs/*.md` 日本語比率 < 0.10 で FAIL) | 翻訳判断、英語 / 日本語の使い分け |
| **Secret 検査** | `audit security` が cwd を name + value scan、`gitleaks` (任意 install) | secret らしいファイルの除外判定、commit 前確認 |

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
