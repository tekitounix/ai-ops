# Backlog 導入 (PR θ)

Branch: `chore/backlog`
Worktree: `../ai-ops.backlog/`

## Purpose / Big Picture

現状、deferred 候補の行き場が無い:
- 各 plan の `Improvement Candidates` の `deferred` は plan archive 後に忘れ去られる
- 「次以降の PR で対応する」とだけ書かれた残課題が active plan を膨張させる
- 順序最適化 (今やめて後でやる) の退避先が無く、deletion か archive の二択

`docs/plans/backlog.md` を 1 ファイル作り、deferred / Cancelled の集約場所にする。新 plan 起草時の候補 pool としても機能。

## Progress

- [x] (2026-05-03 13:30Z) Initial plan drafted.
- [x] (2026-05-03 13:35Z) `docs/plans/backlog.md` 作成 (運用ルール 4 項目 + High 3 / Medium 5 / Low 5 / Cancelled 2 件)。過去 plan ε / ζ / η + docs 監査の deferred を吸い上げ。
- [x] (2026-05-03 13:38Z) ADR 0008 末尾に Amendment 2026-05-03 (PR θ): Backlog の Context / Decision / 構造 / 遷移 / 運用ルール 4 項目 / Enforcement。
- [x] (2026-05-03 13:40Z) `docs/operation.md` に "## Backlog (PR θ)" section 追記 (1 段落 + ADR link)。
- [x] (2026-05-03 13:42Z) `templates/plan.md` Improvement Candidates Enum reference に「`deferred` 判定時は backlog.md への転記必須」明記。
- [x] (2026-05-03 13:43Z) `ai_ops/audit/lifecycle.py` REQUIRED_FILES に `docs/plans/backlog.md` 追加。
- [x] (2026-05-03 13:44Z) tests/test_audit.py に assertion 追加 (合計 266 PASS、smoke 2 件 skip)。
- [x] (2026-05-03 13:45Z) `ai-ops check` 全パス。
- [ ] PR 作成、CI 通過、merge、auto-archive。

## Surprises & Discoveries

- (作業中に追記)

## Decision Log

- Decision: ファイル名は `docs/plans/backlog.md` (plans/ 配下、archive/ と同階層)。
  Rationale: plan family の一員として位置付け、`docs/backlog.md` のように plans/ 外に置くと「plan と独立した何か」と誤解される。
  Date/Author: 2026-05-03 / Claude.

- Decision: 4 段階 (High / Medium / Low / Cancelled) で priority 区分。
  Rationale: 3 段階 (High/Medium/Low) だと「却下したが履歴を残したい」が無くなる。Cancelled section に reason 付きで残せば、再度同じ candidate が上がった時に判断材料になる。
  Date/Author: 2026-05-03 / Claude.

- Decision: backlog item は出所 (どの plan / 監査 / 議論で出てきたか) を必ず明記。
  Rationale: 出所が分かれば、再評価時に「なぜ deferred したか」を追跡できる。出所無しの item は「孤児」として整理対象になる。
  Date/Author: 2026-05-03 / Claude.

- Decision: 「3 plan 連続で deferred のまま放置」を再評価のトリガーとする (定量基準)。
  Rationale: ADR 0008 の Improvement Capture loop で同様の閾値を採用済み (Decision Log 内記述)。一貫性のため踏襲。
  Date/Author: 2026-05-03 / Claude.

## Outcomes & Retrospective

ship したもの (PR θ):

1. **`docs/plans/backlog.md`** 新規 — High 3 / Medium 5 / Low 5 / Cancelled 2 件の初期 entry。過去 PR ε / ζ / η + docs 監査の deferred を吸い上げ。
2. **ADR 0008 amendment** — Context / Decision / 構造 / 遷移図 / 運用ルール 4 項目 / Enforcement を末尾に追加。
3. **`docs/operation.md`** — "## Backlog (PR θ)" section を「ワークフロー tier」と「マージ後の手順」の間に追加 (1 段落)。
4. **`templates/plan.md`** — Improvement Candidates Enum reference に「`deferred` 判定時は backlog.md への転記必須」明記。
5. **audit lifecycle** REQUIRED_FILES に `docs/plans/backlog.md` 追加 + test 1 件。

### 効果

| 観点 | Before | After |
|---|---|---|
| deferred 候補の行き場 | 各 plan に閉じ、archive 後に忘れ去られる | `backlog.md` 1 ファイルに集約 |
| 「次 PR で対応」記述 | active plan を膨張させる | backlog.md に転記、active は今やることだけ |
| 順序最適化の退避先 | deletion か archive (二択) | backlog.md High/Medium/Low/Cancelled に move |
| 新 plan の起草 | ゼロから候補考案 | backlog から pick |

### 実例

本 PR 自身の Improvement Candidates は「(none this pass)」だが、もし将来「backlog.md に hygiene check を追加すべき」のような deferred が出たら、PR 完了前に backlog.md の Medium に追記してから archive する流れになる。

### 残課題

- backlog.md の hygiene check (Cancelled section が空、出所未記載 等の機械検査) は本 PR では未実装。実害が出てから追加する (over-engineering 回避)。
- 過去 archive plan の「今後の plan へのフィードバック」section も backlog 候補だが、本 PR では「残課題」section のみ吸い上げた。フィードバックは ADR / docs 改訂で吸収済みのものが多い。

### 今後の plan へのフィードバック

- backlog 導入で「考えたけど今回はやらない」を明示的に残せるようになった。新 plan 起草時に「ゼロから考える」のではなく「backlog を見て pick」の流れができれば、判断の連続性が保てる。
- 4 段階 (High/Medium/Low/Cancelled) は現状の規模に妥当。100 entry 超えたら priority 内 sub-grouping を検討する。
- Cancelled section は「なぜやらなかったか」の institutional memory。同じアイデアが再浮上したとき、過去の判断を踏まえた議論ができる。

## Improvement Candidates

(作業中に追記)

## Context and Orientation

過去 plan の `### 残課題` セクションを集約 (PR ε / ζ / η 由来 + docs 監査):

**PR ε close-loops**:
- M1: AI レビュー request changes 時の override SOP
- M2: setup ci の Tier A 説明強化
- M3: モデル名期限切れ検知
- M4: `audit projects` rate limit 配慮
- M5: end-to-end test

**PR ζ selective-review**:
- model 選定 heuristic を diff content / 規模ベースに拡張
- `audit security` で `[review]` schema 整合性 (例: `monthly_usd_limit < per_pr_usd_limit` 矛盾) チェック

**PR η e2e-fixes**:
- workflow 関連変更で E2E pass 必須化の仕組み

**docs 監査 (PR δ 前) で deferred (PR δ で吸わなかったもの)**:
- `project-relocation.md` 439 行を Recovery 切り出しで分離
- `direnv exec . sh -c '...'` 重複の helper 化

## Plan of Work

### A. `docs/plans/backlog.md` 新規作成

High / Medium / Low / Cancelled の 4 section + 運用ルール 4 項目を含む 1 ファイル。

### B. ADR 0008 amendment

`docs/decisions/0008-plan-persistence.md` 末尾に Amendment 2026-05-03 (PR θ): backlog.md の位置付け、active ↔ backlog ↔ archive の遷移、3-deferred 閾値。

### C. `docs/operation.md` plan section 追記

backlog の存在と運用 1 段落 (Active が膨張したら退避、新 plan は backlog から pick)。

### D. `templates/plan.md` Improvement Candidates Enum

「`deferred` (理由 + backlog.md への転記必須)」と明記。

### E. `audit lifecycle` REQUIRED_FILES に追加

`docs/plans/backlog.md` を REQUIRED_FILES に追加。簡易 hygiene check は本 PR では実装しない (over-engineering 回避)。

### F. テスト

`tests/test_audit.py` に `assert "docs/plans/backlog.md" in REQUIRED_FILES` 1 件。

## Concrete Steps

```sh
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops.backlog
$EDITOR docs/plans/backlog.md  # 新規
$EDITOR docs/decisions/0008-plan-persistence.md  # amendment
$EDITOR docs/operation.md
$EDITOR templates/plan.md
$EDITOR ai_ops/audit/lifecycle.py
$EDITOR tests/test_audit.py
python -m ai_ops check
git add -A && git commit -m "chore(plans): introduce backlog.md (PR θ)"
git push -u origin chore/backlog
gh pr create
```

## Validation and Acceptance

- `docs/plans/backlog.md` が存在し、4 section + 運用ルールを含む
- `audit lifecycle` REQUIRED_FILES に `docs/plans/backlog.md` がある
- ADR 0008 に Amendment block がある
- `docs/operation.md` plan section に backlog 言及がある
- `templates/plan.md` Improvement Candidates Enum に backlog 転記指示がある
- `python -m ai_ops check` 全パス、pytest +1 件

## Idempotence and Recovery

- 全変更は git revert 可能
- backlog.md は人間が読む docs、機械検査は最低限 (ファイル存在のみ)

## Artifacts and Notes

- PR URL: TBD

## Interfaces and Dependencies

- 新規 file: `docs/plans/backlog.md`
- 既存拡張: ADR 0008、operation.md、templates/plan.md、audit/lifecycle.py、test_audit.py
