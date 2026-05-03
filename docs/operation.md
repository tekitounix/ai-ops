# ai-ops 運用ガイド

ai-ops の運用を 1 ファイルで把握できるマスターガイド。深い背景は [`docs/decisions/INDEX.md`](decisions/INDEX.md) と各 sub-flow doc を参照。

## ai-ops とは

AI コーディングエージェント (Claude Code、Codex、Cursor 等) に複数プロジェクトを横断する共通の運用台本を提供する仕組み。台本は repo にコミット済み。使用者が自然言語で意図を伝え、エージェントが台本に従って自律実行する。

## ライフサイクルとサブフロー

非自明な作業はすべて次のフローを通る。詳細フェーズと Fact / Inference / Risk 分類は [`ai-first-lifecycle.md`](ai-first-lifecycle.md)。

```text
Intake → Discovery → Brief → Proposal → Confirm → Agent Execute → Verify → Adopt
```

入口は意図別に分かれる:

| やりたいこと | 使うコマンド / プロンプト | doc |
|---|---|---|
| 新規プロジェクト | `ai-ops new` | [`ai-first-lifecycle.md`](ai-first-lifecycle.md) |
| 既存プロジェクトを取り込み | `ai-ops migrate <path>` | [`project-addition-and-migration.md`](project-addition-and-migration.md) |
| drift 修正 | `align this project` プロンプト | [`realignment.md`](realignment.md) |
| `~/ghq/` 配下へ移動 | relocation Brief | [`project-relocation.md`](project-relocation.md) |
| 全プロジェクト監査 | `audit my projects` プロンプト | [`projects-audit.md`](projects-audit.md) |
| ai-ops 自身の運用 | self-check + plans + ADR | [`self-operation.md`](self-operation.md) |

## AI エージェントが従うワークフロー

主体は AI エージェント。使用者は自然言語で意図を伝え、エージェントが下記を自律実行する。

```text
[使用者: 自然言語で意図]
   ▼
[AI エージェント]
 ① Discovery (read-only) → ② Brief 起草
   → ③ ★Confirm (destructive / 環境変更 / 視認性 / 横断的編集 等)
   → ④ ai-ops worktree new <slug>
   → ⑤ 作業 + plan を living document として更新
   → ⑥ ai-ops check (lifecycle / harness / security / nix / pytest)
   → ⑦ commit + gh pr create
   → ⑧ CI 待ち (managed-project-check.yml)
   → ⑨ AI レビュー待ち (Copilot + ai-ops review-pr)
   → ⑩ ★Tier C なら人間レビュー待ち
   → ⑪ merge → ⑫ archive (Tier 別) → ⑬ ai-ops worktree cleanup → ⑭ 完了報告

[並行: ai-ops repo の scheduled cron]
 ecosystem-watch.yml (週次) — drift → Issue / sub-issue
 propagate-cron.yml  (週次) — propagate --auto-yes → 各管理対象に PR
 Renovate           — flake.lock 定期 PR
```

**人間が介入する 3 点**:

1. **Confirm** (③) — Brief 後の destructive / 環境 / 視認性 / 横断的操作の承認
2. **Tier C 最終レビュー** (⑩) — CODEOWNERS + ruleset で強制
3. **AI レビュー request changes 時の対処** — 続行 / 修正 / override の判断

これら以外 (branch 命名、worktree 作成、plan 更新、PR 起票、archive、cleanup、伝播) は AI エージェントまたは scheduled cron が自律実行する。

### secret 扱いの 5 原則 (ADR 0004)

AI エージェントは秘匿情報を扱う場面で次を守る。詳細と禁止リストは [ADR 0004](decisions/0004-secrets-management.md)。

1. secret 値を含む外部コマンド (`bw`, `gh secret`, `op` 等) の output は **subprocess 内で消費**、stdout / チャットに流さない。
2. session token / API key 値が必要なときは shell 内手順 (例: `export BW_SESSION=$(bw unlock --raw)`) を案内し、**値そのものをチャットで受け取らない**。
3. 使用者の Confirm を `echo y` で bypass せず、正規 `--yes` flag を要求する。
4. secret 関連操作後は「rotation 推奨かどうか」を露出の有無 + threat model から判断して明示する。
5. 不正確な報告 (「unset した」「クリアした」) を避け、消えた範囲と残る範囲を分けて伝える。

`audit security` の `SECRET_ARG_FORBIDDEN_PATTERNS` が違反を機械検出して FAIL を返す。規律 + 監査の二重で守る。

## 5 つの戦略

ai-ops は Git / ghq / GitHub / Nix / plan を「使うことが前提」として全体を組み立てる。各戦略の深い背景は [`decisions/INDEX.md`](decisions/INDEX.md) を参照。

- **Git** ([ADR 0009](decisions/0009-git-workflow-tiers.md), [0010](decisions/0010-worktree-workflow.md)): branch 命名 `<type>/<slug>`、squash merge、1 plan : 1 branch : 1 worktree (sibling 配置、3〜5 / repo 上限)、`--no-verify` 禁止、`deleteBranchOnMerge: true`。
- **ghq** (AGENTS.md §Workspace): 全 repo は `~/ghq/<host>/<owner>/<repo>/`。`ghq list -p` が enumerate の正本。`audit projects` がこれを walk。
- **GitHub** ([ADR 0011](decisions/0011-github-native-operation.md), [0012](decisions/0012-pr-ai-review.md)): Tier 別 Ruleset、CODEOWNERS、scheduled Actions (`ecosystem-watch` / `propagate-cron` / Renovate)、reusable workflow (`managed-project-{check,review}.yml`)、二層 PR レビュー。
- **Nix** ([ADR 0005](decisions/0005-nix-optional-reproducibility-layer.md)): default-required reproducibility layer。Stage A/B/C rubric で AI が機械判定。Renovate が `flake.lock` を定期 PR。
- **Plan / ADR** ([ADR 0006](decisions/0006-ai-first-project-lifecycle.md), [0008](decisions/0008-plan-persistence.md)): `docs/plans/<slug>/plan.md` の canonical schema、Outcomes 完成は audit で必須化、archive は `git mv` (Tier A は直 push、Tier B/C は archive PR)、ADR は load-bearing decision のみ。

### 責任分界 (AI エージェント自動 / scheduled cron / 人間判断)

| 領域 | AI エージェント自動 | scheduled cron 自動 | 人間判断 |
|---|---|---|---|
| ブランチ / worktree | `worktree new/cleanup`、命名 | `deleteBranchOnMerge` でマージ後削除 | conflict 解消、rebase 判断 |
| アーカイブ | `git mv` で archive (Tier 別) | `audit lifecycle` で Outcomes TBD = FAIL | (なし) |
| ghq 配置 | 新規 repo を `~/ghq/...` に作成 | `audit projects` が DRIFT を P0 検出 | relocation 各 Step 承認 |
| GitHub PR | `gh pr create` | (なし) | PR 説明確認、Tier C 最終承認 |
| Issue / sub-issue | (中央 dashboard は cron) | `ecosystem-watch.yml` が weekly | triage、誤検知 close |
| Ruleset / CODEOWNERS | `setup ruleset` / `setup codeowners` で適用 | (適用後は GitHub 側で常時強制) | Tier 宣言、例外承認 |
| 伝播 (propagation) | (使用者が `propagate` を呼ぶ場合) | `propagate-cron.yml` が weekly | 各 PR レビュー / merge |
| PR レビュー | `ai-ops review-pr --pr <N>` (ローカル) | Copilot Code Review、`managed-project-review.yml` | request changes 時の対処 |
| Nix 採用 | `migrate --retrofit-nix` | `audit nix` が gap 検出 | Stage 判定 override |
| flake.lock | (なし) | Renovate 定期 PR | レビュー / merge |
| Plan 作成 / 完成 | `worktree new` で seed、内容記述 | `audit lifecycle` Phase 9 (Outcomes TBD = FAIL) | Outcomes 最終確認、IC triage |
| ADR | 起草 (Confirm 後) | (なし) | Propose → Confirm → Execute |
| 言語ポリシー | (日本語で書く) | `audit lifecycle` Phase 11 が比率 < 0.10 で FAIL | 翻訳判断 |
| Secret | (commit 前確認) | `audit security` / gitleaks | 例外判定 |

## ワークフロー tier (ADR 0009)

各管理対象は `.ai-ops/harness.toml::workflow_tier` で 4 段階を宣言する。tier は期待される運用規範を決め、ai-ops は監査するが強制はしない。宣言が無ければ **D** (最も寛容) として扱う。`tier_violations` は宣言と実態の乖離を示す。詳細: [ADR 0009](decisions/0009-git-workflow-tiers.md)。

| Tier | 規範 | 例 |
|---|---|---|
| **A** 軽量 | trunk-based、main 直 push 可、CI green 必須 | ai-ops 自身、knx3 系 |
| **B** 管理 | feature branch + PR 必須、ブランチ保護、AI レビュー必須 | mi_share、audio-dsp-docs |
| **C** 本番 / 公開 | 上記 + reviewer 承認 + signed commits + merge queue | 公開 OSS |
| **D** スパイク | 何でもあり (long-lived branch も許容) | umipal phase-a、研究 repo |

## マージ後の手順 (必ず順番通りに)

1. `gh pr merge <N> --squash` (`deleteBranchOnMerge: true` でリモート枝は自動削除)。
2. プライマリ worktree (`main`) で `git pull --ff-only`。
3. `git fetch --prune origin && git ls-remote --heads origin` で確認。残っていれば `git push origin --delete <branch>`。
4. plan を archive: `git mv docs/plans/<slug> docs/plans/archive/YYYY-MM-DD-<slug>` → commit → push。Tier A は直 push、Tier B/C は archive PR を立てる。
5. `ai-ops worktree cleanup` (任意 `--auto`) で worktree を削除。

## CLI クイックリファレンス

正本リストは `ai-ops --help`。flag 全部入りは各 subcommand の `--help`。

```text
ai-ops new <name> --purpose "..."        新規プロジェクト Brief
ai-ops migrate <path>                    既存取り込み
ai-ops bootstrap [--with-secrets]        Tier 1/2 ツール install (+ Bitwarden 経由 secrets)
ai-ops update                            ツール更新
ai-ops audit {lifecycle,harness,nix,security,projects,standard}  各種監査
ai-ops check                             全 audit + pytest
ai-ops promote-plan <slug>               local plan を repo plan に昇格
ai-ops worktree {new,cleanup}            sibling worktree 管理 (ADR 0010)
ai-ops propagate --kind {anchor,init,files}  管理対象に PR で伝播 (ADR 0011)
ai-ops setup {ci,codeowners,ruleset}     管理対象の GitHub 統合 (ADR 0011)
ai-ops report-drift                      audit 結果を Issue / sub-issue に翻訳
ai-ops review-pr --pr <N>                PR を AI でレビュー (ADR 0012)
```

## さらに読む

- 設計判断: [`decisions/INDEX.md`](decisions/INDEX.md) (12 ADR の 1 行 summary)
- AI エージェント契約: [`AGENTS.md`](../AGENTS.md)
- ライフサイクル deep-dive: [`ai-first-lifecycle.md`](ai-first-lifecycle.md)
- 監査 playbook: [`projects-audit.md`](projects-audit.md)
- drift 修正: [`realignment.md`](realignment.md)
- 物理 relocation: [`project-relocation.md`](project-relocation.md)
- ai-ops 自身の運用: [`self-operation.md`](self-operation.md)
