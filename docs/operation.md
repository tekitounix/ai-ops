# ai-ops Operation Guide

This is the master entry point for understanding how ai-ops operates. Read this first; follow the deep-dive links for details.

## What ai-ops does, in one paragraph

ai-ops gives AI coding agents (Claude Code, Codex, Cursor, …) a shared, repo-committed playbook for setting up, migrating, auditing, and propagating changes across software projects. Each project has tier-appropriate git workflow norms (ADR 0009), parallel work happens in sibling git worktrees bound 1:1:1 to plans (ADR 0010), and improvements to ai-ops itself reach managed projects through GitHub-native PRs and Issues (ADR 0011) — with the user's GitHub Notifications as the central notification channel.

## The lifecycle

Every non-trivial work item runs through:

```text
Intake → Discovery → Brief → Proposal → Confirm → Agent Execute → Verify → Adopt
```

The agent reads context (Discovery), drafts a Brief with project-specific judgment, the user confirms, and only then are files modified with normal tools. Detailed phases and the Fact / Inference / Risk classification: [`docs/ai-first-lifecycle.md`](ai-first-lifecycle.md).

## Sub-flows: pick by intent

| You want to … | Use this sub-flow | Doc |
|---|---|---|
| Start a new project | `ai-ops new` → Brief → execute | [`ai-first-lifecycle.md`](ai-first-lifecycle.md) |
| Bring an existing project under ai-ops | `ai-ops migrate <path>` → Brief → execute | [`project-addition-and-migration.md`](project-addition-and-migration.md) |
| Fix drift in a managed project | `align this project` prompt → Brief → execute | [`realignment.md`](realignment.md) |
| Move a repo into `~/ghq/...` | Phase-1 read-only Discovery → relocation Brief → execute | [`project-relocation.md`](project-relocation.md) |
| Survey every ghq-tracked project | `audit my projects` prompt → priority-sorted table → per-project sub-flow | [`projects-audit.md`](projects-audit.md) |
| Push ai-ops improvements to managed projects | `propagate-anchor` / `propagate-init` / `propagate-files` → PRs to each project | (commands; see Quick reference below) |
| Run ai-ops on its own work | self-check + plans + ADRs | [`self-operation.md`](self-operation.md) |

Each sub-flow follows the same Lifecycle (Discovery → Brief → Confirm → Execute), the difference is scope and entry conditions.

## Workflow tiers (ADR 0009)

Each managed project declares one of 4 tiers in its `.ai-ops/harness.toml::workflow_tier`. Tier sets the expected git workflow; ai-ops audits but never enforces.

- **Tier A — Lightweight**: trunk-based, direct push to main allowed, CI required green. ai-ops itself, knx3-style personal tools.
- **Tier B — Managed**: feature branch + PR required, branch protection. mi_share, audio-dsp-docs.
- **Tier C — Production / Public**: above + reviewer approval + signed commits + merge queue.
- **Tier D — Spike / Research**: anything goes (long-lived branches accepted). umipal phase-a, fx-llm-research.

Missing field defaults to D (most permissive). Audit signal `tier_violations` flags when actual practice deviates from declared tier. Full definition + detection rules: [ADR 0009](decisions/0009-git-workflow-tiers.md).

## Worktree-based parallel work (ADR 0010)

For non-trivial work (multiple commits, parallel streams, anything warranting a plan):

- One **plan** at `docs/plans/<slug>/plan.md`
- One **branch** named `<type>/<slug>` (`feat`/`fix`/`chore`/`docs`/`refactor`)
- One **worktree** at `<repo-parent>/<repo-name>.<slug>/` (sibling layout)

`ai-ops worktree-new <slug>` creates all three with a seeded plan from the canonical template. `ai-ops worktree-cleanup` removes worktrees whose branch's PR is merged AND plan is archived (both signals required for safety). Practical limit is 3–5 worktrees per repo. Full convention: [ADR 0010](decisions/0010-worktree-workflow.md).

## GitHub-native ecosystem operation (ADR 0011)

ai-ops's primary user-facing surface is **GitHub Issues + sub-issues + Projects v2 board + scheduled Actions + Repository Rulesets + CODEOWNERS** — not local CLI invocations. The user's existing GitHub Notifications carry drift status and propagation work.

Three layers:

1. **ai-ops repo runs scheduled workflows** (`.github/workflows/ecosystem-watch.yml`, `propagate-cron.yml`):
   - Weekly cron audits managed projects → opens / updates / closes sub-issues on the central "Ecosystem" parent issue
   - Weekly cron runs `propagate-* --auto-yes` → opens PRs in each managed project
2. **Each managed project hosts a thin caller workflow** (`.github/workflows/ai-ops.yml`, opt-in via `ai-ops setup-ci-workflow`) that calls ai-ops's reusable `managed-project-check.yml` to run `audit harness --strict` on PR + schedule. Tier B+ rulesets make this a required status check.
3. **CODEOWNERS routes ai-ops-related changes to the project owner** (`ai-ops setup-codeowners`). Tier rulesets enforce per-tier policy (`ai-ops setup-ruleset --tier {A,B,C}`).

Drift detection runs locally by default and via scheduled GitHub Actions; either way, the result lands as Issues / sub-issues / PRs in standard GitHub UI. Full design + setup workflow: [ADR 0011](decisions/0011-github-native-operation.md).

## Plan-driven execution (ADR 0008)

Non-trivial work is tracked in `docs/plans/<slug>/plan.md` (canonical schema in [`templates/plan.md`](../templates/plan.md)). Required sections: Purpose / Big Picture, Progress, Surprises & Discoveries, Decision Log, Outcomes & Retrospective, Improvement Candidates, Context, Plan of Work, Concrete Steps, Validation and Acceptance, Idempotence, Artifacts, Interfaces.

Plans are living documents — update Progress / Surprises / Decision Log / Outcomes as work proceeds. Completed plans move to `docs/plans/archive/YYYY-MM-DD-<slug>/` after Verify / Adopt. The lifecycle audit warns when a plan's Progress is complete but it lingers in the active directory. Full schema + adoption rules: [ADR 0008](decisions/0008-plan-persistence.md).

## Improvement Capture loop

Every plan has an `Improvement Candidates` section. Learnings during execution are recorded with `Recommended adoption target` (`current-plan` / `durable-doc` / `adr` / `template` / `audit` / `harness` / `test` / `deferred` / `rejected`) and `Disposition` (`open` / `adopted` / `deferred` / `rejected` / `superseded`). Cross-cutting or destructive adoption goes through Propose → Confirm → Execute. Detail: [`self-operation.md`](self-operation.md) and [`ai-first-lifecycle.md`](ai-first-lifecycle.md).

## Quick CLI reference, grouped by intent

For the authoritative full list with all flags, see [`AGENTS.md`](../AGENTS.md) Subcommands or [`README.md`](../README.md) CLI table.

**Setting up**
- `ai-ops new <name> --purpose "..."` — new project Brief
- `ai-ops migrate <path>` — bring an existing project under ai-ops
- `ai-ops bootstrap` / `ai-ops update` — install / update tier-1/2 tools

**Auditing**
- `ai-ops audit projects` — survey all ghq-tracked projects (priority + sub-flow per project)
- `ai-ops audit harness` — drift between `.ai-ops/harness.toml` and actual files
- `ai-ops audit nix` — Nix adoption gap
- `ai-ops audit security` — secret-name file scan
- `ai-ops audit lifecycle` — ai-ops self-audit
- `ai-ops check` — all of the above + pytest

**Working in parallel (ADR 0010)**
- `ai-ops worktree-new <slug>` — create branch + worktree + plan skeleton
- `ai-ops worktree-cleanup` — remove worktrees with merged PR + archived plan

**Propagating ai-ops improvements (ADR 0011)**
- `ai-ops propagate-anchor` — bump `ai_ops_sha` in managed projects
- `ai-ops propagate-init` — commit untracked manifests
- `ai-ops propagate-files` — refresh `[harness_files]` hashes
- All accept `--auto-yes` for CI / scheduled execution

**GitHub-native ecosystem setup (ADR 0011)**
- `ai-ops setup-ci-workflow --project PATH` — PR adding the drift-check workflow
- `ai-ops setup-codeowners --project PATH` — PR adding CODEOWNERS routing
- `ai-ops setup-ruleset --project PATH --tier {A,B,C}` — apply Repository Ruleset
- `ai-ops report-drift` — translate audit output into Issue / sub-issue lifecycle (called by ecosystem-watch workflow)

## Where to read next

By topic:

- **AI agent contract & cross-cutting policy** → [`AGENTS.md`](../AGENTS.md)
- **Lifecycle deep-dive** → [`ai-first-lifecycle.md`](ai-first-lifecycle.md)
- **Multi-project audit playbook** → [`projects-audit.md`](projects-audit.md)
- **Fixing drift** → [`realignment.md`](realignment.md)
- **Physical relocation (`~/work/...` → `~/ghq/...`)** → [`project-relocation.md`](project-relocation.md)
- **ai-ops self-operation** → [`self-operation.md`](self-operation.md)

By design rationale (ADRs):

- [0001 AGENTS.md primary](decisions/0001-agents-md-as-primary.md)
- [0002 Portability first](decisions/0002-portability-first.md)
- [0003 Deletion policy](decisions/0003-deletion-policy.md)
- [0004 Secrets management](decisions/0004-secrets-management.md)
- [0005 Nix optional reproducibility layer](decisions/0005-nix-optional-reproducibility-layer.md)
- [0006 AI-first project lifecycle](decisions/0006-ai-first-project-lifecycle.md)
- [0007 Python canonical CLI](decisions/0007-python-canonical-cli.md)
- [0008 Plan persistence](decisions/0008-plan-persistence.md)
- [0009 Git workflow tiers](decisions/0009-git-workflow-tiers.md)
- [0010 Worktree workflow](decisions/0010-worktree-workflow.md)
- [0011 GitHub-native ecosystem operation](decisions/0011-github-native-operation.md)
