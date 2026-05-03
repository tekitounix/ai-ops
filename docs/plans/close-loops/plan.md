# Close Loops (PR ε)

Branch: `fix/close-loops`
Worktree: `../ai-ops.close-loops/`

## Purpose / Big Picture

PR δ 後の self-improvement 監査で、**外側の loop が閉じていない 3 件の Critical** が発見された:

- **CR1**: `propagate-cron.yml` が `GITHUB_TOKEN` 制約で他 repo に PR を立てられず、`|| true` で全 step を握り潰し、しかも旧 alias (`propagate-anchor`) のまま。weekly cron が走り続けても誰も気付かない。
- **CR2**: ecosystem dashboard の parent issue が「manual setup」だが setup helper も docs も存在せず、永久に sub-issue が立たないまま。
- **CR3**: `review-pr` の cost monitor は PR Comment 末尾表示のみで cap / alert / 月次集計が無い。Sonnet→Opus 切替で 50× コスト増しても気付かない。

「機能はあるが loop が閉じていない」典型。本 PR で 3 ループすべてを閉じる。

加えて H4 (BW_SESSION lifecycle 明文化) と H7 (`recommended_tier` を docs/table に表示) を合わせて入れる。

## Progress

- [x] (2026-05-03 11:00Z) Initial plan drafted.
- [x] (2026-05-03 11:08Z) CR1+H1: propagate-cron を新 alias (`propagate --kind`) に書き換え、`AI_OPS_PROPAGATE_PAT` 要求を verify step として追加、`|| true` 全削除、Phase 12 scan に `.github/workflows/*.yml` を追加。
- [x] (2026-05-03 11:18Z) CR2: `setup ecosystem --project-name <name>` 実装。既存 parent issue があれば skip、`ecosystem` label 自動作成、`gh issue create` で parent issue を立てる。
- [x] (2026-05-03 11:30Z) CR3: `_read_monthly_budget_usd` (env var > harness.toml > None)、`_cost_cache_path`、`_read_monthly_total_usd`、`_append_cost_entry` を `review.py` に追加。`review_with_llm` で budget 超過なら API call せずに neutral skip + Comment に説明。`run_review_cost` で月次 / repo 別集計を table 出力、CLI に `review-cost --month` を追加。
- [x] (2026-05-03 11:35Z) H4: ADR 0004 §Amendment 2026-05-03 (PR ε): BW_SESSION lifecycle 5 step (発行 / history 抑止 / 範囲 / 終了 / 露出時) を明文化。
- [x] (2026-05-03 11:40Z) H7: `docs/projects-audit.md` の signal 表に `recommended_tier` 行を追加、`_print_table` の cols に `rec` 列を追加。
- [x] (2026-05-03 11:45Z) テスト 8 件追加 (workflow scan / budget cap / cache 記録 / harness.toml 読取 / env override / parent issue helper)、合計 254 件 PASS、smoke 2 件 skip。
- [x] (2026-05-03 11:48Z) `python -m ai_ops check` 全パス。
- [ ] PR 作成、CI 通過、merge、auto-archive、worktree-cleanup

## Surprises & Discoveries

- (作業中に追記)

## Decision Log

- Decision: PAT は `secrets.AI_OPS_PROPAGATE_PAT` 名で要求し、未設定なら job が exit 1。`|| true` を全削除。
  Rationale: silent fail を「明示 fail」に転換することで、初回 setup 時に「PAT が必要」と気付ける。`|| true` は debugging を困難にする anti-pattern。
  Date/Author: 2026-05-03 / Claude.

- Decision: ecosystem parent issue 作成は `setup ecosystem --project R --owner OWNER` という helper として実装、`gh issue create --label ecosystem --title "Ecosystem: <repo>"` を呼ぶ。auto-create はしない (使用者の判断で立てる)。
  Rationale: parent issue は「使用者がこの project を ecosystem dashboard に乗せたい」という宣言的行為。auto-create すると意図しない project まで dashboard に乗る。
  Date/Author: 2026-05-03 / Claude.

- Decision: cost cap は `harness.toml` の `[review_budget]` section で `monthly_usd_limit = 20` のように設定。default は cap 無し (既存挙動を壊さない)。
  Rationale: 各 project が独自の予算を持てる設計が自然。default cap を入れると既存挙動が変わって意図しない skip が発生。
  Date/Author: 2026-05-03 / Claude.

- Decision: cost 月次集計は新 subcommand `ai-ops audit cost-summary` ではなく `ai-ops review-cost` という直接的な名前で。`audit *` には集計系を増やさない (audit は drift / FAIL 系)。
  Rationale: cost 集計は drift 検査ではなく観察的レポート。意味論を分けた方が CLI が分かりやすい。
  Date/Author: 2026-05-03 / Claude.

- Decision: Phase 12 scan target に `.github/workflows/*.yml` を追加するが、`templates/artifacts/` 配下は既存 alias (例: ai-ops.yml で `setup ci` ではなく旧 setup-ci-workflow) を残しているケースもないので fully scan できる。
  Rationale: H1 (propagate-cron 旧 alias) を機械検出する目的。CR1 修正後は cron yaml も新 alias になるので scan 対象拡大は安全。
  Date/Author: 2026-05-03 / Claude.

## Outcomes & Retrospective

ship したもの (PR ε):

1. **CR1 + H1 解消 (propagate-cron loop)**: workflow を新 alias 化、`AI_OPS_PROPAGATE_PAT` 不在で exit 1 (silent fail 防止)、`|| true` 全削除、Phase 12 audit が `.github/workflows/` も scan するよう拡張。今後 alias drift も PAT 設定漏れも CI で気付ける。

2. **CR2 解消 (parent issue 永久未作成)**: `ai-ops setup ecosystem --project-name <name>` 新規 subcommand。Ecosystem dashboard の parent issue を自動作成 (label 込み)、既存があれば skip。これで `ecosystem-watch.yml` が WARN で終わるループを閉じる。

3. **CR3 解消 (cost monitoring loop)**: `harness.toml::[review_budget].monthly_usd_limit` または `AI_OPS_REVIEW_BUDGET_USD_MONTH` env var で月額 USD cap を設定。`review_with_llm` は budget 超過なら API call せず neutral skip + Comment に「budget exceeded」明記。`~/.cache/ai-ops/review-cost-YYYY-MM.json` に各 review entry を追記、`ai-ops review-cost --month YYYY-MM` で repo 別 / model 別の月次集計を出力。

4. **H4 解消 (BW_SESSION lifecycle)**: ADR 0004 amendment block で 5 step 規約を明文化。発行 → history 抑止 → 使用範囲限定 → unset + bw lock → 露出時の対応。

5. **H7 解消 (recommended_tier visibility)**: `docs/projects-audit.md` の signal 表に行追加、`audit projects` の table 出力に `rec` 列追加。JSON にしか無かった field が text 表示でも見えるようになり、利用率が上がる。

6. **テスト 8 件追加** (合計 254 件 PASS): workflow scan 1 + budget cap 4 + cache 記録 1 + parent issue helper 系。

### ループ閉鎖の効果

| Loop | Before (PR δ 後) | After (本 PR 後) |
|---|---|---|
| propagate-cron | GITHUB_TOKEN で他 repo に PR 出せず weekly silently fail | PAT 不在で exit 1 + 新 alias で動作する |
| ecosystem dashboard | parent issue 永久未作成 → sub-issue 永久に立たない | `setup ecosystem` 1 コマンドで dashboard 起動 |
| AI レビューコスト | PR Comment 末尾の表示のみ、上限なし、累積把握なし | budget cap + monthly cache + `review-cost` で完全可視化 |
| BW_SESSION 漏洩 | 暗黙の規律のみ | 5 step 明文化 + 5 原則 |
| Tier 推薦 | JSON にしか出ない silent feature | docs + table 表示で利用率向上 |

### 残課題 (Medium / Low、本 PR スコープ外)

- M1: AI レビュー request changes 時の override SOP
- M2: setup ci の Tier A 説明強化
- M3: モデル名期限切れ検知
- M4: `audit projects` rate limit 配慮
- M5: end-to-end test
- L1-L8: 細かい改善
- 次の self-improvement loop で取り組む候補。

### 今後の plan へのフィードバック

- 「機能はあるが loop が閉じていない」は監査で見つけにくい。今回 agent 監査が顕在化した形だが、定期的に self-improvement loop を回す価値がある。
- ループ閉鎖系の修正は CR (Critical) として優先度高。`silent fail` パターン (`|| true`、`return None on missing key`) は loop が閉じていない signal。
- 規律 + 仕組みの 2 段で守れたものが半数 (BW_SESSION のみ規律ベース)、残り Critical は仕組み側で塞いだ。

## Improvement Candidates

(作業中に追記)

## Context and Orientation

- `.github/workflows/propagate-cron.yml` の現状: GITHUB_TOKEN, `|| true`, 旧 alias 3 種
- `ai_ops/report.py:17-19, 268-273`: parent issue WARN-only design
- `ai_ops/review.py`: cost footer のみ (BUDGET 系コードなし)
- `ai_ops/audit/lifecycle.py:413-422`: Phase 12 scan target に `.github/workflows/` が無い
- `ai_ops/audit/projects.py:99,475-504`: `recommended_tier` field が JSON 出力にあるが table 表示なし、docs 説明なし
- `docs/decisions/0004-secrets-management.md`: BW_SESSION の取り扱い詳細なし

## Plan of Work

### 1. propagate-cron.yml 修正 + Phase 12 scan 拡張 (CR1 + H1)

```yaml
# .github/workflows/propagate-cron.yml の差分
- name: Verify PAT is set
  env:
    AI_OPS_PROPAGATE_PAT: ${{ secrets.AI_OPS_PROPAGATE_PAT }}
  run: |
    if [ -z "$AI_OPS_PROPAGATE_PAT" ]; then
      echo "::error::AI_OPS_PROPAGATE_PAT not set. propagate-cron requires a PAT with repo write to all managed projects." >&2
      exit 1
    fi
- name: Propagate (anchor / init / files)
  env:
    GH_TOKEN: ${{ secrets.AI_OPS_PROPAGATE_PAT }}
  run: |
    python -m ai_ops propagate --kind anchor --all --auto-yes
    python -m ai_ops propagate --kind init   --all --auto-yes
    python -m ai_ops propagate --kind files  --all --auto-yes
```

`|| true` 全削除 (silent fail 排除)。

`ai_ops/audit/lifecycle.py` の `_check_deprecated_alias_in_active_docs` の scan target に `.github/workflows/*.yml` を追加。

### 2. `setup ecosystem` helper (CR2)

`ai_ops/setup.py` に `run_setup_ecosystem(project: str, owner: str | None, dry_run: bool)`:
- `gh issue create --repo <ai-ops repo> --title "Ecosystem: <repo>" --label ecosystem,ai-ops`
- 既存 parent issue があれば skip
- 使用者承認後に実行 (Operation Model)

CLI: `ai-ops setup ecosystem --project <repo> [--ai-ops-repo OWNER/NAME]`

### 3. cost cap + monthly aggregation (CR3)

`ai_ops/review.py`:
- `harness.toml` の `[review_budget]` section から `monthly_usd_limit` を読む
- 月次累計を `~/.cache/ai-ops/review-cost-YYYY-MM.json` に追記 (project + cost + tokens + timestamp)
- 累計が cap を超えたら `state="neutral"` で skip + Comment に「budget exceeded」明記
- env var override も用意 (`AI_OPS_REVIEW_BUDGET_USD_MONTH=20`)

`ai_ops/cli.py` に新 subcommand `review-cost`:
- `~/.cache/ai-ops/review-cost-YYYY-MM.json` から月次集計
- table 出力 (project / count / total_tokens / total_cost)
- `--month YYYY-MM` で月指定可

### 4. ADR 0004 BW_SESSION amendment (H4)

ADR 0004 の Amendment block に BW_SESSION lifecycle 規約を追加:
- `bw unlock --raw` の出力は **shell 変数のみで保持**、コマンド引数 / commit / log に書かない
- 用途終了後は `unset BW_SESSION && bw lock`
- shell history 抑止のため、`HISTCONTROL=ignorespace` を設定し `export` の前に space prefix
- 複数 shell session 間で session token を共有しない (各 session で発行)
- `bootstrap --with-secrets` 完了時に「session を破棄してください」リマインダーを stderr に出す

### 5. recommended_tier 表示 (H7)

`docs/projects-audit.md` の signal 表に 1 行追加:
```
| `recommended_tier` | `A` / `B` / `C` / `D` / null — 宣言なし (default D) の管理対象に対する推薦 tier (P2 観察、priority に乗らない) |
```

`ai_ops/audit/projects.py` の table 表示 (`_print_table` 系) で recommended_tier 列を追加。

### 6. テスト追加

- `tests/test_setup.py` に `test_setup_ecosystem_creates_parent_issue_when_missing` / `test_setup_ecosystem_skips_when_present`
- `tests/test_review.py` に `test_review_skipped_when_budget_exceeded` / `test_review_records_cost_to_cache`
- `tests/test_cli.py` に `test_audit_lifecycle_alias_check_scans_workflows` / `test_review_cost_subcommand_works`
- `tests/test_audit.py` に `recommended_tier` 表示の assertion 追加

## Concrete Steps

```sh
# 1. workflow + audit
$EDITOR .github/workflows/propagate-cron.yml
$EDITOR ai_ops/audit/lifecycle.py

# 2. setup ecosystem
$EDITOR ai_ops/setup.py ai_ops/cli.py

# 3. cost cap + cli
$EDITOR ai_ops/review.py ai_ops/cli.py

# 4. ADR 0004 amend
$EDITOR docs/decisions/0004-secrets-management.md

# 5. docs + table
$EDITOR docs/projects-audit.md ai_ops/audit/projects.py

# 6. test
$EDITOR tests/...
python -m pytest -v
python -m ai_ops check

# 7. PR
git add -A && git commit -m "fix: close 3 critical loops + tighten secret lifecycle (PR ε)"
git push -u origin fix/close-loops
gh pr create ...
```

## Validation and Acceptance

- `python -m ai_ops audit lifecycle` exit 0、Phase 12 が `.github/workflows/` も scan
- `propagate-cron.yml` が新 alias、PAT 要求、`|| true` 削除済み
- `setup ecosystem --help` が動く、parent issue 作成 (dry-run で検証)
- `review-cost --help` が動く、月次集計が出る
- `harness.toml::[review_budget].monthly_usd_limit = 0.001` を入れて `review-pr` が即 budget exceeded で neutral skip する
- ADR 0004 に BW_SESSION lifecycle amendment block がある
- `audit projects` の table に recommended_tier 列がある
- 本 PR の AI レビューが pass

## Idempotence and Recovery

- すべて git revert 可能
- cost cache は `~/.cache/ai-ops/` に置くので user は安全に削除可能
- parent issue auto-create は dry-run と確認 prompt 完備

## Artifacts and Notes

- PR URL: TBD

## Interfaces and Dependencies

- 新 subcommand: `setup ecosystem`、`review-cost`
- 新 secret: `AI_OPS_PROPAGATE_PAT` (各 ai-ops 利用者が設定)
- 新 config: `harness.toml::[review_budget]`
- 新 cache file: `~/.cache/ai-ops/review-cost-YYYY-MM.json`
