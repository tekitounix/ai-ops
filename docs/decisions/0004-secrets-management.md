# ADR 0004: 秘匿情報を AI 文脈に入れない

> Status: Accepted
> Date: 2026-04-21
> Amended: 2026-05-03 (PR β: 「絶対やらないリスト」追加、audit security で機械強制)

## Decision

AI agent に secret value、credential、customer data、production token を見せない。

最低限のコントロール:

- `.env`、`.env.*`、`*.key`、`*.pem`、`secrets/` は明示的な暗号化例外を除き ignore する。
- `.env.example` には placeholder か secret manager への参照だけを書き、実値は書かない。
- runtime 注入は secret manager または環境変数で行う。
- tool-specific な deny list は defense in depth であり、source of truth ではない。

## Secret Tiers

| Tier | 例 | AI visibility |
|---|---|---|
| Critical | root key、signing key、本番 DB master | never |
| High | 本番 API key、OAuth client secret | never |
| Medium | dev/staging key、personal PAT | never |
| Low | localhost dummy 値、public test key | dummy が明らかな場合のみ allow |

## Absolutely-do-not-do リスト (PR β amendment)

PR α マージ後の運用テストで API key の不適切な扱いが 5 件発覚した。再発防止として以下を明文化する。違反は `audit security` の `SECRET_ARG_FORBIDDEN_PATTERNS` で機械検出する。

1. **secret 値を CLI 引数で渡さない** — `gh secret set --body <value>`、`curl -H "Authorization: Bearer <token>"`、`mysql -p<password>` 等は process list (`ps auxww`) に値が瞬間的に出る。stdin (`--body-file -`、`--password-stdin`) または環境変数で渡す。
2. **secret 値を `print` / `echo` / `log` に出さない** — stdout / stderr / log file に値が残る。secret を扱う関数は戻り値を呼び出し側に返し、内部で消費させる。
3. **secret 値を含む生 output を直接表示しない** — `bw list items`、`gh secret list --show-values` 等は、必要なフィールドだけ pipe (`jq -r '.login.password'`) で抽出する。生 JSON / 全行表示は禁止。
4. **session token / API key 値をチャット / commit / PR description / コメントに貼らない** — Claude / Codex 等の AI tool を経由するチャット履歴は外部サーバに保存される可能性がある。値はローカル shell 内で完結させ、AI には「item 名」「環境変数名」までしか伝えない。
5. **AI エージェントが使用者の Confirm を `echo y` で bypass しない** — AGENTS.md §Operation Model の Propose → Confirm → Execute は使用者本人の能動的承認を要求する。bypass が必要なら正規 flag (`--yes`) を新設し、使用者がそれを明示的に渡す。

## AI エージェントの secret 扱い 5 原則

`docs/operation.md` の AI エージェントワークフローでも参照されるが、ここに source of truth として置く。

1. secret 値が含まれる可能性がある外部コマンド (`bw`, `gh secret`, `op`, `vault` 等) の output は **subprocess 内で消費** し、stdout / chat に流さない。
2. session token / API key 値が必要な場合は、使用者に shell 内での実行手順 (例: `export BW_SESSION=$(bw unlock --raw)`) を提示し、**値そのものをチャットで受け取らない**。
3. 使用者の Confirm を `echo y` で bypass せず、`--yes` 等の正規 flag を要求する。
4. secret 関連の操作後は「rotation 推奨かどうか」の判断基準を明示する (露出の有無、threat model、共有 host か個人機か)。
5. 不正確な報告 (「unset した」「クリアした」など) を避け、消えた範囲 (shell var など) と残る範囲 (チャット context、log file など) を分けて伝える。

## Rationale

AI への漏洩は、値が context に入った瞬間に発生する。「モデルに繰り返さないよう頼む」より「読ませない」方が確実。

加えて、人間 / AI を問わず secret を扱うときの工程 (CLI 引数、log、チャット、tempfile) はすべて漏洩経路になりうる。「規律で防ぐ」のではなく「技術的に不可能にする」「監査で機械検出する」の 2 段で守る。

## Enforcement

- `audit security` の `SECRET_ARG_FORBIDDEN_PATTERNS` が `ai_ops/` 配下を grep で scan し、`--body`/`--password`/`--token` の引数渡しを FAIL として検出する。
- `bootstrap --with-secrets` の `_gh_secret_set` は `--body-file -` + stdin 経由で実装。
- 違反は `ai-ops check` で CI が落ちるので merge 不可能。

## Related

- ADR 0002: portability first
- ADR 0010 §Lifecycle 4: マージ後手順 (Tier 別 archive)
- ADR 0012: PR 自動レビュー (二層構成)
