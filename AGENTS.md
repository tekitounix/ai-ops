# AGENTS.md - ai-ops

This repo is the cross-project AI operations source of truth. Keep it small. If a detail is recoverable from Git history, code, or command output, do not duplicate it here.

## Workspace

- All Git repositories live under `~/ghq/`.
- Get the user name with `git config --get ghq.user`; never hardcode it.
- Own projects: `~/ghq/github.com/$(git config --get ghq.user)/<repo>/`.
- External projects: `~/ghq/<host>/<org>/<repo>/`.
- Scratch work: `~/scratch/`, not a Git repo.
- Do not create repos under Desktop, Documents, or ad-hoc work directories.
- Cross-repo references in committed docs use URLs (`https://github.com/<owner>/<repo>/...`). Use `~/ghq/...` only when explaining the local working layout; do not use local paths for committed references to other repositories.

## Lifecycle and CLI

Master operation guide: `docs/operation.md`. It documents the canonical lifecycle (`Intake -> Discovery -> Brief -> Proposal -> Confirm -> Agent Execute -> Verify -> Adopt`), the sub-flow selector (new project / migrate / realign / relocate / projects audit / self-operation / propagation), and a CLI quick reference grouped by intent.

User-facing entrypoint: `README.md`. The README's second Quick start prompt (`align this project`) decides between migrate / realign / relocate / no-op for a single working tree; the third (`audit my projects`) sweeps every ghq-tracked project and routes each P0 / P1 finding into the matching sub-flow with its own confirmation. Both prompts include `docs/projects-audit.md` and `docs/project-relocation.md` as their authoritative playbooks.

`ai-ops` is the Python CLI (installed console script, `python -m ai_ops`, or `nix run github:<owner>/ai-ops -- ...`). The full subcommand list with all flags lives in `docs/operation.md` (intent-grouped) and `ai-ops --help` (authoritative). Do not duplicate it here.

## Plans

Use `docs/plans/<slug>/plan.md` for non-trivial execution-time plans that need handoff, multi-session continuity, or cross-agent review. Start from `templates/plan.md`, keep `Progress` / `Surprises & Discoveries` / `Decision Log` / `Outcomes & Retrospective` / `Improvement Candidates` current, and archive completed plans under `docs/plans/archive/YYYY-MM-DD-<slug>/`. Do not store transient task state in `AGENTS.md`, and do not treat `~/.claude/plans/` or other user-local AI tool storage as canonical.

Improvement capture loop (作業中の学びを durable 化する手順) は `docs/self-operation.md` と `docs/ai-first-lifecycle.md` を参照。

## Cross-cutting CLI behavior

- `new` / `migrate` `--nix` flag: `auto` (default; AI decides via per-project rubric), `none` (justification required in brief), `devshell`, `apps`, `full`.
- Reproducibility tools (Tier 1 includes `nix`) are installed only with explicit user confirmation per Operation Model. ai-ops does not silently mutate `~/.zshrc`, package managers, or OS schedulers, but it does propose installs via `bootstrap` / `update`.
- When already running inside an AI agent, do not call another AI via `ai-ops --agent claude` or `ai-ops --agent codex`. Use docs directly, or use `--agent prompt-only` / `--dry-run` for prompt and discovery output only.

## Operation Model

Use Propose -> Confirm -> Execute for:

- destructive operations
- environment changes
- AI data substrate operations such as `~/.claude/projects/`
- visibility changes
- cross-cutting edits
- project-specific harness overwrite
- project physical relocation (e.g. `~/work/<repo>` → `~/ghq/<host>/<owner>/<repo>`) — see `docs/project-relocation.md`

One proposal requires one confirmation. Batch approval, meaning several distinct operations under a single y/N, is forbidden. Multiple steps inside a single operation may share one confirmation when they are presented together up front (e.g. `ai-ops bootstrap` showing the full list of missing tools before asking once to install them all). Read-only commands and local tests do not need confirmation.

## Safety

- Never commit `.env`, `*.key`, `*.pem`, credentials, customer data, or production secrets.
- Never push public visibility without explicit in-session confirmation.
- Never skip git hooks with `--no-verify` unless explicitly requested.
- Do not modify user environment files such as `~/.zshrc`, `~/.bashrc`, `~/.gitconfig`, `~/.config/*`, or OS scheduler files.
- Do not install launchd, cron, systemd, Task Scheduler, or background agents.
- Use `$HOME`, placeholders, or `git config --get ghq.user`; do not hardcode absolute user paths.
- Deleting tracked files is done as Git deletion, not by moving them into an in-repo archive.
- Prefer recovery-maximizing deletion: tracked file deletion via Git, then review with `git diff`; avoid `rm -rf`.

## Natural language

Default policy:

- Source code (identifiers / comments / tests), commit messages, branch / tag names, and LICENSE: English.
- The primary operating language is Japanese because the owner is a Japanese speaker.
- `README.md` is the only document that is English by default, because GitHub renders it as the public first entrypoint.
- `AGENTS.md`, docs, issues, PRs, briefs, and plans are Japanese by default unless the project brief records a different operating language.

For completed projects intended for public consumption, add English documentation according to public importance. Use the sibling pattern when needed: keep **`README.md` in English** and place localized versions such as `README.ja.md` beside it. Put a one-line language selector at the top of each localized README file.

Translate deeper docs / ADRs or add localized siblings incrementally when public users, contributors, release readiness, or support burden justify the extra maintenance cost. Do not translate internal working docs only for appearance.

## Multi-agent

When running multiple AI agents in the same repository, use each AI tool's native worktree support:

- Claude Code: `claude --worktree <name>` creates an isolated working tree under `.claude/worktrees/<name>/` and cleans it up on exit when no uncommitted changes remain.
- Codex: Codex App has built-in worktree support. For standalone Codex CLI, use `git worktree add ../<repo>.<branch> <branch>` for equivalent isolation.

The practical limit is 2-4 parallel agents. Beyond that, orchestration cost usually outweighs the benefit of parallelism. For large parallel work, create one integration branch and merge into `main` in stages. Avoid parallel edits to the same file; split file ownership by agent.

Every `ai-ops` command is worktree-compatible and treats the current working directory as the project root. You can run `ai-ops new` / `migrate` / `audit` / `check` directly from a worktree.

## Checks

Before reporting completion for this repo:

```sh
python -m ai_ops check
git diff --check
```

When Nix is available:

```sh
direnv exec . sh -c '
set -e
nix flake check --all-systems --no-build
nix build --no-link ".#checks.$(nix eval --impure --raw --expr builtins.currentSystem).all"
'
```

## See Also

- `README.md` - first entrypoint
- `docs/ai-first-lifecycle.md` - canonical workflow
- `docs/realignment.md` - drift correction prompt for already-running projects
- `docs/self-operation.md` - ai-ops dogfood / release gate
- `docs/decisions/` - load-bearing ADRs only
