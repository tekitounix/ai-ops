# E2E Fixes (PR η)

Branch: `fix/e2e-fixes`
Worktree: `../ai-ops.e2e-fixes/`

## Purpose / Big Picture

PR ζ E2E in ai-ops-managed-test で 2 件の bug を発見:

1. **`setup ci` の `@v1` 置換漏れ**: `templates/artifacts/.github/workflows/ai-ops.yml` は `uses: ...managed-project-{check,review}.yml@v1` だが、ai-ops repo に `v1` tag が無く、`setup.py` も `@v1` を `@<ai_ops_ref>` に置換しない。結果、配布された caller workflow が reusable workflow をロードできず startup_failure。
2. **`secrets: inherit` で startup_failure**: caller 側に ANTHROPIC_API_KEY 等が無い場合でも reusable workflow ロードに失敗する (`required: false` 宣言があっても効いていない可能性)。明示渡しに変える方が堅牢。

## Progress

- [x] (2026-05-03 13:00Z) Initial plan drafted.
- [x] (2026-05-03 13:10Z) template の `uses: ...@v1` を `@main` に変更、コメントも更新。
- [x] (2026-05-03 13:12Z) `setup.py` の `run_setup_ci_workflow` で `@main` を `@<ai_ops_ref>` に置換する 2 行追加。
- [x] (2026-05-03 13:13Z) `secrets: inherit` を `secrets: ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` 等の明示渡しに変更。
- [x] (2026-05-03 13:18Z) `tests/test_setup.py` 新規 (3 件): substitution / explicit-secrets / no-v1。
- [x] (2026-05-03 13:20Z) `ai-ops check` 全パス、pytest 266 件 PASS。
- [ ] PR 作成、CI 通過、merge、auto-archive。

## Surprises & Discoveries

- E2E でないと見つからない bug のクラス: GitHub Actions の reusable workflow load 時の制約 (caller-callee secret 制約) は actionlint でも捕まえられない。
- 「`@main` を default」と「`@v1` tag を pin」の trade-off: tag pin は安定だが ai-ops 自身に tag を切る運用負荷を生む。default は `@main` で十分、release を切るタイミングで template を `@v1.0` に bump する。

## Decision Log

- Decision: template default は `@main`、`setup ci --ai-ops-ref` で tag pin 可。
  Rationale: ai-ops 自身に release tag を切る運用は今のところ無い。`@main` なら最新 fix が即届く。pin したい使用者は flag で。
  Date/Author: 2026-05-03 / Claude.

- Decision: `secrets: inherit` を明示渡し `secrets: ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` に変える。
  Rationale: `inherit` は caller の全 secret を passthrough するが、reusable workflow ロード時に何らかの制約 (詳細未解明だが startup_failure を観測) で fail する可能性。明示渡しは挙動が予測可能、不要な secret も渡らない (security 的にも好ましい)。
  Date/Author: 2026-05-03 / Claude.

## Outcomes & Retrospective

ship したもの (PR η):

1. **template fix**: `templates/artifacts/.github/workflows/ai-ops.yml` で `uses: ...@v1` → `@main`、`secrets: inherit` → 明示渡し (`ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` 等)。
2. **setup.py substitution 拡張**: `run_setup_ci_workflow` で `@main` を `@<ai_ops_ref>` に置換する 2 行追加。`--ai-ops-ref v1.0` のような tag pin が機能する。
3. **テスト 3 件追加** (合計 266 件 PASS): substitution の行為確認、明示渡し confirm、@v1 残存 check (uses 行のみ)。

### E2E で発見した 2 件の bug

| 観点 | Before | After |
|---|---|---|
| `setup ci` で配布される workflow | `@v1` ハードコード → ai-ops に v1 tag が無く startup_failure | `@main` default、`--ai-ops-ref` で tag pin 可 |
| review job の secrets | `secrets: inherit` で startup_failure (詳細未解明) | 明示渡し、未設定 secret は空文字列で渡る (review.py 側 neutral skip) |

### E2E が見つけたものの価値

- actionlint や unit test では捕まえられない実 GitHub Actions の制約 (reusable workflow load 時の `secrets: inherit` の挙動など) は、実 PR を立てないと検出できない。
- self-improvement loop (PR ζ → E2E → PR η) の流れが本物の bug を発見した。「ai-ops 自身を ai-ops で運用する」原則の dogfood が効いている。

### 今後の plan へのフィードバック

- `setup ci` 系の helper は **実 repo に PR を立てる E2E** で workflow load 時の制約まで検証する必要がある。今後の workflow 関連変更では同じ E2E pass を必須化する。
- template に hard-coded reference を入れるときは、必ず substitution 候補かどうか docstring で明示する。

## Improvement Candidates

- E2E test を CI で回すか? 「test repo に PR を立てて check pass を確認」を ai-ops 自身の CI で何らかの形で再現できれば、回帰防止になる。今は手動 dogfood のみ。

## Context and Orientation

- `templates/artifacts/.github/workflows/ai-ops.yml`: `@v1` × 2、`secrets: inherit`
- `ai_ops/setup.py:204` の `run_setup_ci_workflow`: `tier: 'D'` → `tier: '{tier}'` と `ai_ops_ref: 'main'` → `ai_ops_ref: '{ai_ops_ref}'` の置換のみ。`@v1` は触っていない。
- ai-ops repo に tag は 0 件 (`git tag --list` 空)
- E2E ログ: ai-ops-managed-test PR #4 で startup_failure × 2 の後、review job 削除で success。`.github/workflows/ai-ops.yml` 内の `@main` 置換は手動で行った。

## Plan of Work

### A. template `@v1` → `@main`

`templates/artifacts/.github/workflows/ai-ops.yml`:
```yaml
uses: tekitounix/ai-ops/.github/workflows/managed-project-check.yml@main
uses: tekitounix/ai-ops/.github/workflows/managed-project-review.yml@main
```

### B. `setup.py` で `@main` を `@<ai_ops_ref>` に置換

```python
content = content.replace("managed-project-check.yml@main",
                           f"managed-project-check.yml@{ai_ops_ref}")
content = content.replace("managed-project-review.yml@main",
                           f"managed-project-review.yml@{ai_ops_ref}")
```

これで `--ai-ops-ref v1.0` のような tag pin にも対応できる。

### C. `secrets: inherit` → 明示渡し

template の `secrets: inherit` を:
```yaml
secrets:
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

に変える。caller 側に該当 secret が無くても (空文字列が渡る)、callee の `required: false` で OK。

### D. テスト

- `tests/test_setup.py` (新規 or 既存): `run_setup_ci_workflow` が `@v1` ではなく `@<ai_ops_ref>` を含む content を生成すること
- `tests/test_audit.py` Phase 12 alias check: template にまだ `@v1` が残っていないこと (regex で検出)

## Concrete Steps

```sh
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops.e2e-fixes
$EDITOR templates/artifacts/.github/workflows/ai-ops.yml
$EDITOR ai_ops/setup.py
$EDITOR tests/test_setup.py  # 新規
python -m pytest tests/test_setup.py -v
python -m ai_ops check
git add -A && git commit -m "fix(setup): substitute @<ai_ops_ref> + replace secrets: inherit (PR η)"
git push -u origin fix/e2e-fixes
gh pr create --label review:request
```

## Validation and Acceptance

- template の `@v1` が 0 件、`@main` が 2 件
- `setup.py` の置換 logic が `@<ai_ops_ref>` も対象
- pytest 263 + 新規 ≥ 2 = ≥ 265 PASS
- `ai-ops check` 全パス
- 本 PR の AI レビューが pass

## Idempotence and Recovery

- 全変更は git revert 可能
- ai-ops-managed-test の workflow は手動修正済み (PR ζ E2E で `@main` に変更済み) なので、本 fix で setup ci を再実行した時に矛盾しない

## Artifacts and Notes

- E2E PR (test repo): https://github.com/tekitounix/ai-ops-managed-test/pull/4 (closed/merged、startup_failure 解消後 success)

## Interfaces and Dependencies

- 既存拡張: `templates/artifacts/.github/workflows/ai-ops.yml`、`ai_ops/setup.py`
- 新規: `tests/test_setup.py` (もし無ければ)
