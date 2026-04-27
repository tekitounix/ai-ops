# AGENTS.md — ai-ops

This repo is the cross-project AI operations source of truth. Keep it small. If a detail is recoverable from Git history, code, or command output, do not duplicate it here.

## Workspace

- All Git repositories live under `~/ghq/`.
- Get the user name with `git config --get ghq.user`; never hardcode it.
- Own projects: `~/ghq/github.com/$(git config --get ghq.user)/<repo>/`.
- External projects: `~/ghq/<host>/<org>/<repo>/`.
- Scratch work: `~/scratch/`, not a Git repo.
- Do not create repos under Desktop, Documents, or ad-hoc work directories.

## Lifecycle

Use `README.md` as the user-facing entrypoint.

```text
Intake -> Discovery -> Brief -> Proposal -> Confirm -> Agent Execute -> Verify -> Adopt
```

- New project brief: `templates/project-brief.md`.
- Migration brief: `templates/migration-brief.md`.
- Handoff brief: `templates/agent-handoff.md`.
- Canonical workflow: `docs/ai-first-lifecycle.md`.
- Detailed guide: `docs/project-addition-and-migration.md`.

`ai-ops` is the Python CLI: installed console script, `python -m ai_ops`, or `nix run github:<owner>/ai-ops -- ...`.

When already running inside an AI agent, do not call another AI via `ai-ops --agent claude` or `ai-ops --agent codex`. Use docs directly, or use `--agent prompt-only` / `--dry-run` for prompt and discovery output only.

## Operation Model

Use Propose -> Confirm -> Execute for:

- destructive operations
- environment changes
- AI data substrate operations such as `~/.claude/projects/`
- visibility changes
- cross-cutting edits
- project-specific harness overwrite

One proposal requires one confirmation. Batch approval is forbidden. Read-only commands and local tests do not need confirmation.

## Safety

- Never commit `.env`, `*.key`, `*.pem`, credentials, customer data, or production secrets.
- Never push public visibility without explicit in-session confirmation.
- Never skip git hooks with `--no-verify` unless explicitly requested.
- Do not modify user environment files such as `~/.zshrc`, `~/.bashrc`, `~/.gitconfig`, `~/.config/*`, or OS scheduler files.
- Do not install launchd, cron, systemd, Task Scheduler, or background agents.
- Use `$HOME`, placeholders, or `git config --get ghq.user`; do not hardcode absolute user paths.
- Deleting tracked files is done as Git deletion, not by moving them into an in-repo archive.
- Prefer recovery-maximizing deletion: tracked file deletion via Git, then review with `git diff`; avoid `rm -rf`.

## Multi-agent

複数 AI agent を同 repo で並行運用する場合、各 AI tool の native worktree support を使う:

- Claude Code: `claude --worktree <name>` で `.claude/worktrees/<name>/` に独立 working tree が作られ、退出時に未 commit 変更が無ければ自動 cleanup。
- Codex: Codex App は worktree built-in。Codex CLI 単独なら `git worktree add ../<repo>.<branch> <branch>` で同等。

実用上限は 2-4 並列。それを超えると orchestration コストが parallelism のメリットを上回る。大規模並行時は integration branch を 1 本立てて段階的に main に取り込む。同一ファイルへの並行 edit は避け、agent ごとに担当ファイルを分離する。

`ai-ops` の各コマンドは worktree compatible で、実行 cwd を root として扱う。worktree 内から `ai-ops new` / `migrate` / `audit` / `check` をそのまま使える。

## Checks

Before reporting completion for this repo:

```sh
python -m ai_ops check
git diff --check
```

When Nix is available:

```sh
direnv exec . nix flake check
```

## See Also

- `README.md` — first entrypoint
- `docs/ai-first-lifecycle.md` — canonical workflow
- `docs/decisions/` — load-bearing ADRs only
