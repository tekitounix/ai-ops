# ai-ops

**English** | [日本語](README.ja.md)

AI-first project lifecycle system for creating, migrating, and operating projects with AI agents.

## Quick start

Hand any of these to an AI agent. The agent reads the repo for the rest.

New project, describe what you want:

```text
Per github.com/tekitounix/ai-ops, set up a new project for "<what you want>".
```

New project with a fixed name:

```text
Per github.com/tekitounix/ai-ops, create <project-name> for "<one-line-purpose>".
```

Migrate an existing project:

```text
Per github.com/tekitounix/ai-ops, migrate <source-path>.
```

Or invoke the CLI directly:

```sh
nix run github:tekitounix/ai-ops -- new my-app --purpose "Markdown note app"
nix run github:tekitounix/ai-ops -- migrate "$HOME/ghq/github.com/user/project"
```

If you are already inside an AI agent, do not nest a second AI via `ai-ops --agent claude` or `--agent codex`. Use `--agent prompt-only` or `--dry-run` to get prompt / brief / discovery output only.

## Roles

```text
AI agent: project-specific judgment, proposals, post-approval execution
User: visibility, secret boundaries, long-term decisions
Python CLI: discovery, prompt assembly, agent invocation, check / audit
Nix: optional reproducibility layer
Git: history and recovery; in-repo archive is usually unnecessary
```

This repo is not an installer. It does not modify user shells, global git config, OS schedulers, or AI tool user configs.

## Layout

```text
README.md
AGENTS.md
CLAUDE.md
pyproject.toml
flake.nix
ai_ops/
tests/
docs/
  ai-first-lifecycle.md
  project-addition-and-migration.md
  decisions/
templates/
```

History, old plans, legacy scripts, and obsolete templates are not kept in the active tree. Refer to or restore them from Git history when needed.

## Verification

```sh
python -m ai_ops check
python -m ai_ops audit security
direnv exec . nix flake check
git diff --check
```

Nix is optional. `python -m ai_ops check` must work in environments without Nix.
