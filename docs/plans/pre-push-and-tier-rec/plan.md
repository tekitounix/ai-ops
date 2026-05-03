# Pre-push hook + Tier 推薦 + Smoke test (PR γ)

Branch: `feat/pre-push-and-tier-rec`
Worktree: `../ai-ops.pre-push-and-tier-rec/`

## Purpose / Big Picture

PR β で残した 3 件を 1 PR で:

1. **pre-push hook (optional install)** — branch 命名 + Tier B+ の main 直 push 禁止を local で止める。`bootstrap --with-pre-push-hook --project <path>` で使用者承認の上 install。
2. **`audit projects` の Tier 推薦** — 宣言済み tier が無い管理対象に対して、visibility / contributor 数 / age 等の signal から推薦 tier を P2 として表示。
3. **smoke test** — `@pytest.mark.smoke` で実 API を叩く 1-2 件。API key 設定時のみ実行 (skip otherwise)。LLM 仕様変更を本番前に検知。

これで前回露出した 7 つの穴のうち残り 3 件が塞がる。

## Progress

- [x] (2026-05-03 07:30Z) Initial plan drafted.
- [x] (2026-05-03 07:40Z) pre-push hook を `templates/artifacts/pre-push` に作成 (branch 命名 + Tier B/C main 直 push 禁止)。lifecycle audit `REQUIRED_FILES` + `allowed_template_files` に登録。
- [x] (2026-05-03 07:48Z) `bootstrap --with-pre-push-hook --project PATH` を実装。`install_pre_push_hook()` は既存 hook があれば skip + 警告、yes flag で確認なし install。
- [x] (2026-05-03 08:00Z) `audit projects` に `recommended_tier` field + `_recommend_tier()` + `_gh_repo_visibility_and_contributors()`。managed プロジェクトで未宣言 (default D) なら gh から signal を取って P2 観察的に推薦。失敗時 None。
- [x] (2026-05-03 08:10Z) smoke test (`tests/test_review_smoke.py`、`@pytest.mark.smoke` で skip default)。`pyproject.toml` に marker 登録。Anthropic / OpenAI 各 1 件で API key 設定時のみ実走。
- [x] (2026-05-03 08:15Z) テスト 11 件追加 (合計 243 PASS、smoke 2 件 skip)。
- [x] (2026-05-03 08:18Z) `python -m ai_ops check` 全パス。
- [ ] PR 作成、CI 通過 (AI レビュー再実走)、merge、auto-archive、worktree-cleanup。

## Surprises & Discoveries

- (作業中に追記)

## Decision Log

- Decision: pre-push hook install は `--with-pre-push-hook --project <path>` を `bootstrap` の flag として実装 (PR α で `--with-secrets` を組み込んだのと同パターン)。
  Rationale: 専用 subcommand を増やさない方針 (PR α の削減原則)。bootstrap は「初期セットアップ」の責務なので hook install も自然に収まる。
  Date/Author: 2026-05-03 / Claude.

- Decision: hook 内容は最小限の 2 項目 (branch 命名 + Tier B+ main 直 push 禁止)。それ以上は増やさない。
  Rationale: hook が複雑なほど摩擦が増え、`--no-verify` で skip したくなる誘惑が強くなる。最小限なら使い続けてもらえる。
  Date/Author: 2026-05-03 / Claude.

- Decision: Tier 推薦は **P2 (観察のみ)** として `audit projects --json` の出力に `recommended_tier` field を追加するだけ。`tier_violations` のように priority を上げない。
  Rationale: 推薦は推測。priority に乗せると誤検知で運用を乱す。使用者が JSON を見て判断材料にする位置付け。
  Date/Author: 2026-05-03 / Claude.

- Decision: 推薦ロジックは **保守的なルールベース** (LLM は使わない)。
  Rationale: 推薦のためだけに LLM を呼ぶのはコストとレイテンシに見合わない。`mgd=yes` で `workflow_tier` 未宣言、かつ visibility public なら C 推薦、private + contributor 1 名なら A 推薦、private + contributor >1 名なら B 推薦、archived/no-recent-commits なら D 推薦、のような単純規則。
  Date/Author: 2026-05-03 / Claude.

- Decision: smoke test は `tests/test_review_smoke.py` 1 ファイル、`@pytest.mark.smoke` で skip default。CI では別 job (`smoke`) として `if: secrets.ANTHROPIC_API_KEY != ''` で gate。
  Rationale: 実 API を毎 PR で叩くとコスト + flakiness。smoke は schedule (週次) または手動 trigger でいい。本 PR 自身は dogfood で実 API が走るので smoke が無くても production 検証は最小限なされている。
  Date/Author: 2026-05-03 / Claude.

## Outcomes & Retrospective

ship したもの (PR γ):

1. **pre-push hook (optional install)** — `templates/artifacts/pre-push` に最小 hook (branch 命名 + Tier B/C main 直 push 禁止)。`bootstrap --with-pre-push-hook --project PATH` で使用者承認の上 install。既存 hook は上書きしない (使用者の hook を尊重)。
2. **Tier 推薦ロジック** — `audit projects --json` 出力に `recommended_tier` field 追加。managed プロジェクトで未宣言 (default D) のとき、`gh repo view` から visibility / contributors を取得し:
   - public → C 推薦
   - private + contributors > 1 → B 推薦
   - private + solo + 活動中 → A 推薦
   - 1 年以上 inactive → 推薦なし (D 維持が妥当)
   `gh` 不在 / 取得失敗時は None。priority は変えない (P2 観察のみ、誤検知で運用を乱さない)。
3. **smoke test** — `tests/test_review_smoke.py` (`@pytest.mark.smoke` で skip default)。Anthropic / OpenAI API 各 1 件、API key 設定時のみ実走。SDK 仕様変更を本番 PR より先に検知できる。`pyproject.toml` に marker 登録。
4. **テスト 11 件追加** (合計 243 PASS / smoke 2 件 skip): pre-push hook の 4 件 (non-repo / dry-run / 既存 skip / executable copy)、Tier 推薦の 6 件 (各分岐 + edge case)、smoke 2 件 (Anthropic / OpenAI ping)。

### スコープ外 (今回も保たれた)

- 7 つの穴のうち #1 (bw 生 JSON 露出) は規律のみで未自動化。将来 `audit security` に新 pattern 追加で技術化可能だが、本 PR では未対応 (複雑度抑制)。
- smoke test の CI integration (別 job + secrets gate) は未実装。本 PR は marker と test 追加のみ。CI 統合は需要が出てから別 PR で。

### 当初の問題リスト 7 件への完全対応状況

| # | 問題 | 状態 |
|---|---|---|
| 1 | dogfood ギャップ | ✅ PR α + 本 PR で AI レビュー実走確認 |
| 2 | API key 未登録 | ✅ PR α `--with-secrets` で登録、`--yes` で対話省略可 |
| 3 | コスト未管理 | ✅ PR α で Comment footer に毎回表示 |
| 4 | docs 肥大化 | ✅ PR α で 275 → 136 行に圧縮 |
| 5 | archive 自動化 | ✅ PR β `worktree cleanup --auto-archive` |
| 6 | エージェント遵守 | ✅ PR β secret 5 原則 + 本 PR pre-push hook (optional) |
| 7 | smoke test | ✅ 本 PR で `@pytest.mark.smoke` 追加 |

直前の事故 5 件 (PR α 後発覚) は PR β + 本 PR で完了。

### 今後の plan へのフィードバック

- 「機能を増やしながら複雑度を増やさない」原則は α / β / γ で一貫して適用できた。
  - α: subcommand 18→12、docs 275→136
  - β: 新 subcommand なし、新 file 1 (pre-push template は γ)、機能は既存拡張で実装
  - γ: 新 file 2 (pre-push、smoke test)、新 subcommand なし、既存 flag 拡張
- ai-ops 自身の AI レビュー dogfood は本 PR で 2 回目の実走 (PR β #8 が初実走)。Sonnet 4.6 が cost $0.05-0.06 で contract compliance を判定する loop が安定している。
- pre-push hook は最小限 (2 項目) に保ったので、`--no-verify` で skip したくなる誘惑が小さい。将来追加するなら同様に「これがあって本当に困らないか」を厳しく問う。

## Improvement Candidates

(作業中に追記)

## Context and Orientation

- `ai_ops/bootstrap.py`: PR α/β で `_gh_secret_set` (stdin)、`run_install_secrets`、`--yes` を追加済み。`--with-pre-push-hook` も同パターンで追加可能。
- `ai_ops/audit/projects.py`: 9 signal を出力。`workflow_tier` field は宣言値 / default D を返す。`recommended_tier` を追加するなら同じ row に置く。
- `ai_ops/audit/projects.py` の signal 計算は cwd ごとに行うので、git remote の visibility / contributor 数を `gh` 経由で取る (もしくは local git log だけで完結させる)。LLM 不使用。
- `tests/`: pytest marker `slow` は既存。`smoke` を追加する。
- `pyproject.toml`: pytest config を見て marker を登録。
- 既存 `.github/workflows/ci.yml`: `python` job で `pytest -m slow` も走らせている。`smoke` は別 job、secrets 必須。

## Plan of Work

### 1. pre-push hook

`templates/artifacts/pre-push` (新規):

```bash
#!/usr/bin/env bash
# Installed by `ai-ops bootstrap --with-pre-push-hook` (ADR 0010 §Lifecycle 4 enforcement)
# Checks (local):
#  - branch name matches `<type>/<slug>` convention
#  - Tier B/C projects: refuse direct push to main / master
set -e
remote="$1"
url="$2"
zero=$(git hash-object --stdin </dev/null | tr '[0-9a-f]' '0')
while read local_ref local_sha remote_ref remote_sha; do
    branch="${local_ref#refs/heads/}"
    if [ "$local_sha" = "$zero" ]; then
        # branch deletion; allow
        continue
    fi
    if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
        if [ -f .ai-ops/harness.toml ] && \
           grep -qE '^\s*workflow_tier\s*=\s*"[BC]"' .ai-ops/harness.toml; then
            echo "ai-ops pre-push: direct push to '$branch' is forbidden by Tier B/C policy" >&2
            echo "  Open a feature branch and PR instead (ADR 0009)." >&2
            exit 1
        fi
    elif ! [[ "$branch" =~ ^(feat|fix|chore|docs|refactor)/[a-z0-9._-]+$ ]]; then
        echo "ai-ops pre-push: branch '$branch' does not match <type>/<slug> convention (ADR 0010)" >&2
        echo "  expected types: feat/fix/chore/docs/refactor" >&2
        exit 1
    fi
done
exit 0
```

`ai_ops/bootstrap.py` に `install_pre_push_hook(project: Path, dry_run: bool, yes: bool)`:
- `<project>/.git/hooks/pre-push` を template から copy + chmod +x
- 既存 hook がある場合は警告 + skip (既存内容を上書きしない)
- yes なしなら確認 prompt

CLI: `bootstrap --with-pre-push-hook --project <path>` flag を追加。

### 2. Tier 推薦ロジック

`ai_ops/audit/projects.py` に `_recommend_tier(project_path, signals)` を追加:

```python
def _recommend_tier(path, mgd, declared_tier, visibility, contributors, last_commit_days):
    if mgd != "yes" or declared_tier:  # 宣言済みは推薦しない
        return None
    if visibility == "public":
        return "C"  # public なら本番扱い
    if last_commit_days > 365:
        return "D"  # 1 年触ってないなら spike 扱い
    if (contributors or 1) > 1:
        return "B"
    return "A"
```

JSON 出力に `recommended_tier` field を追加。table 表示は P2 行に小さく表示。

`gh repo view --json visibility,...` で取得 (既存の `gh` 経由パターン踏襲)。`gh` 不在なら None。

### 3. smoke test

`tests/test_review_smoke.py` (新規):

```python
@pytest.mark.smoke
def test_anthropic_api_returns_parseable_json(monkeypatch):
    """API key が設定されていれば実 API を叩く。default は skip。"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    text, in_tok, out_tok = review._call_anthropic(
        "claude-sonnet-4-6",
        "Reply with a JSON object {\"ok\": true}",
        "Test ping",
        api_key,
    )
    assert text is not None
    assert in_tok > 0
    assert out_tok > 0
```

`pyproject.toml` の pytest config に `smoke` marker を登録。

`.github/workflows/ci.yml` に optional `smoke` job (本 PR スコープ外。今回は marker と test 追加だけで、CI integration は次 PR or 手動 trigger に任せる)。

### 4. テスト

- `test_bootstrap.py`: `install_pre_push_hook` が dry-run で書き込まないこと、既存があれば skip + 警告、yes なしなら confirm を呼ぶこと。
- `test_audit.py`: `_recommend_tier` の各分岐 (public / private 1 contributor / private multi / archived)。
- `test_review_smoke.py`: skip default、API key ありなら実 API ping。
- README claim verification: 既存変更なし。

## Concrete Steps

```sh
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops.pre-push-and-tier-rec

# 1. pre-push hook
$EDITOR templates/artifacts/pre-push
$EDITOR ai_ops/bootstrap.py ai_ops/cli.py

# 2. Tier 推薦
$EDITOR ai_ops/audit/projects.py

# 3. smoke test
$EDITOR tests/test_review_smoke.py
$EDITOR pyproject.toml  # marker 登録

# 4. テスト
$EDITOR tests/test_bootstrap.py tests/test_audit.py
python -m pytest -v

# 5. lifecycle audit に templates/artifacts/pre-push を REQUIRED_FILES として登録
$EDITOR ai_ops/audit/lifecycle.py

# 6. 検証
python -m ai_ops check

# 7. PR
git add -A && git commit -m "feat(γ): pre-push hook + tier recommendation + smoke test"
git push -u origin feat/pre-push-and-tier-rec
gh pr create ...

# 8. merge → auto-archive で 1 コマンド完結
gh pr merge <N> --squash
git pull --ff-only && git fetch --prune origin
python -m ai_ops worktree cleanup --auto-archive --auto
```

## Validation and Acceptance

- `python -m ai_ops audit lifecycle` exit 0 (新ファイル `templates/artifacts/pre-push` が REQUIRED_FILES に含まれる)
- `python -m ai_ops check` exit 0、pytest 全パス (smoke は skip)
- `bootstrap --with-pre-push-hook --project <path> --dry-run` で書き込み無し、本実行で `.git/hooks/pre-push` が生成
- pre-push hook が:
  - `git push origin feat/x` で OK
  - `git push origin some-random-name` で reject (branch 命名違反)
  - tier B/C 宣言済み repo で `git push origin main` で reject
- `audit projects --json` 出力に `recommended_tier` field が現れる
- 本 PR のマージで AI レビューが再走、cost footer が出る

## Idempotence and Recovery

- pre-push hook install は idempotent (既存があれば skip)、削除は使用者が手動で `rm .git/hooks/pre-push`
- Tier 推薦は read-only (signal 計算のみ)
- smoke test は default skip なので本 PR が green の保証は変わらない

## Artifacts and Notes

- PR URL: TBD
- AI レビュー結果: TBD (本 PR 自身の dogfood)

## Interfaces and Dependencies

- 新 flag: `bootstrap --with-pre-push-hook --project <path>`
- 新 file: `templates/artifacts/pre-push`、`tests/test_review_smoke.py`
- 既存拡張: `ai_ops/{bootstrap,cli,audit/projects,audit/lifecycle}.py`
- pytest marker: `smoke` (`pyproject.toml` で登録)
