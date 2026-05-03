# Backlog

`Improvement Candidates` で `deferred` 判定された候補と、横断的に「やる予定だがまだ着手していない」作業の退避場所。新 plan 起草時はここから pick する。

各 entry は出所 (どの plan / 監査 / 議論で出てきたか) を明記する。3 plan 連続で deferred のまま動かないものは再評価して降格 / 起票する (ADR 0008 §Improvement Capture loop の 3-deferred 閾値と一貫)。

## 運用ルール

1. **Backlog → active plan**: 新 plan 起草時、backlog から 1-3 candidate を pick して plan の Plan of Work に組み込む。pick した candidate は backlog から削除 (Cancelled に履歴を残したい場合は strikethrough)。
2. **Active plan → Backlog**: plan の `Improvement Candidates` で `deferred` と判定したものは、archive 前に backlog の適切な priority section に転記する。出所として plan slug を明記。
3. **3-deferred 閾値**: 同じ candidate が 3 plan 連続で deferred のまま動かなければ、High → Medium → Low → Cancelled の降格を検討する。
4. **Cancelled の不可逆性**: Cancelled は履歴。再評価で active に戻す場合は新 entry として High / Medium に追加し、Cancelled の strikethrough は残す。

## High (近 1-2 PR で着手したい)

- [ ] **AI レビュー request changes 時の override SOP** (出所: PR ε close-loops M1) — 誤検知時の対処手順 (override / 修正 / status check ignore) が docs に無い
- [ ] **`audit security` で `[review]` schema 整合性チェック** (出所: PR ζ selective-review) — `monthly_usd_limit < per_pr_usd_limit` のような矛盾を検出
- [ ] **モデル名期限切れ検知** (出所: PR ε close-loops M3) — Anthropic / OpenAI の model deprecation 通知を捕まえる仕組み

## Medium (落ち着いたら)

- [ ] **`setup ci` の Tier A 説明強化** (出所: PR ε close-loops M2) — `--tier A` で `--strict` を要求しない動作を help / docs に明記
- [ ] **`audit projects` の rate limit 配慮** (出所: PR ε close-loops M4) — 100 project × 3 gh API call で月間 limit を圧迫しうる
- [ ] **end-to-end 運用シナリオ test** (出所: PR ε close-loops M5) — `new` → `migrate` → `worktree new` → PR → review → merge → cleanup の通し test
- [ ] **model 選定を diff content / 規模ベースに拡張** (出所: PR ζ selective-review) — 現状は label のみ
- [ ] **workflow 変更時の E2E pass 必須化の仕組み** (出所: PR η e2e-fixes) — actionlint や unit test では捕まえられない reusable workflow load 制約を CI で確認

## Low (見直し材料、参考)

- [ ] **`project-relocation.md` 439 行を Recovery 切り出しで分離** (出所: docs 監査 M4) — clean migration だけのエージェントが半分のサイズで済む
- [ ] **`docs/operation.md` に `audit projects --json --priority` 注記** (出所: docs 監査 M2)
- [ ] **`direnv exec . sh -c '...'` 重複の helper 化** (出所: docs 監査 L5) — 7 ファイルでコピペ
- [ ] **conventional commits の audit 化** (出所: PR α 振り返り) — commit message format を `audit lifecycle` で確認
- [ ] **`Branch:` `Worktree:` フィールドを冒頭に書く規約の audit** (出所: PR α 振り返り) — plan.md 冒頭フォーマットの強制

## Cancelled / Deferred (履歴、理由付き)

- ~~**`ai-ops self-improve` 統合 subcommand**~~ — 削減方針と矛盾、複数 audit + agent review を強制連結する複雑度増。手動で個別 audit を呼ぶ運用で十分 (PR α 判断)
- ~~**`setup-managed --tier B` 一括 helper**~~ — `setup {ci,codeowners,ruleset}` の sub-subparser に統合する方が柔軟 (ADR 0011 amendment 経由で正式に rejected)
