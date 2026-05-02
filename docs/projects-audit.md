# Projects Audit (every ghq-tracked project)

> Scope: enumerate every ghq-tracked project, surface drift signals per project, prioritize by reversibility / urgency, and route each high-priority finding into the appropriate single-project sub-flow (migrate / realign / relocate). Read-only Discovery → priority-sorted Brief → per-project Execute on confirmation.

## When to use

The Quick start prompt `Per github.com/tekitounix/ai-ops, audit my projects.` reaches this playbook. The agent reads ai-ops as reference, walks `ghq list -p`, and emits a priority-sorted Audit Brief.

This playbook does **not** modify any project without per-project user confirmation. For greenfield work use the first Quick start prompt; for a single working tree use the second (`align this project`).

## Operation Model

```text
Phase 1 Discovery (read-only, all projects)
  -> Phase 2 Brief (priority-sorted table + recommendations)
  -> Phase 3 Execute (per-project, per sub-flow, per confirmation)
  -> Phase 4 Verify (re-run discovery on touched projects)
```

Each project that requires action gets its own Propose → Confirm → Execute cycle. Batch approval across projects is forbidden by AGENTS.md §Operation Model. Mid-session interruption / resumption is supported because the Brief is the durable state.

## Phase 1 — Discovery (read-only via the CLI)

The agent runs the canonical collector — it does not assemble the table from individual `find` / `git` invocations. The CLI is deterministic, version-controlled, and produces identical output for AI agents and scheduled jobs (cron / CI).

```sh
# Machine-readable view for the agent to reason over.
python -m ai_ops audit projects --json > /tmp/projects-audit.json

# Or, for the user to glance at:
python -m ai_ops audit projects
```

Each row carries the nine signals that drive priority and sub-flow assignment:

| key | meaning |
|---|---|
| `loc` | `ok` if path is under `~/ghq/<host>/<owner>/<repo>/`, else `DRIFT` |
| `mgd` | `yes` if `.ai-ops/harness.toml` is present, `src` for ai-ops itself, else `no` |
| `nix` | `present` / `missing` / `n/a` (n/a = docs-only repo) |
| `sec` | secret-name file count (`.env`, `*.key`, `*.pem`, `id_rsa`, …; `.env.example` etc. excluded) |
| `dirty` | uncommitted state lines (`git status --porcelain`) |
| `last_commit_human` | `git log -1 --format=%ar` (e.g. "1 day ago") |
| `todo` | TODO / FIXME / WIP / TBD count across text sources (rg-based; degrades to 0 if rg absent) |
| `agents_md` | AGENTS.md present at root |
| `policy_drift` | `ok` / `stale` / `diverged` / `ahead-and-behind` / `no-anchor` / `n/a` — managed project's own `templates/plan.md` and active plans vs ai-ops canonical schema (`^## ` heading set). `n/a` = unmanaged or ai-ops itself. `no-anchor` = `harness.toml.ai_ops_sha` missing. `stale` = canonical has sections project lacks. `diverged` = project has extra sections. `ahead-and-behind` = both. AGENTS.md is intentionally not checked (project-specific contract). |
| `pending_propagation_prs` | Count of open PRs whose head branch starts with `ai-ops/` in the project's GitHub repo (i.e., PRs created by `ai-ops propagate-anchor` or `ai-ops propagate-init`). `-1` indicates `gh` is unavailable so the count is unknown; `0` means no in-flight propagation work. Polls only managed projects to keep audit cheap. |
| `remote_anchor_synced` | `true` / `false` / `null` — whether `origin/<default-branch>`'s `.ai-ops/harness.toml` carries `ai_ops_sha == current ai-ops HEAD`. `true` = propagation is done, `false` = anchor-sync PR would help, `null` = couldn't determine (no `gh`, fetch failed, or no manifest on default branch). When `true`, severity does not escalate to P1 just because local `harness_drift` is True (user merely needs to pull). |

Plus three derived flags the CLI computes once: `has_stack`, `is_docs_only`, `harness_drift`. Filenames only — secret **values** are never opened (the CLI's `_count_secret_files` is name-based).

### Filter to a single priority during reasoning

```sh
python -m ai_ops audit projects --json --priority P0   # immediate-action only
python -m ai_ops audit projects --json --priority P1   # planned-action only
```

### Exit code (for cron / CI)

`ai-ops audit projects` returns `1` if any P0 or P1 row remains in the (filtered) output, `0` otherwise. A scheduled job that runs the command nightly and sets up an alert on rc=1 surfaces drift the moment it appears.

## Phase 2 — Audit Brief

The Brief is a Markdown document the agent assembles from the CLI's JSON output. Title: "Projects Audit Brief". Date-stamped. Pinned in chat for the rest of the session.

### Priority assignment (computed by the CLI)

| Priority | Trigger |
|---|---|
| **P0** | `loc=DRIFT` (project lives outside `~/ghq/`) OR `sec≥1` (secret-name file present) |
| **P1** | stack-bearing project with `nix=missing`, OR `mgd=yes` with harness drift, OR `mgd=yes` with `policy_drift` ∈ {`stale`, `diverged`, `ahead-and-behind`, `no-anchor`}, OR last commit older than 540 days (~18 months) on a still-active stack |
| **P2** | observation only: clean managed projects, validation fixtures (`mgd=no` and intentionally so), dirty work in progress, TODO churn |

A project's priority is the highest it qualifies for; the JSON lists each project exactly once.

### Sub-flow assignment (also computed by the CLI)

| Condition | `sub_flow` |
|---|---|
| `loc=DRIFT` | `relocate` → `docs/project-relocation.md` |
| `loc=ok` AND `mgd=no` AND has stack or non-docs source | `migrate` → `docs/project-addition-and-migration.md` |
| `loc=ok` AND `mgd=yes` AND drift signal (`nix=missing+has_stack`, `harness_drift`, or `policy_drift` ∈ {`stale`, `diverged`, `ahead-and-behind`, `no-anchor`}) | `realign` → `docs/realignment.md` |
| otherwise | `no-op` |

Validation / fixture repositories (`mgd=no` and intentionally so, often `~/ghq/local/...`) are P2 by default and listed in the Brief as `no-op` unless the user explicitly opts them into a sub-flow.

### Brief structure (what the agent assembles from the JSON)

```markdown
# Projects Audit Brief — YYYY-MM-DD

Source: `python -m ai_ops audit projects --json`
Total: <N> projects (managed=<X>, P0=<a>, P1=<b>, P2=<c>)

## P0 — immediate action (<a> projects)
| project | path | loc | sec | sub-flow | reason |
| ...     | ...  | ... | ... | ...      | ...    |

## P1 — planned action (<b> projects)
| project | path | nix | harness_drift | last | sub-flow | reason |

## P2 — observation only (<c> projects)
- short summary, no per-row table needed unless something stands out.
```

Reason text in the table cites the specific trigger (e.g. "loc=DRIFT (~/work/foo)", "nix=missing + has_stack=true (package.json)", "harness_drift=true (3 modified files)"). The Brief surfaces the exact signal that drove each priority so the user can confirm intent before approving the sub-flow.

## Phase 3 — Execute (per project, per confirmation)

The agent walks the Brief in priority order — every P0 row first, then P1. P2 rows are observed only and never auto-executed. For each row that requires action:

1. Propose the sub-flow with the project's path and the specific drift signals that triggered the priority.
2. Wait for individual user confirmation (`yes` / `defer` / `skip`). The ai-ops Operation Model forbids batch approval; one confirmation buys exactly one project's sub-flow.
3. On `yes`, follow the linked playbook in full — including its own Phase 1-4. This audit does not skip or abbreviate sub-flow steps.
4. On `defer` / `skip`, record the choice in the Brief so a later session can pick it up.

The Brief is the durable state. If the session is interrupted (context pressure, user step-away, partial action), the Brief shows what is finished, what is deferred, and what is pending — and the next agent invocation resumes from there using the same Quick start prompt.

## Phase 4 — Verify (re-run discovery on touched projects)

After Phase 3 (or any intentional pause), the agent re-runs Phase 1 Discovery for every project that was touched and emits a delta table:

```text
| project | pri before | pri after | result        |
|---------|------------|-----------|---------------|
| <name>  | P0         | P2        | passed        |
| <name>  | P1         | P1        | partial — see brief |
```

The same priority logic that triggered Phase 3 must now resolve to **P2 or below** for the touched project. Anything still at P0 / P1 is recorded as deferred in the Brief, with the reason, and is the entry point for the next audit cycle.

## Constraints

- Phase 1 reads only filenames, git metadata, and text-source patterns. Secret **values** are never opened.
- Each P0 / P1 project gets its own Propose → Confirm → Execute. Batch approval across multiple projects is forbidden (AGENTS.md §Operation Model).
- Sub-flow execution defers entirely to the linked playbook. This audit does not duplicate relocation / migration / realignment steps; if a sub-flow's own destructive step requires confirmation (e.g. relocation Step 2's `mv`), that confirmation is presented inside this audit session.
- Validation / fixture repositories (`mgd=no` and intentionally so, often `~/ghq/local/...`) are P2 by default and excluded from drift counts unless user explicitly opts them in.
- Phase 4 reuses Phase 1 logic verbatim. No separate "verify" procedure; touched projects must drop to P2 or below.
- The Brief is durable. The agent never advances past a step in Phase 3 without writing the outcome (`done` / `deferred` / `skipped`) into the Brief, so resume after interruption is loss-free.

## See Also

- `AGENTS.md` §Workspace — `~/ghq/` is canonical
- `AGENTS.md` §Operation Model — Propose → Confirm → Execute, no batch
- `docs/realignment.md` — single-project realign sub-flow
- `docs/project-addition-and-migration.md` — single-project migrate sub-flow
- `docs/project-relocation.md` — single-project relocate sub-flow
- `ai-ops audit nix --report` — nix-gap subset across all projects (legacy column-only view)
- `ai-ops audit harness --path <P> --strict` — per-project harness drift used in P1 classification
