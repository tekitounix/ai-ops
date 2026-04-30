# ai-ops

[![CI](https://github.com/tekitounix/ai-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/tekitounix/ai-ops/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**English** | [日本語](README.ja.md)

A small Python CLI that lets AI coding agents (Claude Code, Codex, Cursor, ...) propose project setup decisions instead of using fixed templates. You describe your intent; the agent observes, drafts a structured Brief, you confirm, the agent executes.

## Why

Templates like cookiecutter / copier / yeoman freeze decisions before a project is born — name, layout, stack are all chosen up front and copy-pasted. The right shape depends on the project, and AI agents can reason about it. ai-ops gives them the framework: read context, draft a Brief (Fact / Inference / Risk / User decision / AI recommendation), wait for human confirmation, then execute with normal tools.

## Quick start

Hand any of these to an AI agent. The agent reads the repo for the rest.

```text
Per github.com/tekitounix/ai-ops, set up a new project for "<what you want>".
```

```text
Per github.com/tekitounix/ai-ops, create <project-name> for "<one-line-purpose>".
```

```text
Per github.com/tekitounix/ai-ops, migrate <source-path>.
```

```text
Per github.com/tekitounix/ai-ops, realign this project.
```

The agent reads this repo, discovers your environment (`git config --get ghq.user`, OS, ...), drafts an 11-section Brief, proposes a target shape (name, repo placement under `~/ghq/...`, tier, stack, check command), waits for your confirmation, and only then creates / migrates files. The realignment prompt is for projects that already exist but have drifted from their operational ideal — the agent inspects the project read-only, emits a Realignment Brief grouped by reversibility (P0 doc-only / P1 structural / P2 behavioral), and waits for per-scope confirmation before editing.

If you are already inside an AI session, do not nest a second AI via `--agent claude` / `--agent codex`. Use `--agent prompt-only` or `--dry-run` to get prompt / brief / discovery output only.

## Install

```sh
# Nix (no install required)
nix run github:tekitounix/ai-ops -- --help

# pip (editable install from clone)
git clone https://github.com/tekitounix/ai-ops
cd ai-ops && pip install -e .

# from source without install
git clone https://github.com/tekitounix/ai-ops
cd ai-ops && python -m ai_ops --help
```

Requires Python 3.11+. Zero runtime dependencies (stdlib only).

## Commands

| Command | Purpose |
|---|---|
| `ai-ops new <name> --purpose "..."` | Assemble prompt + Brief draft for a new project |
| `ai-ops migrate <path>` | Read-only discovery + Brief for migrating an existing project |
| `ai-ops migrate <path> --retrofit-nix` | Narrow scope: add `flake.nix` + `.envrc` to an existing managed project |
| `ai-ops bootstrap [--tier {1,2}]` | Survey required tools (git, ghq, direnv, jq, gh, nix; +shellcheck/actionlint/gitleaks/fzf/rg) and install missing ones with user confirmation. Default `--tier 1` (required only) |
| `ai-ops update [--tier {1,2}]` | Survey present tools and update them with user confirmation. Default `--tier 2` (required + recommended) |
| `ai-ops audit {lifecycle,nix,security,harness,standard}` | Self-audit (`lifecycle` is for ai-ops itself; `security` works in any repo) |
| `ai-ops audit nix --report` | Walk `ghq list -p` and print a fleet table of Nix gaps |
| `ai-ops audit nix --propose <path>` | Emit a Markdown retrofit proposal for one project |
| `ai-ops audit harness [--path PATH]` | Detect harness drift (`.ai-ops/harness.toml` vs actual file hashes) |
| `ai-ops audit standard --since REF` | Detect ADR (docs/decisions/) changes since a reference for propagation |
| `ai-ops check` | All audits + pytest |
| `ai-ops promote-plan <slug> [--source PATH]` | Promote a user-selected local AI plan into `docs/plans/<slug>/plan.md` after confirmation |

Each command reads `templates/` from this repo, embeds `AGENTS.md` as the operating rules, and either prints the prompt or invokes a configured AI agent.

`new` / `migrate` flags: `--agent {claude,codex,prompt-only,...}`, `--tier {T1,T2,T3}`, `--nix {auto,none,devshell,apps,full}` (default `auto` = AI agent decides via per-project rubric, ADR 0005), `--output <path>`, `--dry-run`, `--interactive`. `migrate` also supports `--retrofit-nix` (Nix-only narrow scope) and `--update-harness` (harness drift remediation, Phase 8-B).

## Configuration

`~/.config/ai-ops/config.toml` (user) or `./ai-ops.toml` (repo):

```toml
[agent]
default = "claude"

[agents.claude]
command = ["claude", "-p", "--no-session-persistence", "--tools", ""]

[agents.codex]
command = ["codex", "exec", "-m", "gpt-5.2", "--sandbox", "read-only", "-"]
```

CLI flag `--agent <name>` overrides config. Built-in defaults work without any config file.

## Roles

```text
AI agent: project-specific judgment, proposals, post-approval execution
User: visibility, secret boundaries, long-term decisions
Python CLI: discovery, prompt assembly, agent invocation, check / audit, tool bootstrap
Nix: default-required reproducibility layer (stack-aware, per-project rubric, ADR 0005 amended)
Git: history and recovery; in-repo archive is usually unnecessary
```

This repo is not a *silent* installer. It does not modify user shells, global git config, OS schedulers, or AI tool user configs without confirmation. `ai-ops bootstrap` / `ai-ops update` install or upgrade required tools only after explicit user approval (Operation Model: Propose → Confirm → Execute).

## Concepts

- **Lifecycle (8-step)**: Intake → Discovery → Brief → Proposal → Confirm → Agent Execute → Verify → Adopt. See [docs/ai-first-lifecycle.md](docs/ai-first-lifecycle.md).
- **Brief**: 11-section structured proposal the AI fills before execution. See [templates/](templates/).
- **Execution plan**: optional living plan for non-trivial execution work under `docs/plans/<slug>/plan.md`, using [templates/plan.md](templates/plan.md).
- **Self-operation**: how ai-ops dogfoods its own lifecycle, release gate, file hygiene, and drift review. See [docs/self-operation.md](docs/self-operation.md).
- **Realignment**: how an already-running project that has drifted from its operational ideal is brought back. Read-only Discovery -> Realignment Brief -> per-scope Execute on confirmation. See [docs/realignment.md](docs/realignment.md).
- **Tier**: T1 public / T2 private / T3 local / OFF (PII). See [docs/project-addition-and-migration.md](docs/project-addition-and-migration.md).
- **Operation Model**: Propose → Confirm → Execute for destructive or cross-cutting changes. Defined in [AGENTS.md](AGENTS.md).
- **Multi-agent**: parallel sessions use `claude --worktree` or Codex's built-in worktree. See AGENTS.md "Multi-agent".

## Layout

```text
README.md  AGENTS.md  CLAUDE.md
pyproject.toml  flake.nix
ai_ops/        Python CLI source
tests/         pytest
docs/
  ai-first-lifecycle.md
  project-addition-and-migration.md
  realignment.md
  self-operation.md
  decisions/   ADR 0001-0008
  plans/       active execution plans + archive
templates/     project-brief / migration-brief / agent-handoff / plan
```

Old pre-Phase-9 plans, legacy scripts, and obsolete templates are not in the active tree. Refer to or restore them from Git history when needed.

## Verification

```sh
python -m ai_ops check                # all-in-one
python -m ai_ops audit security       # secret scan only
direnv exec . sh -c '
set -e
nix flake check --all-systems --no-build
nix build --no-link ".#checks.$(nix eval --impure --raw --expr builtins.currentSystem).all"
'
```

Nix is **default-required** as the project-level reproducibility layer (per-project rubric, ADR 0005 amended). `python -m ai_ops check` runs without Nix as a bootstrap fallback, but stack-bearing projects (Node / Python / Rust / Go / xmake / DSL) fail `ai-ops audit nix` until a `flake.nix` is in place or an explicit opt-out justification is recorded in the brief.

## License

[MIT](LICENSE).
