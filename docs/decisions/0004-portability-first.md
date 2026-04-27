# ADR 0004: ポータビリティ優先

> Status: Accepted
> Date: 2026-04-20

## Decision

ai-ops は installer ではない。clone、pull、CLI 実行の副作用として user environment を変更しない。

禁止:

- `~/.zshrc`、`~/.bashrc`、`~/.profile`
- global `.gitconfig`
- `~/.config/*`
- `~/.claude/*`、`~/.cursor/*`、`~/.codex/*`
- OS scheduler / background agent 設定
- hardcoded username / absolute user path

許可:

- repo-local files
- user が明示承認した in-session operation
- `$HOME`、`<username>`、`git config --get ghq.user` などの placeholder / dynamic lookup

## Rationale

運用方法を共有する repo が user machine を勝手に変更すると、再現性と信頼性が壊れる。ai-ops は方法論と repo-local tooling を提供し、採用は user が明示的に行う。

## Related

- ADR 0001: AGENTS.md primary
- ADR 0007: deletion policy
- ADR 0014: Nix optional layer
