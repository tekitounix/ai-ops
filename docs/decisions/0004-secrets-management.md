# ADR 0004: 秘匿情報を AI 文脈に入れない

> Status: Accepted
> Date: 2026-04-21

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

## Rationale

AI への漏洩は、値が context に入った瞬間に発生する。「モデルに繰り返さないよう頼む」より「読ませない」方が確実。

## Related

- ADR 0002: portability first
