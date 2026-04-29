# Repository File Audit — 2026-04-29

Scope: every tracked file from `git ls-files` was reviewed one by one (71 files at the time of audit, including the three new self-operation artifacts added in the same baseline). Ignored generated files were reviewed by deterministic category because they are not source-of-truth files and some are binary cache artifacts.

Result: no tracked file is recommended for deletion or relocation. The tree is compact; the main improvement is making self-operation explicit.

## Tracked Files

| Path | Role | Necessity | Placement verdict |
|---|---|---|---|
| `.envrc` | Local direnv entry for the Nix dev shell. | Required for the documented Nix workflow. | Correct at repo root. |
| `.github/workflows/ci.yml` | GitHub Actions matrix for Python and Nix checks. | Required for public release readiness. | Correct under `.github/workflows/`. |
| `.gitignore` | Keeps local caches, build output, and generated bundled resources out of Git. | Required. Updated with coverage and Nix result outputs. | Correct at repo root. |
| `AGENTS.md` | Cross-agent source of truth. | Required by ADR 0001 and lifecycle audit. | Correct at repo root. |
| `CLAUDE.md` | Claude Code adapter that points to `AGENTS.md`. | Required for tool portability with negligible cost. | Correct at repo root. |
| `LICENSE` | MIT license for T1 public repo. | Required for public use. | Correct at repo root. |
| `README.md` | English public entrypoint. | Required; GitHub renders this first. | Correct at repo root. |
| `README.ja.md` | Japanese sibling README. | Required for current user/operator language. | Correct as sibling to `README.md`. |
| `ai_ops/__init__.py` | Package marker and version. | Required for import/package behavior. | Correct in package root. |
| `ai_ops/__main__.py` | `python -m ai_ops` entrypoint. | Required by README and CI. | Correct in package root. |
| `ai_ops/agents/__init__.py` | Public exports for agent adapters. | Useful package boundary. | Correct in `agents/`. |
| `ai_ops/agents/base.py` | Agent protocol. | Required abstraction for prompt-only/subprocess adapters. | Correct in `agents/`. |
| `ai_ops/agents/prompt_only.py` | Built-in no-AI fallback. | Required for portability and dry-run workflows. | Correct in `agents/`. |
| `ai_ops/agents/subprocess.py` | External AI CLI adapter. | Required for configured Claude/Codex invocation. | Correct in `agents/`. |
| `ai_ops/audit/__init__.py` | Audit package marker. | Required package structure. | Correct in `audit/`. |
| `ai_ops/audit/harness.py` | Harness drift detector. | Required by documented `audit harness`. | Correct in `audit/`. |
| `ai_ops/audit/lifecycle.py` | ai-ops structural self-audit. | Required by `ai-ops check`; now also protects `docs/self-operation.md`. | Correct in `audit/`. |
| `ai_ops/audit/nix.py` | Nix adoption rubric and reports. | Required by ADR 0005 and CLI. | Correct in `audit/`. |
| `ai_ops/audit/security.py` | Built-in and gitleaks-backed security audit. | Required for T1 safety gate. | Correct in `audit/`. |
| `ai_ops/audit/standard.py` | ADR drift audit. | Required by documented `audit standard`. | Correct in `audit/`. |
| `ai_ops/bootstrap.py` | Tool bootstrap/update operation. | Required by README and ADR 0002 amendment. | Correct in package root; broad enough to remain one module. |
| `ai_ops/checks/__init__.py` | Checks package marker. | Required package structure. | Correct in `checks/`. |
| `ai_ops/checks/runner.py` | `ai-ops check` orchestration. | Required completion gate. | Correct in `checks/`. |
| `ai_ops/cli.py` | CLI parser and handlers. | Required primary command surface. | Correct in package root. |
| `ai_ops/config.py` | Agent config resolution. | Required by CLI. | Correct in package root. |
| `ai_ops/lifecycle/__init__.py` | Lifecycle package marker. | Required package structure. | Correct in `lifecycle/`. |
| `ai_ops/lifecycle/migration.py` | Migration prompt discovery and assembly. | Required by `ai-ops migrate`. | Correct in `lifecycle/`. |
| `ai_ops/lifecycle/plans.py` | `promote-plan` implementation. | Required by ADR 0008. | Correct in `lifecycle/`. |
| `ai_ops/lifecycle/project.py` | New-project prompt and brief draft assembly. | Required by `ai-ops new`. | Correct in `lifecycle/`. |
| `ai_ops/lifecycle/prompts.py` | Shared prompt templates and Nix rubric text. | Required by new/migrate prompt assembly. | Correct in `lifecycle/`. |
| `ai_ops/models.py` | Small dataclasses for command specs/results. | Required shared model layer. | Correct in package root. |
| `ai_ops/paths.py` | Source/bundled resource resolution. | Required for source, wheel, and Nix execution. | Correct in package root. |
| `ai_ops/process.py` | UTF-8 subprocess wrapper. | Required shared utility. | Correct in package root. |
| `docs/ai-first-lifecycle.md` | Canonical lifecycle. | Required by README and AGENTS. | Correct in `docs/`. |
| `docs/decisions/0001-agents-md-as-primary.md` | ADR for AGENTS.md source of truth. | Required historical decision. | Correct in `docs/decisions/`. |
| `docs/decisions/0002-portability-first.md` | ADR for no silent environment mutation. | Required safety contract. | Correct in `docs/decisions/`. |
| `docs/decisions/0003-deletion-policy.md` | ADR for recovery-first deletion. | Required safety contract. | Correct in `docs/decisions/`. |
| `docs/decisions/0004-secrets-management.md` | ADR for keeping secrets out of AI context. | Required T1 safety contract. | Correct in `docs/decisions/`. |
| `docs/decisions/0005-nix-optional-reproducibility-layer.md` | ADR for default-required Nix reproducibility. | Required despite legacy filename wording; content is amended. | Correct in `docs/decisions/`; rename would add churn without value. |
| `docs/decisions/0006-ai-first-project-lifecycle.md` | ADR for lifecycle model. | Required. | Correct in `docs/decisions/`. |
| `docs/decisions/0007-python-canonical-cli.md` | ADR for Python CLI implementation. | Required and lifecycle-audited. | Correct in `docs/decisions/`. |
| `docs/decisions/0008-plan-persistence.md` | ADR for repo-local plans. | Required and lifecycle-audited. | Correct in `docs/decisions/`. |
| `docs/plans/.gitkeep` | Keeps active plan directory present when empty. | Useful because `docs/plans/` is part of the model. | Correct. |
| `docs/plans/archive/.gitkeep` | Keeps archive directory present when empty. | Useful because archive path is documented. | Correct. |
| `docs/plans/archive/2026-04-29-ai-ops-self-operation/file-audit.md` | This audit. | Required as evidence for the self-operation baseline. | Correct under archived plan directory. |
| `docs/plans/archive/2026-04-29-ai-ops-self-operation/plan.md` | Archived self-operation baseline ExecPlan. | Required as evidence for the self-operation baseline. | Correct under archived plan directory. |
| `docs/project-addition-and-migration.md` | Detailed project/migration guide. | Required by README and AGENTS. | Correct in `docs/`. |
| `docs/self-operation.md` | Durable self-operation guide (release gate, dogfood checks, drift review, file hygiene). | Required by AGENTS.md and lifecycle audit. | Correct in `docs/`. |
| `flake.lock` | Pins Nix dependency universe. | Required by ADR 0005 and reproducibility. | Correct at repo root. |
| `flake.nix` | Dev shell, apps, and checks. | Required release gate. | Correct at repo root. |
| `pyproject.toml` | Canonical Python package metadata. | Required for packaging and tests. | Correct at repo root. |
| `setup.py` | Build hook that bundles top-level AGENTS/templates into wheel resources. | Required; not redundant with `pyproject.toml`. | Correct at repo root. |
| `templates/agent-handoff.md` | Handoff template. | Required lifecycle artifact. | Correct in `templates/`. |
| `templates/artifacts/.envrc` | Target-project direnv artifact. | Required by Nix retrofit flow. | Correct in `templates/artifacts/`. |
| `templates/artifacts/flake.nix.minimal` | Minimal Nix template. | Required by Nix rubric fallback. | Correct in `templates/artifacts/`. |
| `templates/artifacts/flake.nix.node` | Node Nix template. | Required by Nix rubric. | Correct in `templates/artifacts/`. |
| `templates/artifacts/flake.nix.python` | Python Nix template. | Required by Nix rubric. | Correct in `templates/artifacts/`. |
| `templates/artifacts/flake.nix.xmake` | xmake / embedded Nix template. | Required by Nix rubric. | Correct in `templates/artifacts/`. |
| `templates/artifacts/renovate.json` | Dependency update template. | Required by lockfile cadence guidance. | Correct in `templates/artifacts/`. |
| `templates/artifacts/update-flake-lock.yml` | Fallback lock update workflow template. | Required for non-Renovate cases. | Correct in `templates/artifacts/`. |
| `templates/migration-brief.md` | Migration brief schema. | Required by lifecycle and CLI. | Correct in `templates/`. |
| `templates/plan.md` | Execution plan schema. | Required by ADR 0008. | Correct in `templates/`. |
| `templates/project-brief.md` | New project brief schema. | Required by lifecycle and CLI. | Correct in `templates/`. |
| `tests/test_audit.py` | Nix/security/lifecycle audit tests. | Required behavior coverage. | Correct in `tests/`. |
| `tests/test_audit_harness.py` | Harness drift tests. | Required coverage for `audit harness`. | Correct in `tests/`. |
| `tests/test_audit_standard.py` | ADR drift tests. | Required coverage for `audit standard`. | Correct in `tests/`. |
| `tests/test_bootstrap.py` | Bootstrap/update tests. | Required coverage for installer safety. | Correct in `tests/`. |
| `tests/test_cli.py` | CLI behavior and prompt assembly tests. | Required command-surface coverage. | Correct in `tests/`. |
| `tests/test_config.py` | Agent config tests. | Required config precedence coverage. | Correct in `tests/`. |
| `tests/test_packaging.py` | Non-editable install smoke test. | Required because packaging resources are non-standard. | Correct in `tests/`; marked slow. |
| `tests/test_paths.py` | Resource path resolution tests. | Required for Nix/wheel/source execution. | Correct in `tests/`. |

## Ignored Generated Files Observed

| Path/category | Role | Necessity | Action |
|---|---|---|---|
| `.direnv/` | direnv/Nix local state. | Not source of truth. | Keep ignored. Do not commit. |
| `.pytest_cache/` | pytest local cache. | Not source of truth. | Keep ignored. Can be regenerated. |
| `ai_ops.egg-info/` | editable/install metadata. | Not source of truth. | Keep ignored. Can be regenerated. |
| `ai_ops/_resources/` | build-time bundled copy of `AGENTS.md` and `templates/`. | Generated by `setup.py`; source is top-level files. | Keep ignored. Do not edit directly. |
| `build/` | packaging build output. | Not source of truth. | Keep ignored. Can be regenerated. |
| `ai_ops/**/__pycache__/`, `tests/__pycache__/` | Python bytecode caches. | Not source of truth. | Keep ignored. Can be regenerated. |

## Recommendations

- Keep all tracked files.
- Keep current placement; the package/docs/templates/tests boundaries are coherent.
- Treat `docs/self-operation.md` as the durable operational entrypoint for this repo's own dogfood loop.
- Do not turn generated artifact cleanup into a default check; `python -m ai_ops check` and packaging smoke tests legitimately create caches/build output.
