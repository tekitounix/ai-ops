# ADR 0009: Git workflow tiers for managed projects

> Status: Accepted
> Date: 2026-05-02

## Context

ai-ops mandates a PR-based workflow for the changes it propagates to managed projects (`propagate-anchor`, `propagate-init`, `propagate-files` all open PRs and never push directly to main). However, ai-ops itself and many of its managed projects use ad-hoc git practices:

- ai-ops's own development pushes directly to main (12+ commits in a single session in this very plan series, with 10 consecutive CI failures slipping through unnoticed).
- `umipal` accumulated a long-lived `phase-a/a3-spike-clock-tree` branch with 30+ uncommitted files and 6 deletions, plus its `.ai-ops/harness.toml` was committed only on a `repo-restructure` branch never merged to `master` — which broke `propagate-anchor` until the detector was made remote-aware.
- `mi_share` similarly carries multiple parallel worktrees (`mi_share`, `mi_share.ai-ops-setup`, `mi_share.repo-restructure`) of the same upstream, with `harness.toml` only on a feature branch.

The propagation tooling assumes default branch is the source of truth; when projects' actual git practice deviates from that assumption, the tooling fails or produces misleading audit results.

A one-size-fits-all "all projects must use PR workflow" rule is too rigid for solo personal tools (knx3, ai-ops itself) where direct push is reasonable. A no-rules "each project does what it wants" stance is what created the current mess.

## Decision

Define **four explicit workflow tiers** that managed projects declare in their `.ai-ops/harness.toml`. Each tier has clear norms about branching, push policy, PR usage, and CI gating. Audit signals detect deviation from the declared tier; they do **not** enforce it.

### Tiers

**Tier A — Lightweight (solo, fast iteration)**
- Suitable for: personal tools, single-developer projects (ai-ops itself, knx3).
- Branch: trunk-based; main is the working integration branch. Long-lived feature branches (>30 days) discouraged.
- Push: direct push to main is allowed.
- PR: optional; CI must be green for any push to main.
- Worktree: per-task worktrees encouraged for parallel work but not required.
- Cleanup: stale topic branches deleted promptly.

**Tier B — Managed (multiple PRs in flight)**
- Suitable for: projects where `propagate-*` PRs from ai-ops coexist with user feature work (mi_share, audio-dsp-docs, fastener-research).
- Branch: feature branch + main. main is protected.
- Push: direct push to main not allowed; all changes via PR.
- PR: CI required to be green; review optional (self-review acceptable for solo owners).
- Worktree: encouraged when handling concurrent in-flight PRs.
- Cleanup: branches deleted on merge.

**Tier C — Production / Public**
- Suitable for: public OSS, multi-developer projects, anything with external contributors.
- Branch: feature branch + main with strict protection.
- Push: PR-only.
- PR: CI required + at least one review approval + signed commits encouraged.
- Worktree: standard practice for parallel work.
- Cleanup: enforced by branch protection rules.

**Tier D — Spike / Research (intentionally ad-hoc)**
- Suitable for: long-running research branches, exploratory spikes that legitimately accumulate WIP (umipal's phase-a spike work, fx-llm-research's research artifacts).
- Branch: long-lived feature branches accepted as the working space; main may be far behind the spike.
- Push: anything goes on the spike branch; main itself can still follow Tier A/B norms when promoted.
- PR: not required for spike-internal commits.
- CI: optional; spike branches may not run full CI.
- Cleanup: spike branches archived (not deleted) with a tag when the spike concludes.
- **Critical caveat for propagation**: ai-ops's `propagate-*` only target `main` (or the project's default branch). A spike-only manifest will never be propagated; user must merge the manifest to default before propagation works. This is documented and audited.

### Declaration

A project declares its tier in `.ai-ops/harness.toml`:

```toml
ai_ops_sha = "..."
last_sync = "..."
workflow_tier = "B"          # one of "A", "B", "C", "D"

[harness_files]
...
```

Missing field is treated as `"D"` (most permissive) for backward compatibility. ai-ops's own `harness.toml`, when ai-ops becomes self-managed, declares `workflow_tier = "A"`.

### Audit signals

`ai-ops audit projects` adds:

- `workflow_tier` column showing the declared value (or `"D"` default).
- `tier_violations` count: number of detected deviations from the declared tier's norms.

Specific detectors (per tier):

- Any tier: `.ai-ops/harness.toml` exists only on a feature branch, not on default → "manifest not on default branch" (already detected by `propagate-anchor` and `propagate-files`).
- Tier A: any feature branch >30 days old with uncommitted-on-default WIP commits → "long-lived branch in Tier A".
- Tier B/C: commits on main authored without a PR (detected via `gh api repos/.../commits` showing no associated PR) → "direct-push-to-main in Tier B/C".
- Tier C only: PR merged without review approval → "unreviewed merge in Tier C".
- Tier D: no specific violations (anything goes); the only signal is "user declared Tier D — propagation requires manual merge to default" as INFO not WARN.

Detection only. ai-ops does **not** enforce tiers (no branch-protection-rule mutation, no commit hook installation). Enforcement is the project owner's responsibility via GitHub UI, server-side hooks, or whatever they choose. ai-ops just makes drift visible.

### Reflection in managed projects

The tier declaration is a user judgment call, not a mechanical sync. Therefore:

- New projects via `ai-ops migrate`: the AI agent surfaces tier choice in the Brief based on observed signals (managed status, public/private, recent activity, contributor count). User confirms the tier in the Brief; the manifest is created with that tier.
- Existing projects: the tier is added on the next realignment cycle. `docs/realignment.md` Phase 2 Brief includes a tier proposal step.
- ai-ops itself: declares Tier A in this commit (dogfood).
- Other existing projects: default to "D" until user runs realignment to declare explicitly. Audit shows `workflow_tier=D` so they're visible but not flagged as violation.

`propagate-init` / `propagate-anchor` / `propagate-files` do **not** auto-add or change `workflow_tier`. The field is set once via realignment and changed only by user-driven realignment.

## Consequences

Positive:

- Workflow norms become explicit and project-specific without forcing a one-size-fits-all rule.
- The propagation system's existing assumptions (default branch is canonical) become defensible because we require Tier A/B/C projects to have manifest-on-default. Tier D is the explicit exception and warns about it.
- Audit visibility for "shoemaker's children" — ai-ops itself becomes self-aware that direct-push-to-main is its declared norm (Tier A), and any deviation that would break that (e.g., a Tier A project accumulating long-lived feature branches) is flagged.
- New projects start with explicit tier declaration in Brief, eliminating "what's the right workflow?" ambiguity at project birth.

Negative:

- One more dimension for managed projects to declare. Most projects can default to D and ignore until they grow; only those that hit propagation issues need to declare a stricter tier.
- Tier violation detection is heuristic. Some signals (long-lived branch, direct push) require gh API calls that may rate-limit or fail offline.
- Tier D is permissive enough that it doesn't really constrain umipal-style chaos. The audit can warn but not prevent. Real reduction of umipal's mess comes from user adopting Tier B.

Out of scope (deferred):

- `ai-ops setup-workflow --tier <X>` automation (mutating GitHub branch protection via API) — too heavy for v1.
- Per-tier CI configuration templates — projects bring their own CI.
- Cross-machine state sync for multi-machine workflows.
- Squash vs. merge vs. rebase strategy normalization — out of scope; project-specific.

## Related

- ADR 0005: Nix optional reproducibility layer (precedent for tiered adoption).
- ADR 0006: AI-first project lifecycle.
- ADR 0008: Execution plan persistence.
- ADR 0010: Worktree-based parallel work and plan binding — refines the
  Tier B/C "feature branch + PR" expectation to "trunk-based + short-
  lived branch + worktree per parallel task" per current (2026) industry
  best practice. Long-lived branches are a Tier D acceptance, not a
  Tier B norm.
- `docs/plans/git-workflow-tiers/plan.md`: implementation plan.
