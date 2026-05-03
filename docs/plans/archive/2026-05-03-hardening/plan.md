# Hardening (PR β)

Branch: `fix/hardening`
Worktree: `../ai-ops.hardening/`

## Purpose / Big Picture

PR α (#7) のマージ後、API key 登録の運用テスト中に security 上の不適切な扱いが 5 件発覚した:

1. `bw list items` の生 JSON を画面出力 → 旧 API key 値がチャット履歴に残った
2. `gh secret set --body <value>` で平文を CLI 引数に渡した → process list 経由で瞬間的に値が見える
3. AI エージェントが `printf "y\n" | ai-ops bootstrap` で Confirm を bypass → AGENTS.md §Operation Model 違反
4. BW_SESSION token をチャットメッセージで受け取った → 短命だが Anthropic 側のチャット保存に乗る
5. 「session を unset した」と不正確に報告 → shell unset と context 残存を混同

「規律に頼らず仕組みで止める」原則で 4 層に対処する:

1. **コード**: `_gh_secret_set` を `gh secret set --body-file -` (stdin) に、`bootstrap --yes` flag で正規 bypass を提供
2. **規約**: ADR 0004 に「絶対やらない」リストを明文化、AGENTS.md / operation.md に AI 向け 5 原則
3. **検査**: `audit security` に `FORBIDDEN_SECRET_PATTERNS` を追加し、grep ベースで違反を機械検出
4. **規律**: AI ワークフローに secret 扱いの 5 原則を追加 (最後の砦)

加えて、元の PR β スコープから 2 件: `worktree cleanup --auto-archive` (Tier 別 archive 自動化) と pre-push hook optional install。Tier 推薦 (元の β の 1 件) は PR γ に回す (今回スコープ外)。

## Progress

- [x] (2026-05-03 06:00Z) Initial plan drafted.
- [x] (2026-05-03 06:10Z) `_gh_secret_set` を `--body-file -` + stdin 経由に変更。process list に値が出ない。
- [x] (2026-05-03 06:15Z) `bootstrap --yes` / `-y` flag 追加。`run_install` / `run_install_secrets` に `yes` パラメータを伝搬。
- [x] (2026-05-03 06:25Z) `ai_ops/audit/security.py` に `SECRET_ARG_FORBIDDEN_PATTERNS` 追加。`ai_ops/` 配下 (self module 除外) を grep して `--body <secret>` 等を FAIL 検出。tests/ は除外 (test fixture を含むため)。
- [x] (2026-05-03 06:35Z) ADR 0004 を amend (絶対やらないリスト 5 件 + AI 5 原則)。AGENTS.md §Safety と `docs/operation.md` の AI ワークフロー section にも反映。
- [x] (2026-05-03 06:50Z) `worktree cleanup --auto-archive` 実装 (`_read_tier`、`find_archive_pending_worktrees`、`auto_archive_plan`)。Tier A / unmanaged は git mv + commit + push、Tier B/C は警告のみで PR 経路を案内。
- [x] (2026-05-03 06:52Z) pre-push hook は本 PR スコープから外し PR γ に分離 (Decision Log 参照)。
- [x] (2026-05-03 06:58Z) `python -m ai_ops check` 全パス、pytest 233 件 PASS (新規 11 件: stdin / yes / FORBIDDEN_SECRET / tier 読取 / auto-archive)。
- [ ] PR 作成、CI 通過 (本 PR が AI レビュー dogfood の初実走になる)、merge、archive、worktree-cleanup。

## Surprises & Discoveries

- (作業中に追記)

## Decision Log

- Decision: `_gh_secret_set` は `--body-file -` + stdin で渡す。tempfile は使わない。
  Rationale: tempfile は disk に値が一時的に書かれるリスクがある。stdin なら memory のみ。`gh` の `--body-file -` は stdin から読む正規仕様。
  Date/Author: 2026-05-03 / Claude.

- Decision: `bootstrap --yes` は `tier 1` ツール install と secrets 登録の両方を skip-confirmation する 1 個の flag。tool 確認と secret 確認を別々の flag にしない。
  Rationale: 2 個に分けても使用者の判断負荷を増やすだけ。`--yes` は「私 (使用者) は事前にすべての操作内容を承認した」という宣言として機能する。
  Date/Author: 2026-05-03 / Claude.

- Decision: `audit security` の FORBIDDEN_SECRET_PATTERNS は `ai_ops/` 配下のみ scan。`tests/` は対象外。
  Rationale: テストでは意図的に secret パターンを書く (mock の固定値、test fixture 等)。tests/ を含めると誤検知だらけになる。
  Date/Author: 2026-05-03 / Claude.

- Decision: pre-push hook の install は `bootstrap --tier 2` の中ではなく、専用の `--with-pre-push-hook` flag にする。
  Rationale: tier 2 は recommended tools (shellcheck 等) の install。hook の install は別軸の規律強化なので、混ぜない。`--with-secrets` と同じパターン。
  Date/Author: 2026-05-03 / Claude.

- Decision: pre-push hook の検査内容は最小限: 「branch 名が `<type>/<slug>` 形式」「Tier B+ プロジェクトで main への直 push 禁止」の 2 項目だけ。
  Rationale: hook を増やすほど開発の摩擦が増え、`--no-verify` を使いたくなる誘惑が強くなる。最小限なら使い続けてもらえる。
  Date/Author: 2026-05-03 / Claude.

- Decision: Tier 推薦ロジックは本 PR では実装しない。
  Rationale: PR α で「複雑度を増やさない」原則を立てた。security hardening + auto-archive + pre-push hook で本 PR は十分な規模。Tier 推薦は別 PR (γ) に分離する。
  Date/Author: 2026-05-03 / Claude.

## Outcomes & Retrospective

ship したもの (PR β):

1. **Security hardening (4 層)**
   - **コード**: `_gh_secret_set` を `--body-file -` + stdin に。process list に値が出ない。`bootstrap --yes` / `-y` で正規 bypass を提供 (Operation Model 違反な `echo y` を不要にする)。
   - **規約**: ADR 0004 に「絶対やらないリスト」5 件 (CLI 引数渡し / print / 生 output / チャット貼付 / Confirm bypass) を明文化、AI 5 原則も同 ADR + `docs/operation.md` で参照。
   - **検査**: `audit security` の `SECRET_ARG_FORBIDDEN_PATTERNS` で `ai_ops/` 配下を grep。`--body <value>` 等を FAIL 検出。tests/ は意図的に除外。
   - **規律**: AGENTS.md §Safety に 1 行追記、`docs/operation.md` の AI ワークフローに 5 原則。

2. **`worktree cleanup --auto-archive`** (ADR 0010 §Lifecycle 4 を Tier A で自動化)
   - `_read_tier` が `.ai-ops/harness.toml` から `workflow_tier` を読む (manifest 無し = ai-ops 自身は Tier A 相当)。
   - `find_archive_pending_worktrees` が「PR merged だが plan が active」の worktree を検出。
   - `auto_archive_plan` が Tier A / unmanaged で `git mv` + commit + push、Tier B / C では警告のみで PR 経路を案内。
   - `worktree cleanup --auto-archive` を呼ぶと、archive 忘れの worktree も 1 コマンドで cleanup まで到達できる。

3. **テスト 11 件追加** (合計 233 件 PASS)
   - `_gh_secret_set` が CLI 引数に値を含めず stdin で渡すこと
   - `--yes` で confirmation が呼ばれないこと
   - `audit security` が forbidden pattern を検出 / safe pattern を許容 / tests/ を除外
   - `_read_tier` の挙動、`auto_archive_plan` の Tier 別分岐 (A 直 push / B 警告のみ)

### スコープから外したもの

- **pre-push hook optional install**: 元の plan には含めていたが、本 PR のスコープが膨らむため PR γ に分離。「機能追加より前にまず削減」原則に沿い、本 PR を確実に小さく保つ。
- **Tier 推薦ロジック**: 元から PR γ 予定。

### 直前の事故への効果検証

PR α マージ後の運用で発覚した 5 件の不適切扱いに対して:

| 事故 | 本 PR の防止策 | 効果 |
|---|---|---|
| `bw list` 生 JSON 露出 | (今回未対応、規律のみ) | 5 原則の 1 番目で AI に意識付け、将来 audit pattern 追加余地 |
| `gh secret set --body <v>` 平文渡し | コード変更 + audit FAIL | 機械的に防止 |
| `echo y \| bootstrap` で bypass | `--yes` 正規 flag | 正規ルートを提供 |
| BW_SESSION チャット受信 | 規約 (ADR 0004 + 5 原則) | 規律ベース、技術的強制は将来 |
| 「unset した」不正確報告 | 規約 (5 原則 5 番目) | 規律ベース |

技術的強制が入ったのは 2 件、規律ベースが 3 件。後者も `audit security` に pattern を追加する余地がある (将来 PR で対応)。

### 今後の plan へのフィードバック

- 「コード / 規約 / 検査 / 規律」の 4 層で考えると漏れが少ない。今回も 4 層すべてに手を入れた。
- pre-push hook を分離した判断は正しい (本 PR に詰めると 1 PR の重みが過大)。複雑度抑制原則は引き続き機能。
- 本 PR は ai-ops 自身の AI レビュー dogfood の **初実走**になる (#7 マージ後初の PR、API key 登録済み)。レビュー結果は本 PR 自身の Comment に出る予定。これは self-validation として強い。

## Improvement Candidates

(作業中に追記)

## Context and Orientation

- `ai_ops/bootstrap.py` の `_gh_secret_set` (PR α で追加): `subprocess.run(["gh", "secret", "set", key, "--body", value, "--repo", repo])`。`--body` 引数渡しが問題。
- `ai_ops/bootstrap.py` の `run_install_secrets`: `_confirm("\nProceed?", dry_run=...)` で確認。`--yes` flag は無い。
- `ai_ops/audit/security.py`: name + value scan を実施。CLI 引数 pattern の検出は無し。
- `ai_ops/audit/lifecycle.py` の `FORBIDDEN_ACTIVE_PATTERNS`: `--no-verify` 等を grep で検出する仕組みあり。secret 関連を追加する余地あり。
- `docs/decisions/0004-secrets-management.md` (既存): secret 値を AI 文脈に入れない原則を宣言。具体的な「絶対やらないリスト」は未明文化。
- `ai_ops/worktree.py` の `run_worktree_cleanup`: 「PR merged + plan archived」の両信号で削除。archive 自体は手動。
- `ai_ops/bootstrap.py` の `--tier` flag: 1=required、2=recommended の 2 値。

## Plan of Work

### 1. `_gh_secret_set` を stdin 経由に変更

```python
def _gh_secret_set(repo: str, key: str, value: str, dry_run: bool) -> bool:
    if dry_run:
        print(f"  [dry-run] would set secret {key} on {repo}")
        return True
    result = subprocess.run(
        ["gh", "secret", "set", key, "--body-file", "-", "--repo", repo],
        input=value,
        capture_output=True, text=True, check=False, timeout=20,
    )
    ...
```

`--body-file -` + `input=value` で stdin から値を流し込む。process list には `gh secret set <KEY> --body-file - --repo <repo>` しか出ない (値は出ない)。

### 2. `bootstrap --yes` flag

`cli.py` の bootstrap parser に `--yes` flag を追加。`handle_bootstrap` で `args.yes` を `run_install` / `run_install_secrets` に渡す。両関数の `_confirm` を bypass するパスを追加。

### 3. `audit security` の FORBIDDEN_SECRET_PATTERNS

`ai_ops/audit/security.py` に新セクションを追加 (または `ai_ops/audit/lifecycle.py` の `FORBIDDEN_ACTIVE_PATTERNS` に追記、どちらが適切か実装時判断)。実装方針:

```python
SECRET_ARG_FORBIDDEN_PATTERNS = (
    (r'--body[\s=]+["\']?[\$\{]', "secret value passed via --body CLI arg"),
    (r'--password[\s=]+["\']?[\$\{]', "password passed via CLI arg"),
    (r'--token[\s=]+["\']?[\$\{]', "token passed via CLI arg"),
)
```

scan 対象は `ai_ops/` のみ。`tests/` は test fixture を含むので除外。

### 4. ADR 0004 改訂 + 5 原則

`docs/decisions/0004-secrets-management.md` に「絶対にやらないリスト」5 項目を追加 (上で挙げた 5 件)。
`docs/operation.md` の「AI エージェントが従うワークフロー」section に「secret 扱いの 5 原則」を 1 ブロックで追加。
`AGENTS.md` §Safety に 1 行追記: 「秘匿情報扱いは ADR 0004 厳守、`audit security` で機械的に強制」。

### 5. `worktree cleanup --auto-archive`

`ai_ops/worktree.py` の `run_worktree_cleanup` に flag を追加。`--auto-archive` 指定時:
- マージ済み PR を持つ worktree について、対応 plan が active (未 archive) なら、`git mv` で archive ディレクトリへ移動 + commit
- Tier A (ai-ops 本体) は `git push origin main` で直接反映
- Tier B/C は archive PR を立てる (`git checkout -b chore/archive-<slug>`、push、`gh pr create`)
- archive 完了後に worktree を削除

最初は ai-ops 自身 (Tier A) のみ実装し、Tier B/C は別 PR で対応する選択肢もある。本 PR では **Tier A 経路のみ実装**。Tier B/C は warning で「manually archive via PR」を案内。

### 6. pre-push hook optional install

`ai_ops/bootstrap.py` に `install_pre_push_hook(repo: Path)` を追加。`bootstrap --with-pre-push-hook --project <path>` で使用者承認の上 `.git/hooks/pre-push` を書き込む。検査内容:

```sh
#!/usr/bin/env bash
# Installed by ai-ops bootstrap --with-pre-push-hook (PR β)
remote="$1"
url="$2"
while read local_ref local_sha remote_ref remote_sha; do
    branch="${local_ref#refs/heads/}"
    if [[ "$branch" == "main" || "$branch" == "master" ]]; then
        # Tier B+ check: if .ai-ops/harness.toml declares tier B/C, refuse direct push to main
        if [ -f .ai-ops/harness.toml ]; then
            if grep -E '^workflow_tier\s*=\s*"[BC]"' .ai-ops/harness.toml; then
                echo "ERROR: direct push to $branch forbidden by Tier B/C policy" >&2
                exit 1
            fi
        fi
    elif [[ ! "$branch" =~ ^(feat|fix|chore|docs|refactor)/[a-z0-9-]+$ ]]; then
        echo "WARNING: branch '$branch' does not match <type>/<slug> convention" >&2
    fi
done
exit 0
```

### 7. テスト

- `tests/test_bootstrap.py`: `_gh_secret_set` が stdin で値を渡すこと (`subprocess.run` の `input` kw を mock で確認)、`--yes` で confirm が呼ばれないこと、`install_pre_push_hook` が dry-run で書き込まないこと。
- `tests/test_audit.py`: FORBIDDEN_SECRET_PATTERNS が違反を検出すること、ai_ops/ 配下のみ scan すること、tests/ は除外されること。
- `tests/test_worktree.py`: `--auto-archive` が Tier A で直 push、Tier B/C で警告のみ。

## Concrete Steps

```sh
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops.hardening

# 1-2. _gh_secret_set + bootstrap --yes
$EDITOR ai_ops/bootstrap.py ai_ops/cli.py

# 3. audit security の FORBIDDEN_SECRET_PATTERNS
$EDITOR ai_ops/audit/lifecycle.py ai_ops/audit/security.py

# 4. ADR 0004 + AGENTS.md + operation.md
$EDITOR docs/decisions/0004-secrets-management.md AGENTS.md docs/operation.md

# 5. worktree cleanup --auto-archive
$EDITOR ai_ops/worktree.py ai_ops/cli.py

# 6. pre-push hook
$EDITOR ai_ops/bootstrap.py templates/artifacts/pre-push  # hook 本体は templates に置く

# 7. テスト
$EDITOR tests/test_bootstrap.py tests/test_audit.py tests/test_worktree.py
python -m pytest -v

# 8. 検証
python -m ai_ops check

# 9. PR (本 PR は AI レビュー dogfood の実走テスト)
git add -A && git commit -m "fix(security): harden secrets handling + auto-archive + pre-push hook (PR β)"
git push -u origin fix/hardening
gh pr create ...
```

## Validation and Acceptance

- `python -m ai_ops audit security` exit 0 (本 PR の修正自体が新規検査を pass する)
- `python -m ai_ops check` exit 0、pytest 全パス
- `_gh_secret_set` を呼んだとき `subprocess.run` の引数に値が含まれない (input kw 経由のみ)
- `bootstrap --yes` で `_confirm` が呼ばれない
- `audit security` で FORBIDDEN_SECRET_PATTERNS が ai_ops/ 内の `--body $value` 等を検出する
- ADR 0004 に「絶対やらないリスト」5 項目が含まれる
- `worktree cleanup --auto-archive` が Tier A プロジェクト (ai-ops 自身) で動く
- pre-push hook が `bootstrap --with-pre-push-hook --project <path>` で install できる
- 本 PR の merge 過程で AI レビューが実走 (`ai-ops review-pr` job が成功し、Comment に cost footer が付く)

## Idempotence and Recovery

- `_gh_secret_set` の変更は git revert 可能、既存テストの mock は input kw を見るように追従。
- `--yes` flag は新規追加、既存の対話パスは変えない。
- `audit security` の FORBIDDEN_SECRET_PATTERNS は最初は warning ベースで導入し、安定後に FAIL に格上げする選択肢もある。本 PR では FAIL から開始 (Step 1 の言語ポリシーと同じ厳しさ)。
- pre-push hook の install は idempotent (既存があれば上書きしない、警告)。
- `worktree cleanup --auto-archive` は dry-run と confirmation を保つ。

## Artifacts and Notes

- PR URL: TBD
- 本 PR の AI レビュー結果: TBD (本 PR が ai-ops 自身の AI レビュー dogfood の初実走になる)

## Interfaces and Dependencies

- 新 flag: `bootstrap --yes`、`bootstrap --with-pre-push-hook --project <path>`、`worktree cleanup --auto-archive`
- 新 audit pattern: ai_ops/ 配下の secret CLI 引数渡し検出
- 既存 file 拡張: `ai_ops/{bootstrap,worktree,audit/security,audit/lifecycle,cli}.py`、`docs/decisions/0004-secrets-management.md`、`docs/operation.md`、`AGENTS.md`
- 新規 file: `templates/artifacts/pre-push` (hook script、`audit lifecycle` REQUIRED_FILES に登録)
