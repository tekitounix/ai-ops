# ADR 0014: Nix は optional な再現性 layer

> Status: Accepted
> Date: 2026-04-27

## Decision

Nix を optional but first-class な operations layer として使う。必須入口は Python CLI の `ai-ops check`。

```text
Python CLI: Nix なしで動く
flake.nix: devShell / apps / checks を宣言
flake.lock: Nix dependency universe を固定
```

## Rules

- ai-ops は Nix をインストールしない。
- `nix.conf`、nix-darwin、Home Manager、direnv user config を自動変更しない。
- `flake.lock` 更新は明示的 dependency update として扱う。
- secret 値を Nix store に入れない。
- destructive / hardware operations は `nix flake check` に入れない。

## Verification

```sh
python -m ai_ops check
direnv exec . nix flake check
```

## Related

- ADR 0004: portability first
- ADR 0016: Python canonical CLI
