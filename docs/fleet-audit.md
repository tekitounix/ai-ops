# Fleet Audit (ghq-managed projects)

> Scope: enumerate every ghq-tracked project, surface drift signals per project, prioritize by reversibility / urgency, and route each high-priority finding into the appropriate single-project sub-flow (migrate / realign / relocate). Read-only Discovery → priority-sorted Brief → per-project Execute on confirmation.

## When to use

The Quick start prompt `Per github.com/tekitounix/ai-ops, audit my fleet.` reaches this playbook. The agent reads ai-ops as reference, walks `ghq list -p`, and emits a priority-sorted Fleet Audit Brief.

This playbook does **not** modify any project without per-project user confirmation. For greenfield work use the first Quick start prompt; for a single working tree use the second (`align this project`).

## Operation Model

```text
Phase 1 Discovery (read-only, all projects)
  -> Phase 2 Brief (priority-sorted table + recommendations)
  -> Phase 3 Execute (per-project, per sub-flow, per confirmation)
  -> Phase 4 Verify (re-run discovery on touched projects)
```

Each project that requires action gets its own Propose → Confirm → Execute cycle. Batch approval across projects is forbidden by AGENTS.md §Operation Model. Mid-session interruption / resumption is supported because the Brief is the durable state.

## Phase 1 — Discovery (read-only)

For every project from `ghq list -p`, collect a fixed set of signals. The agent's cwd stays at the ai-ops repo (or any read-only safe location); each project is inspected via `git -C <path>` and `find <path>`, never by `cd`-ing in. Secret **values** must not be opened — only filenames are inspected for the `sec` signal.

```sh
ghq list -p > /tmp/fleet-audit.list
wc -l < /tmp/fleet-audit.list                                # total tracked projects
```

For each project path `$P`:

```sh
# (a) location drift — should be under ~/ghq/<host>/<owner>/<repo>/
case "$P" in
    "$HOME/ghq/"*) loc=ok ;;
    *)             loc=DRIFT ;;
esac

# (b) managed signal
[ -f "$P/.ai-ops/harness.toml" ] && mgd=yes || mgd=no

# (c) nix state — flake.nix presence; gap classification reuses
#     `python -m ai_ops audit nix --report` for the whole fleet at once.
[ -f "$P/flake.nix" ] && nix=present || nix=missing

# (d) secret-name files — name only, no content read
sec=$(find "$P" -maxdepth 3 \( -path "$P/.git" -o -path "$P/node_modules" \
        -o -path "$P/.venv" -o -path "$P/vendor" -o -path "$P/dist" \
        -o -path "$P/build" \) -prune -o \
      -type f \( -name ".env" -o -name "*.key" -o -name "*.pem" \
        -o -name "id_rsa" -o -name "id_ed25519" \) -print 2>/dev/null | wc -l)

# (e) last commit recency
last=$(git -C "$P" log -1 --format=%ar 2>/dev/null || echo "no commits")

# (f) untracked / dirty count (porcelain lines)
dirty=$(git -C "$P" status --porcelain 2>/dev/null | wc -l)

# (g) TODO / FIXME / WIP / TBD count — text-source only, summary
todo=$(rg -c -t md -t py -t js -t ts -t rs -t go --hidden \
        -g '!.git' -g '!node_modules' -g '!.venv' -g '!vendor' \
        -e 'TODO|FIXME|WIP|TBD' "$P" 2>/dev/null | \
        awk -F: '{s+=$2} END{print s+0}')

# (h) AGENTS.md presence
[ -f "$P/AGENTS.md" ] && agents=yes || agents=no
```

`audit nix --report` already computes `nix` gaps fleet-wide; the agent should run it once and join its output into the table rather than re-implementing the rubric per project.

This phase emits no writes. The output is a CSV / TSV held in memory and rendered as Phase 2's Markdown table.

## Phase 2 — Fleet Audit Brief

Single Markdown document. Title: "Fleet Audit Brief". Date-stamped. Pinned in chat for the rest of the session.

### Priority assignment

| Priority | Trigger |
|---|---|
| **P0** | `loc=DRIFT` (project lives outside `~/ghq/`) OR `sec≥1` (secret-name file present) |
| **P1** | stack-bearing project with `nix=missing`, OR `mgd=yes` with harness drift detected by `audit harness --strict --path <P>`, OR `last` is older than 18 months on a still-active stack (archive vs. continue decision needed) |
| **P2** | observation only: clean managed projects, validation fixtures (`mgd=no` and intentionally so), dirty work in progress, TODO churn |

A project's priority is the highest it qualifies for; it is listed once.

### Table format

```text
| project | path                                     | loc  | mgd | nix     | sec | dirty | last      | todo | pri | sub-flow |
|---------|------------------------------------------|------|-----|---------|-----|-------|-----------|------|-----|----------|
| ai-ops  | ~/ghq/github.com/tekitounix/ai-ops       | ok   | yes | present | 0   | 0     | 1 day ago | 12   | P2  | no-op    |
| <name>  | ~/work/<name>                            | DRIFT| no  | missing | 0   | 3     | 4 days    | 31   | P0  | relocate |
```

Columns:

- `project` — last segment of path
- `path` — repo-rel form (`~/ghq/...` or whatever the actual location is)
- `loc` — `ok` if under `~/ghq/`, `DRIFT` otherwise
- `mgd` — yes/no, `.ai-ops/harness.toml` presence
- `nix` — `present` / `missing` / `n/a` (docs-only / archive)
- `sec` — count of secret-name files (P0 trigger when ≥ 1)
- `dirty` — count of porcelain lines (uncommitted state, P2 only)
- `last` — `git log -1 --format=%ar`
- `todo` — text-source TODO/FIXME/WIP/TBD count (P2 signal)
- `pri` — P0 / P1 / P2
- `sub-flow` — recommended next action

### Sub-flow assignment rules

| Condition | Sub-flow |
|---|---|
| `loc=DRIFT` | `relocate` → `docs/project-relocation.md` |
| `loc=ok` AND `mgd=no` AND has source / config (not pure-docs / fixture) | `migrate` → `docs/project-addition-and-migration.md` |
| `loc=ok` AND `mgd=yes` AND any drift signal (harness drift, missing nix on stack-bearing, accumulated TODOs) | `realign` → `docs/realignment.md` |
| `loc=ok` AND clean, or `P2` fixture | `no-op` |

Each project is listed exactly once with exactly one sub-flow recommendation. Validation / fixture repositories are explicitly noted in the Brief and pre-classified as `no-op` unless the user opts them into a sub-flow.

## Phase 3 — Execute (per project, per confirmation)

The agent walks the Brief in priority order — every P0 row first, then P1. P2 rows are observed only and never auto-executed. For each row that requires action:

1. Propose the sub-flow with the project's path and the specific drift signals that triggered the priority.
2. Wait for individual user confirmation (`yes` / `defer` / `skip`). The ai-ops Operation Model forbids batch approval; one confirmation buys exactly one project's sub-flow.
3. On `yes`, follow the linked playbook in full — including its own Phase 1-4. The fleet audit does not skip or abbreviate sub-flow steps.
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

The same priority logic that triggered Phase 3 must now resolve to **P2 or below** for the touched project. Anything still at P0 / P1 is recorded as deferred in the Brief, with the reason, and is the entry point for the next fleet audit cycle.

## Constraints

- Phase 1 reads only filenames, git metadata, and text-source patterns. Secret **values** are never opened.
- Each P0 / P1 project gets its own Propose → Confirm → Execute. Batch approval across multiple projects is forbidden (AGENTS.md §Operation Model).
- Sub-flow execution defers entirely to the linked playbook. The fleet audit does not duplicate relocation / migration / realignment steps; if a sub-flow's own destructive step requires confirmation (e.g. relocation Step 2's `mv`), that confirmation is presented inside the fleet-audit session.
- Validation / fixture repositories (`mgd=no` and intentionally so, often `~/ghq/local/...`) are P2 by default and excluded from drift counts unless user explicitly opts them in.
- Phase 4 reuses Phase 1 logic verbatim. No separate "fleet verify" procedure; touched projects must drop to P2 or below.
- The Brief is durable. The agent never advances past a step in Phase 3 without writing the outcome (`done` / `deferred` / `skipped`) into the Brief, so resume after interruption is loss-free.

## See Also

- `AGENTS.md` §Workspace — `~/ghq/` is canonical
- `AGENTS.md` §Operation Model — Propose → Confirm → Execute, no batch
- `docs/realignment.md` — single-project realign sub-flow
- `docs/project-addition-and-migration.md` — single-project migrate sub-flow
- `docs/project-relocation.md` — single-project relocate sub-flow
- `ai-ops audit nix --report` — fleet-wide nix-gap subset of this audit
- `ai-ops audit harness --path <P> --strict` — per-project harness drift used in P1 classification
