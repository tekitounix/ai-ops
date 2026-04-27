# ai-ops

**English** | [日本語](README.ja.md)

AI-first project lifecycle system for creating, migrating, and operating projects with AI agents.

## Quick start

Hand any of these prompts directly to an AI agent.

New project (describe only what you want to do):

```text
Following github.com/tekitounix/ai-ops's README.md, AGENTS.md, and docs/ai-first-lifecycle.md, set up a new project AI-first to accomplish "<what you want>". Propose the project name, target path (`~/ghq/github.com/<owner>/<repo>/`), tier, stack, and check command, and proceed Propose -> Confirm -> Execute, confirming only the load-bearing decisions.
```

New project (name fixed up front):

```text
Following github.com/tekitounix/ai-ops's README.md, AGENTS.md, and docs/ai-first-lifecycle.md, create <project-name> AI-first for "<one-line-purpose>". Confirm only the load-bearing decisions and proceed Propose -> Confirm -> Execute.
```

Migrate an existing project:

```text
Following github.com/tekitounix/ai-ops's README.md, AGENTS.md, and docs/ai-first-lifecycle.md, migrate <source-path> AI-first. Start with read-only discovery, present the migration plan, then proceed Propose -> Confirm -> Execute.
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
