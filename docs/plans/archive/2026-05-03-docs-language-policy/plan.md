# Docs Language Policy

Branch: `fix/docs-language-policy`
Worktree: `../ai-ops.docs-language-policy/`

## Purpose / Big Picture

AGENTS.md §Natural language は「`docs/` 配下は日本語デフォルト」と宣言しているが、実態として 7 ファイル中 3 ファイル (`docs/operation.md`, `docs/projects-audit.md`, `docs/project-relocation.md`) が完全英語で違反している。これは「ポリシーは書いてあるが検査が無い」という構造的欠陥が原因。

本 plan は次の 2 層で根治する。

1. 違反 3 ファイルを日本語化する。
2. `ai-ops audit lifecycle` に「`docs/` 配下の `.md` の日本語文字比率を測り、閾値未満なら FAIL する」検査を追加する。`README.md` と `docs/decisions/` (ADR 慣行で英語) は除外。

完了後、`python -m ai_ops audit lifecycle` で言語ポリシー違反を検出できるようになり、書き手 (AI / 人) の規律に頼らずに守れる状態にする。

## Progress

- [x] (2026-05-03 01:50Z) Initial plan drafted.
- [x] (2026-05-03 02:00Z) audit lifecycle に日本語比率チェックを実装 + 5 テスト追加。
- [x] (2026-05-03 02:05Z) 違反 3 ファイル (operation.md / projects-audit.md / project-relocation.md) を日本語化。
- [x] (2026-05-03 02:08Z) `ai-ops check` 全 51 件 PASS、pytest 59 件 PASS 確認。
- [ ] PR 作成、CI 通過、merge、archive、worktree-cleanup。

## Surprises & Discoveries

- Observation: TBD (作業中に追記)。

## Decision Log

- Decision: 閾値は 0.10 (10%) とする。
  Rationale: 計測した健全 4 ファイル (`ai-first-lifecycle.md` 等) は 0.36-0.51。コードブロックや英語固有名詞が多くても 10% 未満になる文書はほぼ純英語。`docs/decisions/` 内の ADR (英語慣行) は対象外なので、誤検知のリスクは低い。
  Date/Author: 2026-05-03 / Claude.

- Decision: `docs/decisions/` と `README.md` は除外。
  Rationale: README は AGENTS.md ポリシーで「英語デフォルト」例外。ADR は load-bearing technical decision で、業界慣行として英語で記述される。
  Date/Author: 2026-05-03 / Claude.

- Decision: 違反検出時は FAIL (WARN ではない)。
  Rationale: ポリシーは「default」であって任意ではない。例外を許す場合は、その旨を AGENTS.md に明示的に追記すべきであり、audit が通ってしまう WARN では実効性が無い。
  Date/Author: 2026-05-03 / Claude.

## Outcomes & Retrospective

ship したもの:

1. `ai_ops/audit/lifecycle.py` に Phase 11 (`_check_docs_language_policy` / `_japanese_char_ratio`) を追加。閾値 0.10 未満を FAIL として `run_lifecycle_audit` に統合。`README*` プレフィックスと `docs/decisions/` / `docs/plans/` のサブディレクトリを除外。
2. `tests/test_audit.py` に 5 テスト追加: pass / fail / README 除外 / サブディレクトリ除外 / ai-ops 自身の docs/ 回帰。
3. `docs/operation.md`、`docs/projects-audit.md`、`docs/project-relocation.md` を日本語化。コードブロック、CLI コマンド、ファイル path、固有名詞、テストが期待するアンカー (`Phase 1`、`ANTI-PATTERN`、`INVARIANT:` 等) は英語のまま保持。

残課題: なし。閾値 (0.10) は経験則。誤検知が出たら `DOCS_LANGUAGE_RATIO_THRESHOLD` を調整する。

今後の plan へのフィードバック: 「ポリシー宣言は監査の自動検証と必ずペアにする」。docs/operation.md は私自身が直前の plan で作りながら、AGENTS.md ポリシー違反のまま merge した。書き手の規律に頼る宣言は、いずれ静かに破綻する。

## Improvement Candidates

完了前に triage して durable 化する。

### (作業中に追記)

## Context and Orientation

- AGENTS.md §Natural language: `AGENTS.md`, docs, issues, PRs, briefs, plans は日本語デフォルト。`README.md` のみ英語デフォルト (公開エントリポイント)。
- `ai_ops/audit/lifecycle.py`: 既存の self-audit 実装。`REQUIRED_FILES` で必須ファイル存在を確認し、Phase 8-D で禁止パターン grep を行う。
- 実測 (本 plan 作成時点):

| ファイル | 日本語文字比率 | 状態 |
|---|---|---|
| `docs/operation.md` | 0% | 違反 |
| `docs/projects-audit.md` | 0% | 違反 |
| `docs/project-relocation.md` | 0% | 違反 |
| `docs/ai-first-lifecycle.md` | 51% | OK |
| `docs/realignment.md` | 48% | OK |
| `docs/self-operation.md` | 39% | OK |
| `docs/project-addition-and-migration.md` | 36% | OK |

## Plan of Work

1. `ai_ops/audit/lifecycle.py` に新 Phase (例: Phase 10) を追加。`docs/**.md` を walk し、`README*` と `docs/decisions/**` を除外し、各ファイルの「ひらがな + カタカナ + 漢字」文字数 / 総文字数 を計算。閾値 0.10 未満なら FAIL を返す。
2. 対応する pytest を `tests/audit/test_lifecycle.py` (or 新規 `test_lifecycle_language.py`) に追加: 日本語ファイルが pass、英語ファイルが fail することを確認。
3. `docs/operation.md` を日本語化。コードブロック、CLI コマンド、ファイルパス、固有名詞 (Renovate 等) は英語のまま。
4. `docs/projects-audit.md` を日本語化。
5. `docs/project-relocation.md` を日本語化。
6. `python -m ai_ops audit lifecycle` で全 pass、`python -m ai_ops check` で全 pass を確認。
7. commit、push、PR 作成、CI 通過、merge (`gh pr merge --squash --delete-branch`)。
8. main に戻って archive (`git mv docs/plans/docs-language-policy docs/plans/archive/2026-05-03-docs-language-policy`)、push。
9. `python -m ai_ops worktree-cleanup --auto` で worktree 削除。

## Concrete Steps

```sh
# (worktree 内で作業)
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops.docs-language-policy

# 1-2. 検査追加 + テスト
$EDITOR ai_ops/audit/lifecycle.py
$EDITOR tests/audit/test_lifecycle.py
python -m pytest tests/audit/test_lifecycle.py -x

# 3-5. 違反ファイル日本語化
$EDITOR docs/operation.md
$EDITOR docs/projects-audit.md
$EDITOR docs/project-relocation.md

# 6. check 通過
python -m ai_ops check

# 7. push + PR
git add -A
git commit -m "fix(docs): enforce Japanese-by-default policy + translate 3 violating docs"
git push -u origin fix/docs-language-policy
gh pr create --title "fix(docs): enforce Japanese-by-default + translate violating docs" --body "..."

# 8-9. merge 後
gh pr merge --squash --delete-branch
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops
git pull
git mv docs/plans/docs-language-policy docs/plans/archive/2026-05-03-docs-language-policy
git commit -m "chore(plans): archive docs-language-policy plan"
git push
python -m ai_ops worktree-cleanup --auto
```

## Validation and Acceptance

- `python -m ai_ops audit lifecycle` が exit 0 で通る。
- `python -m ai_ops check` が exit 0 で通る。
- 新規 pytest が pass する。
- CI (5 jobs: python/nix × ubuntu/macos/windows) が green。
- PR merge 後、main で `python -m ai_ops audit lifecycle` を再走させ、違反 0 を確認。

## Idempotence and Recovery

- 各日本語化作業は単一 file 編集なので、git revert で個別に戻せる。
- audit 実装変更も git revert 可能。
- 万一 audit が誤検知で他プロジェクトを壊すリスク → audit 対象は ai-ops 自身の `docs/` のみ (cwd-based)。他プロジェクトに副作用なし。

## Artifacts and Notes

- PR URL: TBD
- merge commit: TBD

## Interfaces and Dependencies

- `ai_ops/audit/lifecycle.py`: 既存 module を拡張。
- `tests/audit/`: 既存 test ディレクトリに pytest を追加。
- AGENTS.md §Natural language: 変更なし。本 plan は宣言済みポリシーの enforcement を実装するもの。
