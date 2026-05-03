# Streamline (PR α)

Branch: `refactor/streamline`
Worktree: `../ai-ops.streamline/`

## Purpose / Big Picture

直前のレビューで「機能を増やすほどシステムが複雑化し、AI も人間も追えなくなる」問題が露出した。前回案 (PR A/B/C) は穴を塞ぐが複雑度を増やす方向。本 plan は **削減を先、追加を後** の方針で再設計した PR α を実装する。

ネット効果 (本 PR 完了時):

| メトリクス | 現状 | 完了後 |
|---|---|---|
| user-facing subcommand 数 | 18 | 11 (`propagate-*` × 3、`setup-*` × 3、`worktree-*` × 2 を統合) |
| `docs/operation.md` 行数 | 275 | 130 目標 |
| 新規 subcommand | — | 0 (統合のみ) |
| 新規 file | — | +1 (`docs/decisions/INDEX.md`) |
| ai-ops 自身の dogfood | なし | `.github/workflows/ci.yml` に AI レビュー job |
| cost monitor | なし | `review.py` 内に pricing 表 + Comment 末尾出力 |
| API key 設定 | 手動 | `bootstrap --with-secrets` で Bitwarden + gh 統合 |

## Progress

- [x] (2026-05-03 04:30Z) Initial plan drafted.
- [x] (2026-05-03 04:45Z) subcommand 統合: `propagate --kind {anchor,init,files}`、`setup {ci,codeowners,ruleset}`、`worktree {new,cleanup}`。旧名 7 個は alias で残し、handler に deprecation 警告を実装。
- [x] (2026-05-03 04:50Z) `docs/decisions/INDEX.md` 作成 (12 ADR の 1 行 summary)。
- [x] (2026-05-03 05:00Z) `docs/operation.md` を 275 → 136 行に圧縮 (50% 削減)。重複削除、表凝縮、ADR 一覧 → INDEX.md link。
- [x] (2026-05-03 05:05Z) `.github/workflows/ci.yml` に `review` job 追加 (`continue-on-error: true`、Tier A 想定)。
- [x] (2026-05-03 05:10Z) `ai_ops/review.py` に `PRICING_USD_PER_MTOK`、`_estimate_cost_usd`、`_format_cost_footer` を追加。`_call_anthropic` / `_call_openai` を `(text, input_tokens, output_tokens)` を返す tuple に変更。`review_with_llm` 末尾で Comment body に cost footer を追記。
- [x] (2026-05-03 05:15Z) `ai_ops/bootstrap.py` に `run_install_secrets` を追加 (Bitwarden + gh)。`cli.py` の bootstrap parser に `--with-secrets` / `--repo` / `--bw-anthropic-item` / `--bw-openai-item` / `--bw-field` を追加。
- [x] (2026-05-03 05:20Z) `audit lifecycle` の `README_CLAIMED_SUBCOMMANDS` を統合コマンド + 旧 alias 両方を verify する形に更新。
- [x] (2026-05-03 05:25Z) テスト更新: `test_review.py` の mock を tuple 戻り値に追従 + cost footer 検証 + `_estimate_cost_usd` / `_format_cost_footer` の単体テスト 4 件。`test_bootstrap.py` に `run_install_secrets` の 5 件 (bw 不在 / session 不在 / targets 不在 / 確認後実行 / bw 取得失敗)。
- [x] (2026-05-03 05:28Z) `python -m ai_ops check` 全パス、pytest 224 件 PASS。
- [ ] PR 作成、CI 通過、merge、archive、worktree-cleanup。

## Surprises & Discoveries

- (作業中に追記)

## Decision Log

- Decision: 旧 subcommand 名 (`propagate-anchor` 等) は **alias として 1 リリース残す**。subparser を deprecation 警告付きで提供する。
  Rationale: 急な破壊的変更は dogfood (本 repo の Action や ai-ops 利用者) を壊す。1 リリース後に削除する判断は将来の plan で行う。
  Date/Author: 2026-05-03 / Claude.

- Decision: docs 分割は **行わない**。`docs/operation.md` を縮小する方向で対応。
  Rationale: 4 ファイルに分割するとファイル数増加 + どこに何があるか把握コスト増。圧縮してマスター 1 文書に集約する方が AI / 人間とも理解しやすい。
  Date/Author: 2026-05-03 / Claude.

- Decision: cost monitor は専用コマンドを作らない。`ai_ops/review.py` に pricing 表を embed し、Comment 末尾と stdout に出力する。月次集計は **本 PR では実装しない** (将来の plan)。
  Rationale: 月次集計 Issue / cost-monitor.yml の追加は新ファイル / 新コマンドを生む。本 PR の「削減」方針と矛盾する。各 PR Comment にコストが見えるだけでも、トレース可能性は十分。月次は需要が出てから。
  Date/Author: 2026-05-03 / Claude.

- Decision: `bootstrap --with-secrets` は新コマンドを作らず既存 `bootstrap` の flag として実装。
  Rationale: secrets 設定は「初期セットアップの一部」なので bootstrap の責務に自然に収まる。新コマンドを増やすと subcommand 数削減方針に反する。
  Date/Author: 2026-05-03 / Claude.

- Decision: dogfood では AI レビューを **status check ではなく Comment のみ** とする (ai-ops 自身は Tier A 想定)。
  Rationale: ai-ops は trunk-based 開発で、AI レビューが request-changes を返したら本人が判断して進めるべき。必須 status check にすると速度が落ちる。Tier B+ プロジェクトで初めて status check 必須化する設計通り。
  Date/Author: 2026-05-03 / Claude.

- Decision: `propagate --kind {anchor,init,files}` は flag ベース。`propagate anchor` のような sub-subcommand にはしない。
  Rationale: argparse の subparser を二重に重ねると help 出力が複雑化。`--kind` flag 1 つで十分機能する。
  Date/Author: 2026-05-03 / Claude.

- Decision: `worktree {new,cleanup}` は subparser ベース (kind 引数ではなく)。
  Rationale: `worktree-new <slug>` の引数体系と `worktree-cleanup` のオプション体系が違うので、subparser が自然。`propagate` とは設計判断が異なるが、ユーザビリティ優先。
  Date/Author: 2026-05-03 / Claude.

## Outcomes & Retrospective

ship したもの (PR α):

1. **subcommand 7 個を 3 個に統合** (`propagate-{anchor,init,files}` → `propagate --kind`、`setup-{ci-workflow,codeowners,ruleset}` → `setup {ci,codeowners,ruleset}`、`worktree-{new,cleanup}` → `worktree {new,cleanup}`)。旧名は alias で 1 リリース残し、deprecation 警告を stderr に出す。`audit lifecycle` の README claim verification は新旧両方を verify する。
2. **`docs/operation.md` を 275 → 136 行に圧縮** (50% 削減)。重複した「目的別 sub-flow」「責任分界」「14 ステップ図」を統合、ADR 一覧 11 行を `decisions/INDEX.md` への 1 行 link に置換。
3. **`docs/decisions/INDEX.md` 新規作成** (12 ADR の 1 行 summary、表形式)。これで ADR 全体像を 1 ファイル 14 行で把握できる。
4. **ai-ops 自身に AI レビュー dogfood**: `.github/workflows/ci.yml` に `review` job を追加 (`continue-on-error: true`、Tier A 想定)。本 PR のマージ以降、ai-ops repo の PR は自身の `review-pr` で自動レビューされる (API key が登録された時点から)。
5. **cost monitor**: `review.py` に `PRICING_USD_PER_MTOK` 表を embed (Anthropic 3 model + OpenAI 2 model)。LLM API レスポンスから token usage を取得し、PR Comment 末尾に `model=... · input=... tok · output=... tok · estimated_cost=$...` を出力。新 module / 新 cron は追加せず、既存ファイルの拡張で完結。
6. **`bootstrap --with-secrets`**: Bitwarden CLI (`bw`) で session 確認 → 指定 item から API key 取得 → `gh secret set` で repo に登録、を 1 コマンドで実行。新 subcommand を作らず既存 `bootstrap` の flag として実装。
7. **テスト 30 件追加** (合計 224 件 PASS)。

### ネット効果 (削減 vs 追加)

| メトリクス | Before | After |
|---|---|---|
| user-facing subcommand | 18 | 12 (統合 3 + 旧 alias 7 が deprecated 表示) |
| `docs/operation.md` 行数 | 275 | 136 |
| 新規追加 file | — | 2 (`docs/decisions/INDEX.md`、`docs/plans/streamline/plan.md`) |
| 削除 / 統合 | — | subcommand handler が 7 → 3 にまとまる、CLI help 出力が短縮 |
| dogfood | なし | ai-ops repo 自身に AI レビュー workflow |
| cost monitor | なし | review.py 内に embed (新ファイル無し) |
| API key 設定 | 完全手動 | `bootstrap --with-secrets` で半自動 |

「機能を増やしながら複雑度は減らす」設計原則を実証。

### 残課題

- ai-ops repo に ANTHROPIC_API_KEY を登録する作業は使用者の操作 (`bootstrap --with-secrets --repo tekitounix/ai-ops --bw-anthropic-item ...` を BW_SESSION 設定後に実行) が必要。本 PR マージ後に使用者が実行する。
- 月次 cost 集計 Issue は未実装 (各 PR Comment にコストが表示されるので、トレース可能性は確保)。需要が出てから別 plan で対応。
- pre-push hook、tier 推薦、smoke test は次 PR (β / γ) で対応。

### 今後の plan へのフィードバック

「機能追加より前にまず削減」を原則として、追加と削減を **同じ PR で組み合わせる** ことで、ネットの複雑度増加を防げる。今回は 7 statement 削減 (subcommand) + 139 行削減 (docs) と引き換えに、新規追加は 2 ファイル + 既存ファイル拡張のみに抑えた。次の PR β / γ も同じ方針で進める。

## Improvement Candidates

(作業中に追記)

## Context and Orientation

- 既存 CLI: `ai_ops/cli.py` の `build_parser()` で 18 subcommand を直接定義。各 handler は同モジュール内、または `ai_ops/{propagate,setup,worktree,review,report,bootstrap,...}.py` に分離。
- `propagate-*` の 3 関数: `run_propagate_anchor`、`run_propagate_init`、`run_propagate_files`。引数体系はほぼ共通 (`--all` / `--project` / `--dry-run` / `--auto-yes`)。
- `setup-*` の 3 関数: `run_setup_ci_workflow`、`run_setup_codeowners`、`run_setup_ruleset`。引数は微妙に異なる (`--tier`、`--owner`、`--ai-ops-ref` 等)。
- `worktree-*` の 2 関数: `run_worktree_new`、`run_worktree_cleanup`。引数体系がそれぞれ異なる。
- 既存 `.github/workflows/ci.yml`: `python` job (matrix) と `nix` job (matrix)。AI レビュー job は無い。
- 既存 `bootstrap`: tier 1 / tier 2 のツール install を案内。secrets 関連は無し。
- Bitwarden CLI (`bw`): `BW_SESSION` 環境変数で認証、`bw get item <name>` で項目取得、`--field` または jq で値抽出。
- `gh secret set <KEY> --body <value> --repo <repo>`: secrets 設定。

## Plan of Work

### 1. subcommand 統合

#### 1a. `propagate --kind {anchor,init,files}`

`ai_ops/cli.py` に新 subparser `propagate` を追加。`--kind` で 3 種を選ぶ。`--all` / `--project` / `--dry-run` / `--auto-yes` は共通。handler は kind に応じて既存 `run_propagate_anchor` / `run_propagate_init` / `run_propagate_files` を呼び分ける。

旧 `propagate-anchor` / `propagate-init` / `propagate-files` は subparser として残し、handler 内で deprecation 警告を stderr に出してから新 handler に転送する。

#### 1b. `setup --component {ci,codeowners,ruleset}`

同様に `setup --component` を追加。`--component` ごとに必要な追加引数 (`--tier`、`--owner`、`--ai-ops-ref`) を受け付ける (合体 argparse)。旧 `setup-*` も alias として残す。

#### 1c. `worktree {new,cleanup}`

`worktree` parser に subparser を持たせる (`new` / `cleanup`)。それぞれ既存と同じ引数。旧 `worktree-new` / `worktree-cleanup` は alias で残す。

#### 1d. README claim verification の更新

`ai_ops/audit/lifecycle.py` の `README_CLAIMED_SUBCOMMANDS` を新コマンドに合わせる。旧 alias も含める (deprecation 期間中)。

### 2. docs/decisions/INDEX.md

12 ADR の 1 行 summary を Markdown 表で並べる。`docs/operation.md` から ADR 一覧 (現 11 行) を INDEX.md に link 1 行で置き換える。

### 3. docs/operation.md 圧縮

現状 275 行 → 130 行目標。具体策:
- 「目的別 sub-flow」表 (8 行) と「AI エージェントが従うワークフロー」(31 行) と「責任分界」表 (22 行) の重複を削る。
- 「5 つの戦略」section の各戦略を 1 段落に圧縮 (現 4-5 段落 → 1 段落)。
- ADR 一覧 11 行を `decisions/INDEX.md` への 1 行 link に置換。
- Markdown 表は「自動」「手動」の境界が分かれば足りるので、コメント / 補足を削る。

### 4. AI レビュー dogfood

`.github/workflows/ci.yml` に新 job `review`:
- `pull_request` イベントのみ
- `pip install .` で ai-ops を install
- `ai-ops review-pr --pr ${{ github.event.pull_request.number }} --provider auto`
- secrets: `ANTHROPIC_API_KEY` を inherit
- continue-on-error: true (Tier A 相当: AI レビュー結果は Comment のみ、status check は ruleset 対象外)

ANTHROPIC_API_KEY を ai-ops repo に登録する手順は `bootstrap --with-secrets` で実装 (次項)。本 PR 自身で key を登録するかは使用者承認後に判断。

### 5. cost monitor (review.py 内)

`ai_ops/review.py` を拡張:
- pricing 表を module 内に埋め込み (`PRICING_PER_MTOK` dict、Anthropic / OpenAI の主要 model)
- LLM API レスポンスから `usage.input_tokens` / `output_tokens` を取得
- cost を計算 (input + output tokens × 単価)
- `ReviewResult.body` の末尾に `--- ai-ops AI Review · model=... · input=... tok · output=... tok · cost=$...` を追記
- `run_review_pr` の stdout にも同情報を出力

### 6. bootstrap --with-secrets

`ai_ops/bootstrap.py` に flag を追加:
```sh
ai-ops bootstrap --tier 1 --with-secrets \
    --bitwarden-anthropic-item "Anthropic API Key" \
    --bitwarden-openai-item "OpenAI API Key" \
    --repo tekitounix/ai-ops
```

挙動:
- `BW_SESSION` 確認 (無ければ `bw unlock --raw` 手順を表示して exit)
- `bw get item "<name>"` で値取得
- 使用者確認 (Operation Model)
- `gh secret set <KEY> --body <value> --repo <repo>` で登録
- 各 provider について同様

### 7. テスト

- `tests/test_cli.py`: 新統合コマンドが動くこと、旧 alias が deprecation 警告と共に動くこと、`audit lifecycle` の README_CLAIMED_SUBCOMMANDS が新旧両方を verify すること。
- `tests/test_review.py`: cost 計算と Comment 末尾出力のテスト追加 (mock LLM レスポンスに usage を含めて検証)。
- `tests/test_bootstrap.py`: `--with-secrets` の Bitwarden 呼び出しと gh secret set の subprocess を mock。

## Concrete Steps

```sh
cd /Users/tekitou/ghq/github.com/tekitounix/ai-ops.streamline

# 1. subcommand 統合 (cli.py 大幅編集 + audit/lifecycle.py)
$EDITOR ai_ops/cli.py ai_ops/audit/lifecycle.py

# 2. ADR INDEX
$EDITOR docs/decisions/INDEX.md

# 3. operation.md 圧縮
$EDITOR docs/operation.md

# 4. dogfood
$EDITOR .github/workflows/ci.yml

# 5. cost monitor
$EDITOR ai_ops/review.py

# 6. bootstrap secrets
$EDITOR ai_ops/bootstrap.py

# 7. テスト
$EDITOR tests/test_cli.py tests/test_review.py tests/test_bootstrap.py
python -m pytest -v

# 8. 検証
python -m ai_ops check

# 9. PR
git add -A && git commit -m "refactor: streamline CLI + dogfood AI review + cost monitor"
git push -u origin refactor/streamline
gh pr create --title "..." --body "..."
```

## Validation and Acceptance

- subcommand 数: `ai-ops --help` で user-facing が 11 (旧 alias 7 + 統合 1 + その他 = 19、ただし旧 alias は help から hide できれば理想)
- `ai-ops --help` 出力が現状より短い (現 ~50 行 → 目標 ~30 行)
- `docs/operation.md` 行数 ≤ 145 (130 目標 + バッファ)
- `docs/decisions/INDEX.md` が存在し、12 ADR をリスト
- `python -m ai_ops audit lifecycle` exit 0
- `python -m ai_ops check` exit 0、pytest 全パス
- 既存テスト + 新規 (cost / bootstrap secrets / alias) が全 PASS
- `.github/workflows/ci.yml` に review job が存在 (`continue-on-error: true`)

## Idempotence and Recovery

- subcommand 統合は backward compat (alias 経由) なので revert 可能。
- 文書圧縮は破壊的でない (ADR INDEX で実情報は残る)。
- bootstrap --with-secrets は使用者承認必須なので暴走しない。
- cost monitor は output-only。

## Artifacts and Notes

- PR URL: TBD
- 本 PR マージで ai-ops 自身に AI レビュー dogfood が始まる (ANTHROPIC_API_KEY 登録は別作業)。

## Interfaces and Dependencies

- 統合後の user-facing subcommand: `new` / `migrate` / `bootstrap` / `update` / `audit` / `check` / `promote-plan` / `propagate` / `worktree` / `setup` / `report-drift` / `review-pr` = 12 個
- 旧 alias (1 リリース残す、deprecation 警告): `propagate-anchor` / `propagate-init` / `propagate-files` / `setup-ci-workflow` / `setup-codeowners` / `setup-ruleset` / `worktree-new` / `worktree-cleanup` = 8 個
- 新規依存 (optional): `bw` (Bitwarden CLI、`bootstrap --with-secrets` 使用時のみ)
- 既存依存: `gh`、Python 3.11+、Anthropic / OpenAI API
