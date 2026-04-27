# ADR 0008: 秘匿情報を AI 文脈に入れない

> Status: Accepted
> Date: 2026-04-21

## Decision

AI agent に secret value、credential、customer data、production token を見せない。

Minimum controls:

- `.env`, `.env.*`, `*.key`, `*.pem`, `secrets/` are ignored unless explicitly encrypted examples.
- `.env.example` may contain placeholders or secret-manager references, never real values.
- Runtime injection uses a secret manager or environment variables.
- If a tool-specific deny list exists, treat it as defense in depth, not source of truth.

## Secret Tiers

| Tier | Examples | AI visibility |
|---|---|---|
| Critical | root keys, signing keys, production DB master | never |
| High | production API keys, OAuth client secrets | never |
| Medium | dev/staging keys, personal PAT | never |
| Low | dummy localhost values, public test keys | allowed when clearly dummy |

## Rationale

AI leakage risk starts when the value enters context. Preventing reads is more reliable than asking the model not to repeat secrets.

## Related

- ADR 0004: portability first
