# docs consolidation: master operation doc + cleanup

ai-ops のドキュメント体系を user / agent から見て「どこから読めばよいか」が明確な一本の master operation doc を中心に再編する。既存のドキュメントは deep-dive として残し、master からリンクで navigate できる状態にする。README は entry 役に絞る。

Plan path: `docs/plans/docs-consolidation/plan.md`。
Branch: `docs/docs-consolidation`。
Worktree: `../ai-ops.docs-consolidation/`。

## Purpose / Big Picture

現状: **「ai-ops のプロジェクト運用ってどうやるの?」と聞かれたとき、3 ADR + 6 operational doc + README + AGENTS.md を読み回らないと全体像が掴めない**。新規 user(または agent)の incumbent cost が高い。

目的: 単一の `docs/operation.md`(master operation guide)を新設し、ライフサイクル / Tier / worktree / propagation / GitHub-native ecosystem / improvement loop / sub-flow 選択 / Quick reference を網羅する。既存の operational doc(`ai-first-lifecycle.md` 等)は deep-dive として保持、master から各 doc に link する hub-and-spoke 構造にする。

完了後の到達点:
- `docs/operation.md` を読めば「ai-ops でプロジェクトを運用する全体像」が分かる
- 既存 doc は深掘り情報として retained、重複排除
- README は (a) Quick start prompts, (b) operation guide pointer, (c) install, (d) CLI reference にフォーカス
- AGENTS.md は cross-cutting policy と subcommand authoritative reference に絞る
- README.ja.md は同期更新

## Progress

- [x] (2026-05-02 18:30Z) 現状 docs inventory 完了。worktree-new docs-consolidation で隔離環境作成。本プラン作成。
- [ ] `docs/operation.md` を新規作成(master entry point)
- [ ] `README.md` を update(operation guide pointer + 1 段落 overview を冒頭追加)
- [ ] `README.ja.md` を同期更新
- [ ] 既存 operational doc 6 個の冒頭に「これは master の deep-dive」note 1 行追加
- [ ] 全 cross-reference の正当性を確認
- [ ] local check + commit + push + PR
- [ ] PR merge + plan archive + worktree-cleanup

## Surprises & Discoveries

- Observation: 既存 operational doc 6 個は実際には scope 別に明確に分かれており、内容の重複は少ない。問題は overlap ではなく **entry point の不在**。
  Evidence: ai-first-lifecycle (新規/migrate)、project-addition-and-migration (判断基準)、realignment (drift 矯正)、self-operation (ai-ops 自己運用)、projects-audit (multi-project 監査)、project-relocation (物理移行) — 各 scope は重ならない。
  Implication: 既存 doc を統合して 1 つにする必要は無い。master doc は **navigator** として機能させ、各 deep-dive は今のまま keep する。

- Observation: `project-relocation.md` が 440 行と異常に長い。物理移行の詳細手順 + recovery + edge case が網羅されている。
  Evidence: `wc -l docs/project-relocation.md` = 440。他 doc は 94〜165 行。
  Implication: relocation は他より頻度が低く、深い内容。master からの位置付けは「特殊 sub-flow」として軽く言及、詳細は relocation doc 参照とする。

- Observation: ADR 0009/0010/0011 は recently 追加された設計だが、operational doc には部分的にしか統合されていない(realignment.md は worktree-new 1 行、self-operation.md は worktree section、projects-audit.md は signal 解説のみ)。GitHub-native operation 全体(ecosystem dashboard、setup-* helper、reusable workflow)は どこにも narrative として書かれていない。
  Evidence: 各 doc の grep。
  Implication: master doc が ADR 0009/0010/0011 の narrative integration を担う。

- Observation: README は CLI reference table が支配的で、「どんな運用なのか」の説明はほぼ無い。
  Evidence: README.md 行 60-85 が CLI 表、それ以外は install / configuration / verification。
  Implication: README から CLI 表は減らさない(hand reference として価値あり)が、上部に "How to operate" sectional pointer を追加する。

## Decision Log

- Decision: master doc は `docs/operation.md` という名前で新規作成する。
  Rationale: ai-ops の中核は「project operation」全般であって git だけではない。`operation.md` がスコープを正確に表す。`workflow.md` は git 専用と誤解されかねないので避ける。
  Date/Author: 2026-05-02 / Codex

- Decision: 既存 operational doc 6 個は **delete / merge しない**。master からの deep-dive として keep する。各 doc 冒頭に「これは master の deep-dive」セクションを 1 行追加。
  Rationale: 既存 doc は scope 別に分かれており、各 scope の詳細は分量があって master に inline できない。hub-and-spoke モデルが妥当。
  Date/Author: 2026-05-02 / Codex

- Decision: README.md に「How does ai-ops work?」セクションを冒頭付近に追加し、`docs/operation.md` への pointer + 1 段落の overview を載せる。CLI 表は keep。
  Rationale: README は最初の入り口、user が「どう運用するの?」を最短で見つけられる導線が要る。
  Date/Author: 2026-05-02 / Codex

- Decision: AGENTS.md の subcommand 一覧は authoritative reference として keep。master doc からは「コマンド詳細は AGENTS.md / README CLI 表参照」と link する。重複しない。
  Rationale: AGENTS.md は agent contract として load される文書、subcommand 一覧を削除すると agent が CLI を発見できなくなる。
  Date/Author: 2026-05-02 / Codex

- Decision: master operation doc は **英語で書く**。日本語版 (`docs/operation.ja.md`) は将来 sibling として要望が出た時点で追加。
  Rationale: README が英語 default なので、その延長として entry doc も英語で揃える。owner は日本語話者だが英語の technical doc は問題なく読める。日本語版要望は ja sibling で後追い可能。
  Date/Author: 2026-05-02 / Codex

- Decision: 本プラン自体を ADR 0010 dogfood として worktree-new で実施。完了時に worktree-cleanup で自動削除。
  Rationale: 直前まで自分で作った workflow を真っ先に follow する。
  Date/Author: 2026-05-02 / Codex

## Outcomes & Retrospective

TBD。

## Improvement Candidates

### `docs/operation.ja.md` 翻訳版

- Observation: 現状 master doc は英語のみ。日本語話者の user は内容把握に翻訳負担。
- Evidence: 本 plan Decision Log。
- Recommended adoption target: `deferred`
- Confirmation needed: no — sibling 翻訳の追加は単純。
- Verification: 実 use で「英語が読みづらい」というシグナルが出たら translate。
- Disposition: deferred。

### docs/decisions/INDEX.md (ADR index)

- Observation: ADR 11 個になり、何がどこに書いてあるか索引が欲しい。
- Evidence: 11 個の ADR が flat list。
- Recommended adoption target: `deferred`
- Confirmation needed: no — index の追加は機械的作業。
- Verification: ADR が 15 個を超えるか、user が「ADR どこ?」と聞くようになったら作る。
- Disposition: deferred — 現状ファイル名で navigate 可能。

### CONTRIBUTING.md の追加

- Observation: 外部 contributor が ai-ops に PR を出すときの guidance が無い。
- Evidence: 現状 CONTRIBUTING.md ファイル無し。
- Recommended adoption target: `deferred`
- Confirmation needed: no — solo dev では不要、external contribution が増えたら必要。
- Verification: 外部 contributor が現れたら作る。
- Disposition: deferred。

## Context and Orientation

現状のドキュメント体系:

- **Root**: `README.md` (英語、entry)、`README.ja.md` (日本語 sibling)、`AGENTS.md` (cross-agent contract)、`CLAUDE.md` (loads AGENTS.md)
- **`docs/`**: 6 operational doc(各 scope 別、重複なし)
- **`docs/decisions/`**: 11 ADR
- **`templates/`**: brief / plan / handoff / artifacts

新設するもの:
- `docs/operation.md` — master operation guide (英語、ADR 0009/0010/0011 を narrative に統合、6 operational doc への hub)

更新するもの:
- `README.md` — operation guide pointer + 1 段落 overview を冒頭追加
- `README.ja.md` — 同期翻訳
- 既存 6 operational doc — 冒頭に master pointer 1 行追加

## Plan of Work

1. `docs/operation.md` を draft する。構成:
   1. Overview (one paragraph)
   2. The Lifecycle: Intake → Discovery → Brief → Confirm → Execute → Verify → Adopt (link to ai-first-lifecycle.md)
   3. Sub-flows by intent (table: 何をしたいか → どの sub-flow を使うか)
   4. Workflow tiers (ADR 0009 narrative summary + link)
   5. Worktree-based parallel work (ADR 0010 narrative + link)
   6. GitHub-native ecosystem operation (ADR 0011 narrative + link)
   7. Plan-driven execution (ADR 0008 narrative + link)
   8. Improvement Capture loop (link)
   9. Quick CLI reference grouped by intent (link to AGENTS.md / README for full)
   10. Where to read next (links to ADRs by topic)

2. README.md を update。冒頭付近に "How does ai-ops work?" 追加、`docs/operation.md` link。

3. README.ja.md を同期更新。

4. 既存 operational doc 6 個の冒頭に 1 行追記:
   `> Master operation guide: [docs/operation.md](operation.md). This document is the deep-dive on <scope>.`

5. AGENTS.md は変更不要(authoritative reference として現状維持)。

6. local check + commit + push + PR + merge + cleanup。

## Concrete Steps

```sh
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops.docs-consolidation
# 実装後
python -m ai_ops check
git diff --check
git push -u origin docs/docs-consolidation
gh pr create --title "docs: master operation guide + doc consolidation"
gh pr checks --watch
gh pr merge --squash --delete-branch
# main 戻り + cleanup
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops
git pull origin main
git mv docs/plans/docs-consolidation docs/plans/archive/2026-05-02-docs-consolidation
git commit + push
python -m ai_ops worktree-cleanup --auto
```

## Validation and Acceptance

### Machine-checkable

- `docs/operation.md` が存在する
- README.md に "How does ai-ops work?" 相当のセクションが存在
- README.ja.md にも同一構造の section
- 既存 operational doc 6 個に master pointer 1 行
- `python -m ai_ops check` PASS、CI 全ジョブ green

### Human-reviewable

- master doc を読めば、「ai-ops の運用とは何か / どの sub-flow を使うべきか / どの ADR を読むべきか」が理解できる
- 既存 doc が master から 1 click で navigate 可能
- README から master へ最短 1 click

## Out of Scope

- 既存 operational doc の内容書き直し(navigation 1 行のみ追記)
- 新規 ADR 作成
- `docs/operation.ja.md` 翻訳版(deferred)
- ADR INDEX(deferred)
- CONTRIBUTING.md(deferred)
- AGENTS.md の構造変更
- templates/ の変更
- 既存 ADR の rewrite

## Idempotence and Recovery

- 全変更は doc edit のみ、Git diff review で reversible
- master doc 新規追加 / README 編集 / 既存 doc 1 行追記 — どれも独立して revert 可能
- worktree 隔離で main に影響なし

## Artifacts and Notes

(進行中) — PR URL、merge SHA、観察事項を記録。

## Interfaces and Dependencies

- 新規ファイル `docs/operation.md`
- 既存ファイル変更: `README.md`、`README.ja.md`、6 operational doc(冒頭 1 行のみ)
- AGENTS.md / CLAUDE.md: 変更なし
- 既存 ADR: 変更なし
- 既存 templates: 変更なし
