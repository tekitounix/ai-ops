# ADR 0010: Worktree-based parallel work and plan binding

> Status: Accepted
> Date: 2026-05-02

## Context

ai-ops uses `git worktree` internally for `propagate-*` PR generation (each PR isolated under `~/.cache/ai-ops/worktrees/`). For human and AI-agent dev work, however, no worktree convention exists. Working sessions in this very repo have routinely pushed directly to `main` with no parallel-work isolation, and managed projects (umipal in particular) have accumulated multiple parallel checkouts without any binding to plan documents.

External research (May 2026 web survey) confirmed two industry trends:

1. **Trunk-based development** is the modern consensus for high-velocity teams. DORA elite performers using trunk-based achieve 182× more frequent deployments and 127× faster lead times. GitFlow is reserved for stability/regulatory contexts.
2. **Git worktree became load-bearing for AI coding in Q1 2026**. By April 2026, almost every major AI coding tool (Claude Code, Cursor, Aider, Codex, Gemini) shipped worktree support. Cursor built "Parallel Agents" directly on worktrees. The practical limit is 3–5 parallel worktrees per repo.

Two layout patterns dominate in practice:

- **Sibling**: `~/projects/my-app/` and `~/projects/my-app-<feature>/` — easy to navigate, separate editor windows per worktree.
- **Grouped**: `~/projects/worktrees/my-app-<task>/` — centralized but separated from the project tree.

ai-ops sits under `~/ghq/<host>/<owner>/<repo>/`. The sibling pattern translates naturally to `~/ghq/<host>/<owner>/<repo>.<slug>/` — and `umipal`/`mi_share` already use this layout incidentally (e.g., `~/ghq/.../mi_share.repo-restructure/`).

The missing piece is binding: when a worktree exists, what plan does it correspond to? When a plan ships, which worktree should be removed? Without explicit binding, parallel work accumulates ad-hoc and cleanup is forgotten.

## Decision

**1. Sibling worktree layout for human/agent dev work**

Worktrees for human or AI-agent dev work live as siblings of the main repo:

```
~/ghq/<host>/<owner>/<repo>/              ← primary checkout (main branch)
~/ghq/<host>/<owner>/<repo>.<slug>/       ← worktree for feature/<slug>
~/ghq/<host>/<owner>/<repo>.<other>/      ← worktree for fix/<other>
```

Naming uses `<repo-name>.<slug>` where `<slug>` matches the plan slug. This convention is already the de facto pattern in `umipal`/`mi_share`; ADR 0010 codifies it.

**Internal worktrees** for `propagate-*` PR generation continue to live under `~/.cache/ai-ops/worktrees/` (not user-visible) because they are short-lived machine artifacts.

**2. Branch ↔ Worktree ↔ Plan binding (1:1:1)**

For non-trivial work that warrants a plan:

- One **plan** at `docs/plans/<slug>/plan.md`.
- One **branch** named `<type>/<slug>` (default `feat`, alternatives `fix`/`chore`/`docs`/`refactor`).
- One **worktree** at `<repo-parent>/<repo-name>.<slug>/`.

The plan document records this binding explicitly via two fields placed near the top:

```markdown
Plan path: `docs/plans/<slug>/plan.md`. Archive path after adoption: `docs/plans/archive/YYYY-MM-DD-<slug>/`.

Branch: `feat/<slug>`
Worktree: `../<repo-name>.<slug>/` (when used; trivial work may stay on main)
```

For trivial single-commit work, no worktree is required and the Branch/Worktree fields can read `Branch: main / Worktree: n/a`.

**3. Practical worktree limit: 3–5 per repo**

Beyond 5, context-switching cost between terminals/editors typically outweighs the parallelism benefit. `ai-ops audit projects` does **not** enforce this; it surfaces an INFO when a project exceeds 5 worktrees.

**4. Lifecycle**

- **Create**: when starting a non-trivial plan and parallel work isolation is wanted, run `ai-ops worktree-new <slug>`. The helper creates the branch, the worktree, and a plan.md skeleton from `templates/plan.md` with Branch/Worktree fields pre-filled.
- **Work**: all work for that plan happens in the worktree. The plan's Progress / Decision Log / etc. are updated there. Commits go on the branch.
- **PR**: when ready, push the branch and open a PR (manually or via `gh pr create`).
- **Merge**: after PR merge the branch is deleted on the remote. ai-ops itself sets the repository's `Automatically delete head branches` setting (`gh repo edit --delete-branch-on-merge`) so deletion happens regardless of whether the merger passed `--delete-branch`. Always confirm post-merge with `git fetch --prune origin && git ls-remote --heads origin`; if a stale ref remains, recover with `git push origin --delete <branch>`.
- **Archive plan** (mandatory before worktree removal): from the primary worktree on `main`, run `git pull --ff-only` to take in the merged PR, then `git mv docs/plans/<slug> docs/plans/archive/YYYY-MM-DD-<slug>` and commit + push the archive move. **Tier A** (ai-ops itself, trunk-based) pushes the archive commit straight to `main`. **Tier B / C** (PR-required) opens a one-commit "chore(plans): archive <slug> plan" PR and merges it the normal way.
- **Remove worktree**: `ai-ops worktree-cleanup` lists worktrees whose branches are merged AND plans are archived, and offers to remove them. `--auto` removes without confirmation; default is interactive. The two signals are required together because either alone leaves a hidden risk: an unarchived plan signals work that may not have shipped, and an unmerged branch signals work whose disposition is unknown.

**5. Coordination across parallel worktrees**

When two worktrees touch the same shared file (`AGENTS.md`, `harness.toml`, ADRs, etc.), conflicts surface at PR merge time. The convention to minimize this:

- Each plan's **Decision Log** records "Other active plans touching the same files" if known. This is a soft signal, not enforcement.
- Plans **rebase frequently** against `main` (or whichever base branch they were created from) to catch conflicts early.
- Long-lived parallel worktrees on the same shared files are a smell — favor sequential execution or merge-then-rebase.

**6. Tier integration (per ADR 0009)**

The worktree convention applies regardless of tier, but the workflow expectations differ:

- **Tier A** (trunk-based solo): worktree per non-trivial parallel task; merge to main quickly via PR or direct push.
- **Tier B/C** (managed/production): worktree per non-trivial parallel task; PR required, branch protection enforces no direct push.
- **Tier D** (spike): worktrees may be very long-lived (the spike branch IS a worktree); explicit acceptance.

ADR 0009 already requires `feature branch + PR` for Tier B; this ADR refines that to `trunk-based + short-lived branch + PR + worktree per parallel task`. Long-lived branches are a Tier D acceptance, not a Tier B norm.

## Consequences

Positive:

- Parallel work has a structural form (branch ↔ worktree ↔ plan) that can be inspected, reasoned about, and cleaned up.
- The de facto sibling pattern becomes documented; future agents working in `umipal` etc. follow the same convention without re-inventing it.
- AI-agent parallel work (Claude Code, Cursor, etc.) maps cleanly onto this convention — each `claude --worktree` session corresponds to one plan/branch.
- Plan docs become self-locating: reading a plan tells you exactly which worktree and branch it lives on.

Negative:

- One more piece of process to remember when starting non-trivial work. Mitigated by `ai-ops worktree-new <slug>` automation.
- Worktree cleanup remains user-driven (no auto-delete) to preserve safety. This means stale worktrees accumulate if `worktree-cleanup` isn't run periodically.
- Disk usage increases linearly with worktree count (each worktree has its own dependency installs).

Out of scope (deferred):

- Stacked PR adoption (research showed `gh-stack` and Graphite are mature; defer to a separate ADR per managed-project tier if/when needed).
- Merge queue automation (Tier C territory; defer until any managed project asks for it).
- jujutsu (jj) adoption (production-ready for solo, but ai-ops's git-based propagators would need adaptation; defer).
- Per-worktree dev-server orchestration (port assignment, db isolation) — out of scope for ai-ops.
- Auto-cleanup hooks on PR merge — leave user-driven for safety.

## Related

- ADR 0006: AI-first project lifecycle.
- ADR 0008: Execution plan persistence.
- ADR 0009: Git workflow tiers (this ADR refines the tier-B/C "PR-based" expectation to "trunk-based + short-lived branches + worktree per parallel task").
- `docs/plans/worktree-workflow/plan.md`: implementation plan.
- External: industry trend toward trunk-based + worktree-per-AI-session workflow (May 2026 survey).
