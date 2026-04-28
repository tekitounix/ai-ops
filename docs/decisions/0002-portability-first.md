# ADR 0002: ポータビリティ優先

> Status: Accepted (Amended 2026-04-29)
> Date: 2026-04-20

## Decision

ai-ops は **silent installer ではない**。clone、pull、CLI 実行で user environment を勝手に変更しない。**ただし user の明示承認 (Operation model: Propose → Confirm → Execute) を経た install / update は許可される**。

silent (= 暗黙的) に変更してはいけないもの:

- shell rc ファイル (`~/.zshrc`、`~/.bashrc`、`~/.profile`) — 各 installer 自身が行う部分は OK、ai-ops 独自編集は禁止
- global `.gitconfig`
- `~/.config/*`
- AI tool の user-level config (`~/.claude/`、`~/.cursor/`、`~/.codex/` 等)
- OS scheduler / background agent 設定 (launchd、cron、systemd、Task Scheduler) — 自動配置禁止、user が手動で recipe を採用するのは OK
- hardcoded username / absolute user path

明示承認 (in-session prompt) を経れば許可:

- 必須 tool の install / update (`ai-ops bootstrap` / `ai-ops update` 経由)
- repo-local files の変更
- user が承認した一時的 operation
- `$HOME`、`<username>`、`git config --get ghq.user` 等の placeholder / dynamic lookup

## Rationale

運用方法を共有する repo が user machine を **silent に** 変更すると再現性と信頼性が壊れる。一方、ai-ops が依存する必須 tool (git / ghq / direnv / nix 等) が無いと user は ai-ops を運用できない。両立のため:

- silent change を禁止
- user 明示承認 (Operation model) 後の install / update を許可

## Amendment 2026-04-29

旧 Decision「ai-ops は installer ではない」は実質 silent change 禁止を意図していたが、文言が installer 全廃に読まれ運用支障 (= Nix 等必須 tool 入れられず install 詰まり) が出ていた。**user 承認付き install / update を明示的に許可** に書き換え。silent change 禁止は維持。

## Related

- ADR 0001: AGENTS.md primary
- ADR 0003: deletion policy
- ADR 0005: Nix optional reproducibility layer (本 ADR amendment と同時に default-required へ amend)
