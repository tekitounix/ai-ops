# ADR 0011: GitHub-native ecosystem operation

> Status: Accepted
> Date: 2026-05-02

## Context

ai-ops's operation has accumulated multiple `propagate-*` subcommands, audit signals, and tier definitions. These all assume the user proactively runs CLI commands to learn about drift, decide what to fix, and execute remediation. There is no notification channel: drift surfaces only when the user runs `audit projects` themselves.

Local mechanisms considered earlier (launchd notifier, direnv hooks, shell prompt integration) were rejected by the user as the wrong abstraction layer. ai-ops already assumes GitHub + ghq as foundational substrate; the right design uses GitHub's own primitives (Issues, sub-issues, Projects v2, scheduled Actions, rulesets, CODEOWNERS, reusable workflows) as the notification + governance + propagation channel.

External research (May 2026) confirmed:

- **GitHub Sub-issues + Projects v2 hierarchy view** went GA in 2026. 50 sub-issues per parent, 8 nested levels, hierarchy view with progress aggregation.
- **Repository Rulesets** went GA, succeeding branch protection rules. Multiple rulesets aggregate; tags and repository-wide events are supported; evaluate mode allows trial.
- **Reusable workflows + composite actions** are the standard for cross-repo workflow sharing. Pin via tag or SHA; calling repo passes inputs.
- **Renovate / Dependabot pattern**: scheduled job opens PRs in target repos; user merges via standard GitHub Notifications. ai-ops's `propagate-*` is already this pattern.
- **GitHub Copilot Cloud Coding Agent** (March 2026): assign Issue → autonomous PR. Pro+ plan required; out of scope for v1.

The decisive insight: **the PR is the notification, the Issue is the work tracker, the Project board is the dashboard.** ai-ops doesn't need a new notification mechanism — it needs to fully use GitHub's existing one.

## Decision

Re-frame ai-ops as a "Renovate-style propagator + central dashboard" running on GitHub-native infrastructure. Three architectural moves:

### Move 1: Central ecosystem dashboard in ai-ops repo

Create a Projects v2 board in the ai-ops repo named "Ecosystem". Each managed project gets one **parent issue** in the ai-ops repo (not in the target project), labelled `ecosystem` and tagged with the project name. Drift signals create **sub-issues** under the parent. The Project board uses hierarchy view to show parent + sub-issue progress at a glance.

Sub-issue lifecycle:

- Created when `ecosystem-watch` workflow detects a new drift category
- Updated (body edited) when drift state changes
- Closed when drift resolves (drift signal disappears in next audit run)

User receives standard GitHub Notifications on issue creation, updates, and closures.

### Move 2: ai-ops repo gains 3 scheduled / on-demand workflows

1. **`.github/workflows/ecosystem-watch.yml`** — weekly cron + `workflow_dispatch`
   - Runs `ai-ops audit projects --json`
   - Calls `ai-ops report-drift` (new helper) which open / updates / closes sub-issues
   - Posts a summary comment on the ecosystem parent issue

2. **`.github/workflows/propagate-cron.yml`** — weekly cron + `workflow_dispatch`
   - Runs `ai-ops propagate-anchor --all --auto-yes`, `propagate-init --all --auto-yes`, `propagate-files --all --auto-yes`
   - Each generates PRs in target managed projects (existing mechanism)
   - PRs are the per-project notifications
   - `--auto-yes` is a new flag added to all `propagate-*` commands to skip per-project Y/n prompts when running in CI

3. **`.github/workflows/managed-project-check.yml`** — reusable workflow
   - Inputs: `tier` (string)
   - Steps: install ai-ops, run `audit harness --strict`, run `audit projects --priority=P0,P1` for the current project
   - Tier B+: required status check; failure blocks merge via ruleset
   - Each managed project's local workflow calls this via `uses: tekitounix/ai-ops/.github/workflows/managed-project-check.yml@v1`

### Move 3: Per-managed-project artifacts distributed via templates + `setup-*` helpers

ai-ops bundles three artifact families that each managed project opts into:

1. **`templates/artifacts/.github/workflows/ai-ops.yml`** — thin caller of the reusable workflow above. Runs on PR + schedule.

2. **`templates/artifacts/.github/CODEOWNERS.template`** — routes `.ai-ops/` and `.github/workflows/ai-ops*.yml` changes to the project owner. So `propagate-*` PRs auto-request user review.

3. **`templates/artifacts/rulesets/<tier>.json`** — Tier-A/B/C ruleset definitions in JSON. Tier A: evaluate mode (informational). Tier B: PR-only, ai-ops-drift status check required. Tier C: above + CODEOWNERS approval required + merge queue.

Three new CLI helpers apply these per-project (user-driven, opt-in):

- `ai-ops setup-ci-workflow [--project PATH]` — creates `.github/workflows/ai-ops.yml` (if absent) referencing the reusable workflow at the user's chosen tag.
- `ai-ops setup-codeowners [--project PATH]` — creates / updates `.github/CODEOWNERS` with ai-ops-related routing.
- `ai-ops setup-ruleset [--tier {A,B,C}] [--project PATH]` — applies the tier ruleset via `gh api repos/{owner}/{repo}/rulesets`.

Each helper uses existing worktree-based PR pattern: creates branch, commits the artifact, pushes, opens PR. User reviews and merges.

### Move 4: New audit signals

Three signals added to `ProjectSignals` to make ai-ops aware of which managed projects have which artifacts deployed:

- `has_ai_ops_workflow: bool` — `.github/workflows/ai-ops.yml` exists on default branch
- `has_codeowners_routing: bool` — `.github/CODEOWNERS` references `.ai-ops/`
- `has_tier_ruleset: bool` — `gh api repos/.../rulesets` returns a ruleset matching the project's declared tier

Missing artifacts surface as `tier_violations` (existing mechanism per ADR 0009) so the user sees them in `audit projects` table and on the ecosystem dashboard.

### Move 5: Tier definition refinement

ADR 0009's tiers gain explicit GitHub-native expectations:

- **Tier A**: ruleset in evaluate mode; ai-ops-drift workflow optional advisory; CODEOWNERS optional.
- **Tier B**: ruleset enforced; PR-only; ai-ops-drift required; CODEOWNERS routes ai-ops review.
- **Tier C**: above + ruleset requires reviewer approval + signed commits + merge queue.
- **Tier D**: rulesets disabled or no ai-ops-drift workflow; explicitly accepted ad-hoc.

ADR 0009 is amended (not superseded) with a "GitHub-native enforcement profile" section pointing here.

### Move 6: Issues vs Discussions split

- **Issues** for ai-ops: drift events, propagation work, project realignment tasks. Actionable + closeable.
- **Discussions** for ai-ops: ADR ideation before formalization, design questions, ecosystem retrospectives. Open-ended.
- **PRs** for ai-ops: all code/doc changes (per ADR 0010 worktree pattern), self-review acceptable for solo dev (Tier A).

## Consequences

Positive:

- ai-ops's primary user-facing surface becomes GitHub's existing notification system (Issues, PRs, Project boards). User doesn't learn a new tool — they use GitHub Notifications they already check.
- The "Ecosystem" Project board becomes a single source of truth for "what's the state of all managed projects?". Sub-issue hierarchy makes complex multi-project work tractable.
- Reusable workflow means the per-project drift gate can be **updated centrally** (bump tag in ai-ops, all managed projects pick up the new check on next CI run). No `propagate-*` PR needed for workflow updates.
- The shoemaker's-children problem ("ai-ops itself doesn't follow the workflow it mandates") closes: ai-ops uses Tier A self-monitoring with its own ecosystem-watch workflow.
- Existing `propagate-*` mechanism gains scheduled execution via `propagate-cron.yml`; user no longer needs to remember to run it.

Negative:

- One repo becomes a notification hub (ai-ops repo gets the issue traffic). User has to watch ai-ops repo (which they already do as owner).
- Reusable workflow tag pinning needs discipline: bumping tags is itself a change that should be reviewed.
- Ruleset JSON is GitHub-specific (no equivalent on GitLab / BitBucket); managed projects must be on GitHub. ADR 0009 already declared GitHub-only as a constraint, so consistent.
- Initial setup per managed project requires running 3 setup helpers (`setup-ci-workflow`, `setup-codeowners`, `setup-ruleset`) — could be combined into `ai-ops setup-managed --tier B` later.

Out of scope (deferred):

- GitHub Copilot Cloud Coding Agent integration (requires Pro+ plan; treat as Tier C optional enhancement)
- GitHub Pages / wiki / Discussions automation (use manually for now)
- GitLab / BitBucket support
- Auto-merge for `propagate-*` PRs (Renovate-style; can add later as `--auto-merge` flag)
- Webhook-based real-time notification (cron is sufficient given drift is rarely time-critical)
- Custom GitHub App / bot infrastructure (gh CLI + Actions covers what we need)

## Related

- ADR 0006: AI-first project lifecycle
- ADR 0008: Execution plan persistence  
- ADR 0009: Git workflow tiers (amended with GitHub-native profile reference)
- ADR 0010: Worktree-based parallel work
- `docs/plans/github-native-operation/plan.md`: implementation plan
- External: GitHub Issues + Sub-issues GA, Projects v2 hierarchy view, Repository Rulesets GA, reusable workflows + composite actions (May 2026 industry survey).

## Amendment 2026-05-03 (PR δ)

本 ADR 本文中の subcommand 例 (`propagate-anchor` / `propagate-init` / `propagate-files` / `setup-ci-workflow` / `setup-codeowners` / `setup-ruleset`) は執筆時点 (2026-05-02) の名称。PR α (2026-05-03) でそれぞれ `propagate --kind {anchor,init,files}` / `setup {ci,codeowners,ruleset}` に統合された (旧名は 1 リリース alias で残存、`audit lifecycle` の README claim verification が両方を verify)。

加えて Move 3 の "later 検討" 案 `ai-ops setup-managed --tier B` (一括 helper) は採用せず、`setup {ci,codeowners,ruleset}` の sub-subparser 統合を選択した。各 component を独立 callable に保つ方が、Tier ごとに適用範囲を分けたいときの柔軟性が高いため。
