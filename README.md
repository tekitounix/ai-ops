# ai-ops

[![CI](https://github.com/tekitounix/ai-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/tekitounix/ai-ops/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**English** | [日本語](README.ja.md)

ai-ops lets AI coding agents (Claude Code, Codex, Cursor, …) decide how to set up, migrate, and audit your projects — instead of running fixed templates. You describe your intent; the agent reads context, drafts a structured plan, you confirm, the agent executes with normal tools.

## Quick start

Hand one of these prompts to an AI agent. The agent reads this repo for the rest.

```text
Per github.com/tekitounix/ai-ops, set up a new project for "<purpose>".
```
**Greenfield work.** The agent drafts a target shape (name, repo location under `~/ghq/...`, stack, check command), proposes it, and only creates files after your confirmation.

```text
Per github.com/tekitounix/ai-ops, align this project.
```
**A single working tree.** The agent inspects the cwd read-only and decides which sub-flow applies — *migrate* (not yet ai-ops-managed), *realign* (managed but drifted), *relocate* (path is outside `~/ghq/...`), or *no action needed* — then asks per scope before editing anything.

```text
Per github.com/tekitounix/ai-ops, audit my projects.
```
**Every ghq-tracked project at once.** The agent walks `ghq list -p`, scores each project on eight signals, and emits a priority-sorted list. Action stays per-project: each P0 / P1 finding routes into the matching sub-flow with its own confirmation. P2 rows are observation only. Full procedure: [`docs/projects-audit.md`](docs/projects-audit.md).

If you are already inside an AI session, do not nest a second AI via `--agent claude` / `--agent codex`. Use `--agent prompt-only` or `--dry-run` to print the prompt without invoking another agent.

## How does ai-ops work?

The full operation guide — lifecycle phases, sub-flow selection, **5 strategies (Git / ghq / GitHub / Nix / plan) with an automated-vs-manual responsibility matrix**, workflow tiers, worktree-based parallel work, GitHub-native ecosystem, plan-driven execution, improvement capture loop, and intent-grouped CLI reference — lives at **[`docs/operation.md`](docs/operation.md)**. Read that one document to understand how the system fits together; it links to deep-dives in `docs/` and to the architectural decisions in `docs/decisions/`.

In one sentence: AI agents read context, draft a Brief, you confirm, and they execute via normal git/gh tooling — with tier-aware policies, sibling git worktrees, and GitHub Issues + scheduled Actions carrying drift signals and propagation PRs to your existing notification channels.

## Install

```sh
# Nix
nix run github:tekitounix/ai-ops -- --help

# pip (editable from a clone)
git clone https://github.com/tekitounix/ai-ops
cd ai-ops && pip install -e .

# from source, no install
git clone https://github.com/tekitounix/ai-ops
cd ai-ops && python -m ai_ops --help
```

Requires Python 3.11+. No runtime dependencies (stdlib only).

## What an "ai-ops project" looks like

ai-ops doesn't ship a fixed template, but the prompts above expect a small set of conventions so they can reason consistently:

- **Live under `~/ghq/<host>/<owner>/<repo>/`** (`ghq` for repo placement). That's where `audit my projects` looks.
- **`AGENTS.md` at the project root** — the agent's operating contract: what to do, what not to do, what counts as "done". The Quick start prompts read this repo's `AGENTS.md` as the cross-project source of truth.
- **`flake.nix` for projects with a stack** (Node / Python / Rust / Go / xmake / DSL). Reproducible dev env via Nix. Docs-only projects opt out via the per-project rubric (see `docs/decisions/0005-...`).
- **`.ai-ops/harness.toml`** (optional manifest the audit uses to detect drift between this repo's spec and your project). Seed it with `ai-ops migrate <path> --update-harness`; without it, the audit shows the project as "unmanaged".

## CLI

| Command | Purpose |
|---|---|
| `ai-ops new <name> --purpose "..."` | Build prompt + draft plan for a new project |
| `ai-ops migrate <path>` | Read-only discovery + plan for migrating an existing project |
| `ai-ops migrate <path> --retrofit-nix` | Narrow scope: add `flake.nix` + `.envrc` only |
| `ai-ops migrate <path> --update-harness` | Narrow scope: refresh `.ai-ops/harness.toml` |
| `ai-ops audit projects [--json] [--priority {P0,P1,P2,all}]` | Score every ghq-tracked project on 8 signals; priority-sorted table or JSON. Exit 1 on any P0/P1 — usable from cron / CI |
| `ai-ops audit nix [--report] [--propose <path>]` | Per-project Nix audit; `--report` walks every project; `--propose` emits a Markdown retrofit plan |
| `ai-ops audit harness [--path PATH] [--strict]` | Detect drift between `.ai-ops/harness.toml` and actual file hashes |
| `ai-ops audit standard --since REF` | Detect ADR (`docs/decisions/`) changes since a reference, for propagation |
| `ai-ops audit security` | Secret scan (works in any repo) |
| `ai-ops audit lifecycle` | Self-audit for ai-ops itself |
| `ai-ops check` | All audits + pytest |
| `ai-ops bootstrap [--tier {1,2}]` | Install missing required tools after confirmation. Default `--tier 1` (required); `--tier 2` adds recommended |
| `ai-ops update [--tier {1,2}]` | Update present tools after confirmation. Default `--tier 2` |
| `ai-ops promote-plan <slug> [--source PATH]` | Promote a local AI plan into `docs/plans/<slug>/plan.md` after confirmation |
| `ai-ops propagate-anchor (--all \| --project PATH) [--dry-run]` | Open PRs to bump `ai_ops_sha` in managed projects whose only drift is the anchor |
| `ai-ops propagate-init (--all \| --project PATH) [--dry-run]` | Open PRs to commit `.ai-ops/harness.toml` from local working copy where the manifest exists on disk but is untracked |
| `ai-ops propagate-files (--all \| --project PATH) [--dry-run]` | Open PRs to refresh `[harness_files]` hashes in `.ai-ops/harness.toml` so they match actual file content on the default branch (no file content is modified) |
| `ai-ops worktree-new <slug> [--type TYPE]` | Create sibling worktree + branch + plan skeleton (ADR 0010); 1:1:1 binding between slug, branch, worktree |
| `ai-ops worktree-cleanup [--auto]` | Remove worktrees whose branch's PR is merged AND plan is archived |
| `ai-ops report-drift [--repo OWNER/NAME]` | Translate `audit projects --json` output into ai-ops-repo Issues / sub-issues for the Ecosystem dashboard (ADR 0011) |
| `ai-ops setup-ci-workflow --project PATH [--tier T]` | PR adding `.github/workflows/ai-ops.yml` (drift gate) to a managed project |
| `ai-ops setup-codeowners --project PATH [--owner USER]` | PR adding `.github/CODEOWNERS` routing ai-ops changes to project owner |
| `ai-ops setup-ruleset --project PATH --tier {A,B,C}` | Apply Repository Ruleset (PR + status checks per tier) via `gh api` |

`new` / `migrate` flags: `--agent {claude,codex,prompt-only,...}`, `--tier {T1,T2,T3}` (T1 public / T2 private / T3 local), `--nix {auto,none,devshell,apps,full}` (default `auto`: AI decides via per-project rubric), `--output <path>`, `--dry-run`, `--interactive`.

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

`--agent <name>` overrides config. Built-in defaults work without any config file.

## Verification

```sh
python -m ai_ops check                # everything
python -m ai_ops audit security       # secret scan only
direnv exec . sh -c '
set -e
nix flake check --all-systems --no-build
nix build --no-link ".#checks.$(nix eval --impure --raw --expr builtins.currentSystem).all"
'
```

Nix is the **default-required** project-level reproducibility layer (per-project rubric, ADR 0005). `python -m ai_ops check` works without Nix as a bootstrap fallback, but stack-bearing projects fail `audit nix` until `flake.nix` is in place or an explicit opt-out justification is recorded in the project's brief.

## Layout

```text
README.md  AGENTS.md  CLAUDE.md
pyproject.toml  flake.nix
ai_ops/        Python CLI source
tests/         pytest
docs/
  ai-first-lifecycle.md       canonical workflow (Intake → Discovery → Brief → Confirm → Execute → Verify → Adopt)
  project-addition-and-migration.md
  realignment.md              correcting an existing project that has drifted
  project-relocation.md       moving from outside `~/ghq/` into `~/ghq/`
  projects-audit.md           the "audit my projects" playbook
  self-operation.md           how ai-ops dogfoods itself
  decisions/                  ADRs 0001-0008
  plans/                      active execution plans + archive
templates/                    project / migration / handoff / execution-plan templates
```

## License

[MIT](LICENSE).
