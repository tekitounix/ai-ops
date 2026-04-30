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
- Realignment (already-running, drifted projects): `docs/realignment.md`.
- Project physical relocation (`~/work/...` → `~/ghq/...`): `docs/project-relocation.md`.
- Fleet audit (all ghq-tracked projects at once): `docs/fleet-audit.md`.
- Self-operation: `docs/self-operation.md`.

The README's second Quick start prompt (`align this project`) is one entry point: read the cwd, decide between migrate / realign / relocate / no-op, then follow the doc that matches the chosen sub-flow. The third prompt (`audit my fleet`) is the fleet-wide variant: walk `ghq list -p`, score each project, route every P0 / P1 finding into the matching single-project sub-flow with its own confirmation.

## Plans

Use `docs/plans/<slug>/plan.md` for non-trivial execution-time plans that need handoff, multi-session continuity, or cross-agent review. Start from `templates/plan.md`, keep `Progress` / `Surprises & Discoveries` / `Decision Log` / `Outcomes & Retrospective` current, and archive completed plans under `docs/plans/archive/YYYY-MM-DD-<slug>/`. Do not store transient task state in `AGENTS.md`, and do not treat `~/.claude/plans/` or other user-local AI tool storage as canonical.

`ai-ops` is the Python CLI: installed console script, `python -m ai_ops`, or `nix run github:<owner>/ai-ops -- ...`.

Subcommands:

- `ai-ops new <name> --purpose "..."` - assemble prompt + Brief draft for a new project.
- `ai-ops migrate <path>` - read-only discovery + Brief for migrating an existing project.
- `ai-ops migrate <path> --retrofit-nix` - narrow scope: add `flake.nix` + `.envrc` to an already-managed project.
- `ai-ops bootstrap` - survey required tools (git / ghq / direnv / jq / gh / nix at tier 1; shellcheck / actionlint / gitleaks / fzf / rg at tier 2) and install missing ones with user confirmation (Operation Model). `--tier` defaults to 1 (required only); pass `--tier 2` to also install recommended tools.
- `ai-ops update` - survey present tools and update them with user confirmation. `--tier` defaults to 2 (required + recommended).
- `ai-ops audit lifecycle` - self-audit for ai-ops itself (incl. Phase 8-D forbidden-pattern grep + README claim verification + Phase 9 plan hygiene warnings + optional OpenSSF Scorecard).
- `ai-ops audit nix` - current cwd Nix audit (Stage A/B/C rubric per ADR 0005).
- `ai-ops audit nix --report` - walk `ghq list -p` and print fleet-wide Nix gap table.
- `ai-ops audit nix --propose <path>` - emit Markdown retrofit proposal for one project.
- `ai-ops audit harness [--path PATH] [--strict]` - detect harness drift (Phase 8-B, L3): missing / modified / extra harness files vs `.ai-ops/harness.toml`. Default returns 0 with a WARN when manifest is absent but harness files exist (fleet visibility); `--strict` flips that to FAIL.
- `ai-ops audit standard --since REF [--path PATH]` - detect ADR (docs/decisions/) changes since a reference (Phase 8-C, L4).
- `ai-ops audit fleet [--json] [--priority {P0,P1,P2,all}]` - walk `ghq list -p`, score each project on 8 signals, emit priority-sorted table (or JSON). Exit 1 when any P0/P1 remains; backs the `audit my fleet` Quick start prompt and is safe to run from cron / CI.
- `ai-ops audit security` - secret scan (works in any cwd).
- `ai-ops check` - all audits + pytest.
- `ai-ops promote-plan <slug> [--source PATH] [--dry-run]` - read a user-selected local AI plan and propose a repo-local `docs/plans/<slug>/plan.md`; writing requires explicit confirmation.

`migrate` flags include `--retrofit-nix` (Nix-only) and `--update-harness` (harness drift remediation, AI agent narrows scope to file restoration / hash refresh).

`new` / `migrate` `--nix` flag: `auto` (default; AI decides via per-project rubric), `none` (justification required in brief), `devshell`, `apps`, `full`.

Reproducibility tools (Tier 1 includes `nix`) are installed only with explicit user confirmation per Operation Model. ai-ops does not silently mutate `~/.zshrc`, package managers, or OS schedulers, but it does propose installs via `bootstrap` / `update`.

When already running inside an AI agent, do not call another AI via `ai-ops --agent claude` or `ai-ops --agent codex`. Use docs directly, or use `--agent prompt-only` / `--dry-run` for prompt and discovery output only.

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
- README / AGENTS.md / docs, issues, and PRs: English by default. If a project chooses Japanese as the primary language, record that choice in its project-specific brief.

For a T1 public repository, use the industry-standard sibling pattern: keep **`README.md` in English** and place localized versions such as `README.ja.md` beside it. GitHub auto-renders only `README.md` on the project page, so the first entrypoint must be English to avoid excluding international contributors. Put a one-line language selector at the top of each README file.

Working docs may use Japanese when that is the lowest-cost operating language, while the public surface, especially the primary README, stays English. `AGENTS.md` should stay English. Translate docs / ADRs or add localized siblings incrementally when there is clear demand.

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
