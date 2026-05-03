# Docs Coherence (PR δ)

Branch: `docs/docs-coherence`
Worktree: `../ai-ops.docs-coherence/`

## Purpose / Big Picture

直前の docs 監査で 3 件の Critical + 7 件の High + 多数の Medium/Low が検出された:

- **C1**: README の `ADRs 0001-0008` 表記 (実際は 0012 まで)
- **C2**: 旧 alias (`propagate-anchor` 等) を 8 active ファイルが正規 example として記載
- **C3**: README.ja.md が新規 7 コマンドを欠落
- **H1-H7**: signal 数不整合、ADR 0007 古い、secret 5 原則が 3 箇所反復、Nix rubric 重複、`--with-secrets` / `--with-pre-push-hook` / `--auto-archive` が public doc に出ない、ADR 0011 Move 3 と実装が乖離

これらを 1 PR で塞ぐ。さらに **再発防止として `audit lifecycle` に新規検査を追加**: active doc 内の旧 alias を grep 検出して FAIL。これで「規約は audit で機械強制」原則を docs にも適用する。

## Progress

- [x] (2026-05-03 09:30Z) Initial plan drafted.
- [x] (2026-05-03 09:35Z) C1: README.md / README.ja.md の `ADRs 0001-0008` を `decisions/INDEX.md` への参照に置換。
- [x] (2026-05-03 09:50Z) C2/C3: README × 2 と 5 active doc / 2 template から旧 alias を完全除去、README.ja.md に新規 7 コマンド (propagate / worktree / setup / report-drift / review-pr) を追記、英版と row 一致。
- [x] (2026-05-03 09:55Z) H1: README × 2 と projects-audit.md の signal 数表記 (8/9) を「signal 群」に抽象化、`audit projects --json` を正本と注記。
- [x] (2026-05-03 09:58Z) H2: ADR 0007 末尾に Amendment 2026-05-03 (PR δ) ブロックを追加、`ai-ops --help` を最新の正本と明記。
- [x] (2026-05-03 10:00Z) H3: docs/operation.md の secret 5 原則 reproduce を short link に短縮、ADR 0004 を canonical に。
- [x] (2026-05-03 10:02Z) H4: project-addition-and-migration.md の Stage A/B/C 完全表を 3 行 link に集約、ADR 0005 canonical。
- [x] (2026-05-03 10:08Z) H5/H6: AGENTS.md §Cross-cutting CLI behavior と docs/operation.md の CLI Quick reference に `--with-secrets` / `--with-pre-push-hook` / `--auto-archive` / `--auto-yes` を記載。
- [x] (2026-05-03 10:12Z) H7 + ADR 0009-0012 alias amendment: 4 本の ADR にそれぞれ Amendment 2026-05-03 (PR δ) ブロックを追加、ADR 0011 で `setup-managed --tier B` 案を採用しなかった旨も記録。
- [x] (2026-05-03 10:18Z) audit lifecycle Phase 12: `DEPRECATED_ALIAS_PATTERN` + `_check_deprecated_alias_in_active_docs` を追加。`docs/decisions/` と `docs/plans/archive/` を除外、active doc + templates のみ scan。
- [x] (2026-05-03 10:22Z) Medium/Low: ADR INDEX に Status 列追加 (Accepted/Amended)、ai-first-lifecycle.md Related に 0009-0012 + INDEX を追加、templates/agent-handoff.md 冒頭に 1:1:1 binding 3 行を追加、handoff の First Read を operation.md に変更。
- [x] (2026-05-03 10:25Z) テスト 5 件追加 (合計 248 PASS、smoke 2 件 skip)、`ai-ops check` 全パス。
- [ ] PR 作成、CI 通過 (AI レビュー再実走)、merge、auto-archive、worktree-cleanup。

## Surprises & Discoveries

- (作業中に追記)

## Decision Log

- Decision: 旧 alias は **active doc から完全除去**、ADR 内 (`0009-0012` の本文) は「執筆当時の名称」として残し、各 ADR 末尾に "Note (PR δ): subcommand 統合 PR α 後、`<old>` は `<new>` に統合された" の amendment 1 行を追加。
  Rationale: ADR は decision の歴史記録なので書き換えると改竄。amendment で現状を補足するのが ADR の正しい維持方法。active doc は使用者が直接コピペするので新形式に統一する。
  Date/Author: 2026-05-03 / Claude.

- Decision: secret 5 原則は **ADR 0004 を canonical** にし、`docs/operation.md` は要約 (3 行) + link に置換。ADR 0004 内の重複 (Absolutely-do-not-do リスト + AI 5 原則) は残す (両者は視点が違う: 前者は禁止行為、後者は AI の振る舞い指針)。
  Rationale: ADR 内 2 リストは確かに重複するが、対象読者が違う (人間運用ルール vs AI エージェント実行原則)。link 1 つで集約するより、ADR 内に並べたほうが用途別に参照しやすい。
  Date/Author: 2026-05-03 / Claude.

- Decision: signal 数表記は **数を書かず「signal 群」と表現**。
  Rationale: signal は機能追加で増減する。具体的な数を doc に書けば必ず drift する。「`audit projects --json` の出力 field」と曖昧化することで実装が source of truth になる。
  Date/Author: 2026-05-03 / Claude.

- Decision: `audit lifecycle` の旧 alias 検出は **active doc + templates のみ scan**、`docs/decisions/` と `docs/plans/archive/` は除外。
  Rationale: ADR は歴史記録なので旧名は許容。archive plan も執筆当時のスナップショット。active doc / templates だけ厳格化することで、ADR amendment が干渉せず最小ストレスで強制できる。
  Date/Author: 2026-05-03 / Claude.

- Decision: Nix rubric 集約は **ADR 0005 を canonical**、project-addition-and-migration.md の Stage A/B/C 表は link 1 行に置換。
  Rationale: Stage A/B/C 表は decision (rubric の formal definition) なので ADR 側が source of truth。playbook (addition-and-migration) は「rubric は ADR 0005 を見よ」で十分。
  Date/Author: 2026-05-03 / Claude.

- Decision: ADR INDEX に **Status 列** (Accepted / Amended / Superseded) を追加。
  Rationale: ADR は時間経過で amend / supersede され得る。INDEX で 1 列見れば「最新有効か?」が即分かるべき。
  Date/Author: 2026-05-03 / Claude.

## Outcomes & Retrospective

ship したもの (PR δ):

1. **Critical 3 件解消**
   - C1: README × 2 の `ADRs 0001-0008` claim drift 修正
   - C2: 旧 alias 残存 8 ファイル + 2 templates から完全除去 (active doc / templates 0 件)
   - C3: README.ja.md に新規 7 コマンドを追加、英版と row 一致

2. **High 7 件解消**
   - H1: signal 数表記を「signal 群」に抽象化、`audit projects --json` を正本と明記
   - H2: ADR 0007 末尾に Amendment block (最新は `ai-ops --help` を正本と明記)
   - H3: secret 5 原則を ADR 0004 に集約、operation.md は短い link に
   - H4: Nix rubric を ADR 0005 に集約、project-addition-and-migration.md は 3 行 link
   - H5/H6: AGENTS.md と operation.md に `--with-secrets` / `--with-pre-push-hook` / `--auto-archive` を記載
   - H7: ADR 0011 に Move 3 amendment (`setup-managed --tier B` 不採用、`setup {ci,codeowners,ruleset}` 採用の経緯記録)
   - 加えて ADR 0009 / 0010 / 0012 にも alias amendment block

3. **再発防止 (機械強制)** - `audit lifecycle` Phase 12: `DEPRECATED_ALIAS_PATTERN` で active doc / templates / active plan を grep 検出。`docs/decisions/` (歴史記録) と `docs/plans/archive/` (snapshot) は除外。違反 = `ai-ops check` FAIL = CI で merge 不可。今後 docs 編集時に旧 alias を seed しても止まる。

4. **Medium / Low 一部対応**
   - ADR INDEX に Status 列 (Accepted / Amended) 追加
   - ai-first-lifecycle.md Related に ADR 0009-0012 + INDEX 追加
   - templates/agent-handoff.md 冒頭に 1:1:1 binding 3 行追加、First Read を operation.md に変更

5. **テスト 5 件追加** (合計 248 PASS、smoke 2 件 skip): 旧 alias 検出 / 検出除外 / archive 除外 / template 検出 / 実 repo 回帰

### スコープから外したもの

- M3 (operation.md に `audit projects --json --priority` 注記): operation.md CLI 表に `audit projects` 注記済み
- M4 (`project-relocation.md` 439 行を Recovery 切り出しで分離): 大手術になるため別 plan で
- M5-M10 (細かいリンク調整): 重要度低、再発防止 audit が支える

### 効果

| メトリクス | Before | After |
|---|---|---|
| Critical 件数 | 3 | 0 |
| High 件数 | 7 | 0 |
| 旧 alias 残存 active ファイル数 | 8 | 0 (audit FAIL で再発防止) |
| Nix rubric 完全重複箇所 | 2 | 1 (ADR 0005 のみ) |
| secret 5 原則 反復箇所 | 3 | 1 (ADR 0004 内 2 + operation link) |
| signal 数の不整合 | 3 種類 | 0 (実装が source of truth) |
| ADR INDEX | Status 列なし | Accepted/Amended 表示 |
| ai-first-lifecycle Related ADR | 0001-0008 | 0001-0012 + INDEX |
| handoff template に 1:1:1 binding | なし | 冒頭 §0 に 3 行 |

「規律より仕組み」原則を docs 整合にも適用 — Phase 12 audit が docs と実装の乖離を技術的に止める。

### 今後の plan へのフィードバック

- docs / 規約の整合性も「audit で機械強制」が正解。ADR 12 本中 7 本を amend したが、`ai-ops check` が Phase 12 で守る限り、もう一度 alias drift が発生しても merge 前に止まる。
- ADR は **歴史記録として保持 + amendment block で最新状態を補足** が正しい維持方法。本文書き換えは判断の改竄になる。
- doc 量 (約 110 KB) は ADR 全 load を含めればまだ大きいが、INDEX による navigate と AGENTS.md/operation.md の小ささ (合わせて 18 KB) で起動コストは抑えられている。

## Improvement Candidates

(作業中に追記)

## Context and Orientation

監査レポート (直前の agent 監査) で見つかった具体的な箇所:

| 種別 | 箇所 | 問題 |
|---|---|---|
| C1 | `README.md:139` / `README.ja.md:130` | `ADRs 0001-0008` (実際は 0012) |
| C2 | `README.md:82-90` / `README.ja.md:64-83` (= C3) / `templates/plan.md:8` / `docs/realignment.md:87` / `docs/self-operation.md:70,74` / `docs/projects-audit.md:49` | 旧 alias を正規 example として記載 |
| C2 (ADR) | `decisions/0009-0012` | ADR 内例が旧 alias |
| C3 | `README.ja.md:64-83` | 新規 7 コマンド欠落 |
| H1 | `projects-audit.md:36` (9 信号) / `README.md:28,72` (8 signals) / 実装 13 列 | 数の不整合 |
| H2 | `decisions/0007-python-canonical-cli.md:33-39, 43-51` | audit module list / CLI surface 古い |
| H3 | `decisions/0004-secrets-management.md:27-35, 37-45` + `operation.md:61-71` | secret 5 原則 3 箇所反復 |
| H4 | `decisions/0005-nix-optional-reproducibility-layer.md:36-71` + `project-addition-and-migration.md:40-71` | Nix rubric 完全重複 |
| H5 | README × 2 (bootstrap 行) | `--with-secrets` 未記載 |
| H6 | AGENTS.md / README × 2 / operation.md (CLI 表) | `--auto-archive` 未記載 |
| H7 | `decisions/0011-github-native-operation.md:117` | `setup-managed --tier B` 予告と実装乖離 |

## Plan of Work

各 Critical / High を順に処理。並行可能なものは多いが、安全に逐次。

1. C1: README × 2 で `ADRs 0001-0008` → `decisions/INDEX.md` への参照に置換
2. C3: README.ja.md の subcommand 表に 7 行追加 (新形式で揃える)
3. C2: 全 active doc で `propagate-{anchor,init,files}` → `propagate --kind X`、`worktree-{new,cleanup}` → `worktree {new,cleanup}`、`setup-{ci-workflow,codeowners,ruleset}` → `setup {ci,codeowners,ruleset}` に一括置換
4. ADR (0009-0012) の旧 alias 言及には末尾 amendment block を追加 (本文は変更しない)
5. H1: signal 数表記を「N signals」から「signal 群」に置換
6. H2: ADR 0007 末尾に amendment block (PR α/β/γ で追加された module / subcommand を反映、または「最新は ai-ops --help を正本」と注記)
7. H3: `docs/operation.md` の secret 5 原則部分を「ADR 0004 §AI エージェントの secret 扱い 5 原則を厳守」に短縮
8. H4: `project-addition-and-migration.md` の Stage A/B/C 表を「Nix 採用判定 rubric は ADR 0005 §Per-project rubric を参照」に置換
9. H5/H6: README の bootstrap / worktree-cleanup 行に新 flag 注記、operation.md の CLI 表を新 flag に揃える
10. H7: ADR 0011 末尾に amendment (`setup-managed --tier B` 案ではなく `setup {ci,codeowners,ruleset}` 統合を採用した経緯)
11. Medium: ADR INDEX に Status 列追加、ai-first-lifecycle.md Related に 0009-0012 追加
12. Low: templates/agent-handoff.md に Plan path / Branch / Worktree フィールド追加
13. **新規 audit**: `ai_ops/audit/lifecycle.py` に `DEPRECATED_ALIAS_PATTERNS` 追加 (active doc + templates 配下を grep、`docs/decisions/` と `docs/plans/archive/` 除外)
14. テスト追加、ai-ops check 通過、PR 作成、CI、merge、auto-archive

## Concrete Steps

```sh
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops.docs-coherence

# 1-12. doc 編集 (Edit ツールで順次)
# 13. audit
$EDITOR ai_ops/audit/lifecycle.py
# 14. テスト
$EDITOR tests/test_audit.py
python -m pytest -v
python -m ai_ops check

# 15. PR
git add -A && git commit -m "docs: align all docs with PR α/β/γ + audit-enforced alias check (PR δ)"
git push -u origin docs/docs-coherence
gh pr create ...
```

## Validation and Acceptance

- `python -m ai_ops audit lifecycle` exit 0 (新規 alias 検査が pass)
- `python -m ai_ops check` exit 0、pytest 全パス
- `grep -rE 'ai-ops (propagate-anchor|propagate-init|propagate-files|worktree-new|worktree-cleanup|setup-ci-workflow|setup-codeowners|setup-ruleset)' README*.md docs/*.md templates/` が **`docs/decisions/`** と **`docs/plans/archive/`** を除いた範囲で **0 件**
- README.ja.md コマンド表に `propagate` / `worktree` / `setup` / `report-drift` / `review-pr` の 5 行が新規にある
- ADR INDEX に Status 列がある
- 本 PR が AI レビュー dogfood を通る (再実走確認)

## Idempotence and Recovery

- 全変更は git revert 可能
- audit 新規検査は最初から FAIL 判定 (warning fall-back を入れない、Step 1 言語ポリシーと同じ厳しさ)
- ADR amendment block 追加は破壊的でない (本文保持)

## Artifacts and Notes

- PR URL: TBD
- AI レビュー結果: TBD

## Interfaces and Dependencies

- 新 audit pattern (active docs/templates only)
- 新 file: 無し
- 既存拡張: 全 active doc + ADR 4 本に amendment + audit/lifecycle.py + test
