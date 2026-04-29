# ai-ops Self-Operation Baseline

This ExecPlan was prepared, verified, and archived in the same session as evidence for the self-operation baseline. It is preserved here unchanged as the historical record.

Archive path: `docs/plans/archive/2026-04-29-ai-ops-self-operation/`. No active execution copy exists under `docs/plans/`.

## Purpose / Big Picture

ai-ops can now point to a repo-local self-operation guide and a file-by-file baseline audit when judging whether the project is release-ready or needs another dogfood pass.

## Progress

- [x] (2026-04-29 04:45Z) Inventory tracked files with `git ls-files`.
- [x] (2026-04-29 04:45Z) Inspect source, docs, templates, tests, packaging, Nix, and ignored generated artifacts.
- [x] (2026-04-29 04:45Z) Add `docs/self-operation.md` and link it from README / AGENTS.
- [x] (2026-04-29 04:45Z) Add file-by-file audit artifact.
- [x] (2026-04-29 04:45Z) Run final checks and record results in this archived plan before adoption.

## Surprises & Discoveries

- Observation: The tracked tree is already compact and no tracked deletion is recommended.
  Evidence: `git ls-files` reported 71 tracked files (including the three new self-operation artifacts added in this baseline); file-by-file audit found every tracked file has a current role.
- Observation: Generated artifacts exist locally but are ignored and deterministic.
  Evidence: `git status --short --ignored` showed `.direnv/`, `.pytest_cache/`, `__pycache__/`, `ai_ops.egg-info/`, `ai_ops/_resources/`, and `build/`.
- Observation: Nix flakes do not include untracked new files from a Git worktree source.
  Evidence: The first `direnv exec . nix flake check` failed because modified `lifecycle.py` required `docs/self-operation.md`, while that new file was still untracked. After `git add -N` on the new docs, the same check passed.

## Decision Log

- Decision: Add `docs/self-operation.md` as a load-bearing self-operation guide.
  Rationale: The release-ready gate and dogfood cadence are operational policy, not transient chat state.
  Date/Author: 2026-04-29 / Codex.
- Decision: Archive this baseline plan instead of leaving an active perpetual plan.
  Rationale: Ongoing operations belong in `docs/self-operation.md`; completed execution evidence belongs in `docs/plans/archive/`.
  Date/Author: 2026-04-29 / Codex.
- Decision: Apply the new "AGENTS.md should stay English" policy in the same diff that introduces it, rewriting the existing Japanese-mixed sentences to English and normalizing em-dashes to hyphens.
  Rationale: The policy text and its application live in one document; deferring the rewrite would leave AGENTS.md self-inconsistent the moment the policy is adopted. The hyphen normalization piggybacks because em-dashes were already being removed by recent Windows UTF-8 work in CLI output, and AGENTS.md was the last place mixing both styles.
  Date/Author: 2026-04-29 / Codex.

## Outcomes & Retrospective

Shipped:

- `docs/self-operation.md` as the durable self-operation guide.
- README / AGENTS links to the new guide.
- lifecycle audit now requires `docs/self-operation.md`.
- File-by-file baseline audit archived beside this plan.
- `.gitignore` covers Python coverage output and Nix `result` symlinks.

Verification:

- `python -m ai_ops check` passed: 99 tests passed, 1 slow test deselected; lifecycle audit PASS 33 / FAIL 0.
- `git diff --check` passed.
- `direnv exec . nix flake check` passed after marking the new files with `git add -N` so the Git-backed flake source could see them.

Remaining:

- No tracked file deletion or relocation is recommended.
- Optional OpenSSF Scorecard remains skipped locally because `scorecard` is not installed.

## Context and Orientation

Relevant source-of-truth files:

- `AGENTS.md` for AI operating rules.
- `README.md` / `README.ja.md` for user entrypoints.
- `docs/ai-first-lifecycle.md` for canonical lifecycle.
- `docs/self-operation.md` for ai-ops dogfood and release gate.
- `docs/plans/archive/2026-04-29-ai-ops-self-operation/file-audit.md` for this baseline file audit.

## Plan of Work

Add a durable self-operation guide, link it from the existing entrypoints, make lifecycle audit require the guide, and record a file-by-file baseline review. Keep edits documentation-first and avoid deleting generated local artifacts without a separate destructive-operation confirmation.

## Concrete Steps

1. Read every tracked file using `git ls-files` as the source file set.
2. Classify each tracked file by role, necessity, and placement.
3. Review ignored generated artifacts by deterministic category.
4. Add `docs/self-operation.md`.
5. Link it from `README.md`, `README.ja.md`, and `AGENTS.md`.
6. Rewrite the remaining Japanese-mixed sentences in `AGENTS.md` to English and normalize em-dashes to hyphens, in line with the newly added "AGENTS.md should stay English" policy.
7. Add `docs/self-operation.md` to `ai_ops.audit.lifecycle.REQUIRED_FILES`.
8. Extend `.gitignore` for Python coverage output (`.coverage`, `htmlcov/`) and Nix `result` symlinks.
9. Run required checks.

## Validation and Acceptance

Required before completion:

```sh
python -m ai_ops check
git diff --check
direnv exec . nix flake check
```

Success means all commands exit 0.

## Idempotence and Recovery

The changes are additive except `.gitignore` generated-artifact patterns. If a future audit disagrees, inspect with `git diff` and either amend the docs or delete the added files through normal Git deletion.

No ignored generated artifacts were deleted in this baseline.

## Artifacts and Notes

- File audit: `docs/plans/archive/2026-04-29-ai-ops-self-operation/file-audit.md`.
- Tracked file count after this baseline lands: 71 (68 pre-existing + `docs/self-operation.md` + this `plan.md` + `file-audit.md`).
- Ignored generated categories observed: `.direnv/`, `.pytest_cache/`, `__pycache__/`, `ai_ops.egg-info/`, `ai_ops/_resources/`, `build/`.

## Interfaces and Dependencies

This baseline changes docs and lifecycle audit expectations only. It does not add CLI commands, public config formats, runtime dependencies, or cross-repo harness files.
