# Strategies Consolidation

Branch: `docs/strategies-consolidation`
Worktree: `../ai-ops.strategies-consolidation/`

## Purpose / Big Picture

ai-ops は Git / ghq / GitHub / Nix を「デフォルトで前提とするツール」として運用全体を組み立てているが、その戦略 (ブランチ命名、worktree 配置、PR 経路、Ruleset、CODEOWNERS、scheduled Actions、Nix gap 検出、Renovate 等) が ADR 0005 / 0008 / 0009 / 0010 / 0011 に分散している。エージェントは横断して再構成しなければ全体像をつかめない。

加えて、各戦略について「どこから自動化されていて」「どこは人間 (使用者または AI エージェント) の判断や手動作業に依っているか」が明文化されていない。例として「PR 出す前に plan の Outcomes を更新する」は規約だが、技術的強制 (audit FAIL) が無いため Outcomes 未完成のまま PR が出る事故が連発している (Step 1 / 2 で実例)。

本 plan は次の 2 つを 1 PR で行う。

1. **戦略の集約**: `docs/operation.md` に "Strategies (Git / ghq / GitHub / Nix / plan)" セクションを追加し、各戦略を 1 行で示し、深い ADR に link する。各戦略について「自動化 / 手動」を明示する責任分界表 (Responsibility Matrix) を 1 表で提示する。
2. **未実装の強制機構の追加**: `audit lifecycle` Phase 9 の「Progress 完了 AND Outcomes が TBD」検出を WARN → FAIL に昇格 (`ai-ops check` が落ちるようになる)。これにより `ai-ops check` を CI で必須にしている本 repo では、Outcomes 未更新の PR がマージできなくなる。

完了後、エージェントは `docs/operation.md` を読むだけで「ai-ops の戦略 5 系統」と「自動化境界」を把握できる。Outcomes 未更新は CI で機械的に止まる。

## Progress

- [x] (2026-05-03 02:45Z) Initial plan drafted.
- [x] (2026-05-03 02:55Z) `_check_plan_hygiene` を `(warnings, failures)` 戻り値に変更し、Outcomes TBD を failures に分類。`run_lifecycle_audit` で fail カウントに加算。既存テスト 4 件を新シグネチャに追従、回帰テスト 1 件追加 (合計 60 件 PASS)。
- [x] (2026-05-03 03:05Z) `docs/operation.md` に「5 つの戦略 (Git / ghq / GitHub / Nix / plan)」セクションと 16 行の責任分界表を追加。
- [x] (2026-05-03 03:08Z) AGENTS.md §Lifecycle and CLI、README.md "How does ai-ops work?"、README.ja.md「ai-ops の運用ってどうやるの」に新セクションへの pointer 追加。
- [x] (2026-05-03 03:10Z) `python -m ai_ops check` 全パス確認。
- [ ] PR 作成、CI 通過、merge、archive、worktree-cleanup。

## Surprises & Discoveries

- (作業中に追記)

## Decision Log

- Decision: 集約先は新規文書ではなく `docs/operation.md` 内のセクション。
  Rationale: 直前の Step 2 で AGENTS.md を 152 → 109 行に減らした方針と一貫。文書を増やすほどエージェントが横断する負担が増える。`docs/operation.md` は既にマスター運用ガイドで、Workflow tiers / Worktree / GitHub-native の section を抱えている。"Strategies and Responsibility Matrix" を 1 つ追加する方が認知負荷が小さい。
  Date/Author: 2026-05-03 / Claude.

- Decision: Outcomes 検査は WARN → FAIL に昇格 (PR check 追加ではなく既存 audit を強化)。
  Rationale: 既存の `_check_plan_hygiene` が「Progress 完了 AND Outcomes が TBD」を既に検出しているが、WARN なので `audit lifecycle` の exit code に影響しない。これを fail 扱いにすれば、`ai-ops check` を必須化している本 repo の CI で機械的に止まる。新規 workflow を追加するより設定値の変更が単純。
  Date/Author: 2026-05-03 / Claude.

- Decision: 「自動化 vs 手動」の表は Strategies セクションの末尾に置く。
  Rationale: 戦略を 5 行で示してから「誰が何をやるか」を表で見せると、戦略 → 責任の流れが自然。表だけでは戦略の意図が伝わらず、戦略だけでは責任分界が曖昧。
  Date/Author: 2026-05-03 / Claude.

## Outcomes & Retrospective

ship したもの:

1. **戦略集約** — `docs/operation.md` に「5 つの戦略 (Git / ghq / GitHub / Nix / plan)」セクションを追加。各戦略を 3-5 行で示し、深い ADR / CLI / 設定への pointer を箇条書き。末尾に 16 行の責任分界表 (自動 / 手動) を配置し、エージェントが「どこから手で介入し、どこは自動で動くか」を一望できる。
2. **Outcomes 強制** — `_check_plan_hygiene` を `(warnings, failures)` 戻り値に拡張。「Progress 完了 AND Outcomes が TBD」を **failures** に分類し、`run_lifecycle_audit` の exit 1 を引き起こす。`ai-ops check` を CI で必須にしている本 repo では、Outcomes 未更新の PR が機械的に止まる。ADR 0010 §Lifecycle 4 で規約として書いた制約が、ようやく audit による技術的強制に昇格した。
3. **Pointer 追記** — AGENTS.md / README.md / README.ja.md の「operation.md は何が書いてあるか」の文に「5 strategies + responsibility matrix」を明記。エージェントがマスターガイドを開く動機が増える。

残課題: なし。本 plan は新ルールに従う第 1 例なので、Outcomes を完成させてから PR を出すという順序自体を dogfood している。

今後の plan へのフィードバック: 「契約 (規約 / 設定) は明文化と同時にツール / 設定で強制する」という Step 2 のフィードバックが、今回 audit 強化として実装に届いた。次は別の規約 — 例えば「commit は conventional commits 形式」「Branch / Worktree フィールドを冒頭に書く」など — も同様に audit 化する余地があるが、過剰な規約化はノイズになるので、実害が出たものから昇格する方針を維持する。

## Improvement Candidates

(作業中に追記)

## Context and Orientation

- AGENTS.md (109 行、Step 2 後): §Workspace、§Lifecycle and CLI、§Plans、§Cross-cutting CLI behavior、§Operation Model、§Safety、§Natural language、§Multi-agent、§Checks。Subcommands は削除済み。
- `docs/operation.md`: マスター運用ガイド。"目的別 sub-flow"、"Workflow tiers"、"Worktree"、"GitHub-native"、"plan 駆動"、"Improvement Capture"、"CLI クイックリファレンス" を持つが、Git / ghq / GitHub / Nix を横串で見る集約セクションは無い。
- ADR 群:
  - 0001 AGENTS.md primary
  - 0002 Portability first
  - 0003 Deletion policy
  - 0004 Secrets management
  - 0005 Nix optional reproducibility layer
  - 0006 AI-first project lifecycle
  - 0007 Python canonical CLI
  - 0008 Plan persistence
  - 0009 Git workflow tiers
  - 0010 Worktree workflow
  - 0011 GitHub-native ecosystem operation
- `ai_ops/audit/lifecycle.py` `_check_plan_hygiene`: 「Progress 完了 AND Outcomes が TBD」を検出するが warning として返す。`run_lifecycle_audit` 内で `warn += 1` を加算するだけで `fail` には加算しない。
- 既存テスト: `test_lifecycle_audit_warns_when_progress_complete_but_outcomes_tbd` は warning 期待。

## Plan of Work

1. **戦略集約セクション追加**: `docs/operation.md` の "目的別 sub-flow" の直後 (overview の文脈で読める位置) に "## 5 つの戦略 (Git / ghq / GitHub / Nix / plan)" を追加する。各戦略は 3-5 行 + 関連 ADR / CLI / 設定 を箇条書き。末尾に "### 責任分界 (自動 / 手動)" の表 1 つ。
2. **Phase 9 強化**: `_check_plan_hygiene` の return type は変えず、`run_lifecycle_audit` 側で「`Progress is complete but ... TBD`」を含む warning は fail にカウントする。または `_check_plan_hygiene` を `(warnings, failures)` を返す形に拡張し、Outcomes TBD は failures に振る。後者の方がクリーンなので採用。
3. **テスト更新**: 既存の WARN 期待テストを FAIL 期待に書き換え + 新規テスト追加 (Outcomes TBD で `run_lifecycle_audit` exit 1)。
4. **AGENTS.md / README pointer**: AGENTS.md §Lifecycle and CLI に「戦略全体は `docs/operation.md` の "5 つの戦略" を参照」の 1 行追加。README にも 1 行 (Quick start の下あたり)。
5. **検証**: `python -m ai_ops check` 全パス、新規 / 更新テスト pass。

## Concrete Steps

```sh
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops.strategies-consolidation

# 1. 検査強化 (実装 + 既存テスト書換 + 新規テスト)
$EDITOR ai_ops/audit/lifecycle.py
$EDITOR tests/test_audit.py
python -m pytest tests/test_audit.py -k "plan_hygiene or outcomes" -v

# 2. 戦略集約セクション追加
$EDITOR docs/operation.md

# 3. pointer 追加
$EDITOR AGENTS.md
$EDITOR README.md
$EDITOR README.ja.md

# 4. 検証
python -m ai_ops check

# 5. push + PR
git add -A
git commit -m "docs+audit: consolidate 5 strategies + enforce plan Outcomes via audit FAIL"
git push -u origin docs/strategies-consolidation
gh pr create --title "..." --body "..."

# 6. merge → archive → cleanup (ADR 0010 §Lifecycle 4 の手順)
gh pr merge <N> --squash
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops
git pull --ff-only && git fetch --prune origin && git ls-remote --heads origin
git mv docs/plans/strategies-consolidation docs/plans/archive/2026-05-03-strategies-consolidation
git commit -m "chore(plans): archive strategies-consolidation plan"
git push
python -m ai_ops worktree-cleanup --auto
```

## Validation and Acceptance

- `python -m ai_ops audit lifecycle` exit 0 (Outcomes 未更新の active plan が無いこと)。
- `python -m ai_ops check` exit 0、pytest 全パス。
- `docs/operation.md` に "5 つの戦略" + 責任分界表が存在。
- 既存テスト `test_lifecycle_audit_warns_when_progress_complete_but_outcomes_tbd` を「FAIL 期待」に書き換え済み。
- 新規回帰テスト: `_check_plan_hygiene` の Outcomes TBD が `run_lifecycle_audit` exit 1 を引き起こす。
- 本 plan の Outcomes & Retrospective を埋めた状態で PR を出す (= 本 plan 自身が新ルールに従う第 1 例)。

## Idempotence and Recovery

- audit 強化は git revert 可能。テスト書換も同様。
- 文書追加は破壊的でない。
- 本 PR 自身がマージ前に新ルールを満たさなければならない (Outcomes 完成必須) — 自己 dogfooding。

## Artifacts and Notes

- PR URL: TBD
- 本 PR のマージで「`audit lifecycle` の Outcomes FAIL 化が機能している」ことを実地検証する (CI pre-merge / post-merge)。

## Interfaces and Dependencies

- `ai_ops/audit/lifecycle.py`: `_check_plan_hygiene` の戻り値拡張または `run_lifecycle_audit` 側の分類強化。
- `tests/test_audit.py`: 既存テスト書換 + 新規テスト。
- `docs/operation.md`: 新セクション追加。
- AGENTS.md / README / README.ja.md: pointer 追加 (各 1-2 行)。
- ADR 群: 既存 ADR 0005 / 0008 / 0009 / 0010 / 0011 を本 plan は変更しない (集約 doc が ADR を参照する側)。
