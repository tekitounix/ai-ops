from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ai_ops.agents.prompt_only import PromptOnlyAgent
from ai_ops.agents.subprocess import SubprocessAgent
from ai_ops.audit.projects import run_projects_audit
from ai_ops.audit.harness import run_harness_audit
from ai_ops.audit.lifecycle import run_lifecycle_audit
from ai_ops.audit.nix import run_nix_audit, run_nix_propose, run_nix_report
from ai_ops.audit.security import run_security_audit
from ai_ops.audit.standard import run_standard_audit
from ai_ops.bootstrap import (
    install_pre_push_hook,
    run_install,
    run_install_secrets,
    run_update,
)
from ai_ops.checks.runner import run_check
from ai_ops.config import load_agent_config
from ai_ops.lifecycle.migration import build_migration_prompt
from ai_ops.lifecycle.plans import run_promote_plan
from ai_ops.propagate import (
    run_propagate_anchor,
    run_propagate_files,
    run_propagate_init,
)
from ai_ops.report import run_report_drift
from ai_ops.review import run_review_cost, run_review_pr
from ai_ops.setup import (
    VALID_TIERS,
    run_setup_ci_workflow,
    run_setup_codeowners,
    run_setup_ecosystem,
    run_setup_ruleset,
)
from ai_ops.worktree import (
    DEFAULT_BRANCH_TYPE,
    VALID_BRANCH_TYPES,
    run_worktree_cleanup,
    run_worktree_new,
)
from ai_ops.lifecycle.project import build_project_prompt, draft_project_brief
from ai_ops.models import MigrationSpec, ProjectSpec
from ai_ops.paths import package_root


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_io()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 0
    target_root = Path.cwd().resolve()
    return args.handler(args, target_root)


def _ensure_utf8_io() -> None:
    """Force UTF-8 on stdout/stderr (Windows only).

    AGENTS.md and the NIX_RUBRIC contain Japanese characters that the
    Windows console codepage (cp1252 / cp932) cannot encode, so any
    `print(prompt)` would crash with UnicodeEncodeError. POSIX terminals
    already default to UTF-8, so this is a no-op there.
    """
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-ops")
    sub = parser.add_subparsers(dest="command")

    new = sub.add_parser("new", help="Prepare an AI-first new-project prompt/brief")
    new.add_argument("name", nargs="?")
    new.add_argument("--purpose", default="")
    new.add_argument("--agent")
    new.add_argument("--interactive", action="store_true")
    new.add_argument("--tier", choices=("T1", "T2", "T3"), default="T3")
    new.add_argument("--type", dest="project_type", choices=("global", "monorepo", "stm32"), default="global")
    new.add_argument(
        "--nix",
        dest="nix_level",
        choices=("auto", "none", "devshell", "apps", "full"),
        default="auto",
        help="Nix level (default 'auto' = AI agent decides via per-project rubric, ADR 0005)",
    )
    new.add_argument("--output", type=Path)
    new.add_argument("--dry-run", action="store_true")
    new.set_defaults(handler=handle_new)

    migrate = sub.add_parser("migrate", help="Prepare an AI-first migration prompt")
    migrate.add_argument("source", nargs="?")
    migrate.add_argument("--agent")
    migrate.add_argument("--interactive", action="store_true")
    migrate.add_argument("--tier", choices=("T1", "T2", "T3"), default="T3")
    migrate.add_argument(
        "--nix",
        dest="nix_level",
        choices=("auto", "none", "devshell", "apps", "full"),
        default="auto",
        help="Nix level (default 'auto' = AI agent decides via per-project rubric, ADR 0005)",
    )
    migrate.add_argument("--output", type=Path)
    migrate.add_argument("--dry-run", action="store_true")
    migrate.add_argument(
        "--retrofit-nix",
        action="store_true",
        help="Narrow scope to Nix retrofit only (add flake.nix to an already-managed project)",
    )
    migrate.add_argument(
        "--update-harness",
        action="store_true",
        help="Narrow scope to harness drift remediation (restore missing/modified files via audit harness)",
    )
    migrate.set_defaults(handler=handle_migrate)

    check = sub.add_parser("check", help="Run ai-ops repository checks")
    check.set_defaults(handler=lambda _args, root: run_check(root))

    audit = sub.add_parser("audit", help="Run read-only audits")
    audit.add_argument(
        "kind",
        nargs="?",
        choices=("lifecycle", "nix", "security", "harness", "standard", "projects"),
        default="lifecycle",
    )
    audit.add_argument(
        "--report",
        action="store_true",
        help="Nix only: walk ghq list -p and print a Nix-gap table for every project",
    )
    audit.add_argument(
        "--propose",
        type=Path,
        metavar="PATH",
        help="Nix only: emit Markdown retrofit proposal for a single project",
    )
    audit.add_argument(
        "--path",
        type=Path,
        metavar="PATH",
        help="Harness / Standard only: target project path (default: cwd)",
    )
    audit.add_argument(
        "--strict",
        action="store_true",
        help="Harness only: treat manifest absence (with harness files present) as failure",
    )
    audit.add_argument(
        "--json",
        action="store_true",
        help="Projects only: emit JSON instead of the text table",
    )
    audit.add_argument(
        "--priority",
        choices=("P0", "P1", "P2", "all"),
        default="all",
        help="Projects only: filter rows by priority (default: all)",
    )
    audit.add_argument(
        "--since",
        metavar="REF",
        help="Standard only: ai-ops git ref to compare against (default: project's manifest sha or HEAD~100)",
    )
    audit.set_defaults(handler=handle_audit)

    bootstrap = sub.add_parser(
        "bootstrap",
        help="Survey and (with user confirmation) install required tools (ADR 0002 amendment)",
    )
    bootstrap.add_argument(
        "--tier",
        type=int,
        choices=(1, 2),
        default=1,
        help="Install tools at or below this tier (default 1 = required only)",
    )
    bootstrap.add_argument("--dry-run", action="store_true")
    bootstrap.add_argument(
        "--yes", "-y", dest="yes", action="store_true",
        help="Skip confirmation prompts (declares prior approval; ADR 0004)",
    )
    # PR α: Bitwarden 経由の secrets 登録 (ai-ops review-pr 等で使う API key)
    bootstrap.add_argument(
        "--with-secrets", dest="with_secrets", action="store_true",
        help="In addition to tools, register API key secrets to a GitHub repo "
             "via Bitwarden + gh secret set (requires BW_SESSION env var)",
    )
    bootstrap.add_argument(
        "--repo", default=None,
        help="Target GitHub repo (owner/name) for --with-secrets",
    )
    bootstrap.add_argument(
        "--bw-anthropic-item", dest="bw_anthropic_item", default=None,
        help="Bitwarden item name holding the Anthropic API key",
    )
    bootstrap.add_argument(
        "--bw-openai-item", dest="bw_openai_item", default=None,
        help="Bitwarden item name holding the OpenAI API key",
    )
    bootstrap.add_argument(
        "--bw-field", dest="bw_field", default="api_key",
        help="Bitwarden field name to read (default: api_key; falls back to login.password)",
    )
    # PR γ: optional pre-push hook install
    bootstrap.add_argument(
        "--with-pre-push-hook", dest="with_pre_push_hook", action="store_true",
        help="In addition to tools, install ai-ops pre-push hook (branch-name + "
             "Tier B/C main-push checks) into the project's .git/hooks/pre-push",
    )
    bootstrap.add_argument(
        "--project", type=Path, default=None,
        help="Path to the project for --with-pre-push-hook (default: cwd)",
    )
    bootstrap.set_defaults(handler=handle_bootstrap)

    update = sub.add_parser(
        "update",
        help="Survey and (with user confirmation) update present tools",
    )
    update.add_argument(
        "--tier",
        type=int,
        choices=(1, 2),
        default=2,
        help="Update tools at or below this tier (default 2 = include recommended)",
    )
    update.add_argument("--dry-run", action="store_true")
    update.set_defaults(handler=handle_update)

    promote = sub.add_parser(
        "promote-plan",
        help="Promote a user-selected local AI plan into docs/plans/<slug>/plan.md",
    )
    promote.add_argument("slug")
    promote.add_argument(
        "--source",
        type=Path,
        help="Local AI plan to read (default: ~/.claude/plans/<slug>.md)",
    )
    promote.add_argument("--dry-run", action="store_true")
    promote.set_defaults(handler=handle_promote_plan)

    # 統合: `ai-ops propagate --kind {anchor,init,files}` (PR α)
    propagate = sub.add_parser(
        "propagate",
        help="Open PRs that propagate ai-ops state to managed projects (ADR 0011)",
    )
    propagate.add_argument(
        "--kind", required=True, choices=("anchor", "init", "files"),
        help="What to propagate: anchor (bump ai_ops_sha), init (commit "
             "untracked harness.toml), files (refresh [harness_files] hashes)",
    )
    p_group = propagate.add_mutually_exclusive_group(required=True)
    p_group.add_argument(
        "--all", dest="all_projects", action="store_true",
        help="Process every managed project under ghq",
    )
    p_group.add_argument(
        "--project", type=Path,
        help="Process a single project at the given path",
    )
    propagate.add_argument("--dry-run", action="store_true")
    propagate.add_argument(
        "--auto-yes", dest="auto_yes", action="store_true",
        help="Skip per-project confirmation (CI use; ADR 0011)",
    )
    propagate.set_defaults(handler=handle_propagate)

    # --- 旧 alias (1 リリース猶予、deprecation 警告付き) ---
    propagate_anchor = sub.add_parser(
        "propagate-anchor",
        help="[DEPRECATED] Use `ai-ops propagate --kind anchor`",
    )
    pa_group = propagate_anchor.add_mutually_exclusive_group(required=True)
    pa_group.add_argument(
        "--all", dest="all_projects", action="store_true",
        help="Process every managed project under ghq",
    )
    pa_group.add_argument(
        "--project", type=Path,
        help="Process a single project at the given path",
    )
    propagate_anchor.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen, write nothing, no network calls",
    )
    propagate_anchor.add_argument(
        "--auto-yes", dest="auto_yes", action="store_true",
        help="Skip per-project confirmation; the workflow file invoking "
             "this command is treated as the user's prior approval (ADR 0011)",
    )
    propagate_anchor.set_defaults(handler=handle_propagate_anchor)

    propagate_init = sub.add_parser(
        "propagate-init",
        help="[DEPRECATED] Use `ai-ops propagate --kind init`",
    )
    pi_group = propagate_init.add_mutually_exclusive_group(required=True)
    pi_group.add_argument(
        "--all", dest="all_projects", action="store_true",
        help="Process every managed project under ghq",
    )
    pi_group.add_argument(
        "--project", type=Path,
        help="Process a single project at the given path",
    )
    propagate_init.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen, write nothing, no network calls",
    )
    propagate_init.add_argument(
        "--auto-yes", dest="auto_yes", action="store_true",
        help="Skip per-project confirmation (CI use; ADR 0011)",
    )
    propagate_init.set_defaults(handler=handle_propagate_init)

    propagate_files = sub.add_parser(
        "propagate-files",
        help="[DEPRECATED] Use `ai-ops propagate --kind files`",
    )
    pf_group = propagate_files.add_mutually_exclusive_group(required=True)
    pf_group.add_argument(
        "--all", dest="all_projects", action="store_true",
        help="Process every managed project under ghq",
    )
    pf_group.add_argument(
        "--project", type=Path,
        help="Process a single project at the given path",
    )
    propagate_files.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen, write nothing, no network calls",
    )
    propagate_files.add_argument(
        "--auto-yes", dest="auto_yes", action="store_true",
        help="Skip per-project confirmation (CI use; ADR 0011)",
    )
    propagate_files.set_defaults(handler=handle_propagate_files)

    # 統合: `ai-ops worktree {new,cleanup}` (PR α)
    worktree = sub.add_parser(
        "worktree",
        help="Manage sibling worktrees with 1:1:1 plan/branch/worktree binding (ADR 0010)",
    )
    wt_sub = worktree.add_subparsers(dest="wt_command")
    wt_n = wt_sub.add_parser("new", help="Create a sibling worktree + branch + plan skeleton")
    wt_n.add_argument("slug", help="Plan slug (also used in branch + worktree path)")
    wt_n.add_argument(
        "--type", dest="branch_type", default=DEFAULT_BRANCH_TYPE,
        choices=list(VALID_BRANCH_TYPES),
        help=f"Branch type prefix (default: {DEFAULT_BRANCH_TYPE})",
    )
    wt_n.add_argument(
        "--base", dest="base_branch", default="main",
        help="Base branch to branch from (default: main)",
    )
    wt_n.add_argument("--dry-run", action="store_true")
    wt_n.set_defaults(handler=handle_worktree_new)
    wt_c = wt_sub.add_parser(
        "cleanup",
        help="Remove worktrees whose PR is merged AND plan is archived",
    )
    wt_c.add_argument(
        "--auto", action="store_true",
        help="Skip per-worktree confirmation; remove all eligible worktrees",
    )
    wt_c.add_argument(
        "--auto-archive", dest="auto_archive", action="store_true",
        help="For Tier A / unmanaged repos, auto-archive plans of merged PRs "
             "before cleanup (git mv + commit + push). Tier B/C is skipped "
             "with a warning to use a PR instead (ADR 0010 §Lifecycle 4)",
    )
    wt_c.add_argument("--dry-run", action="store_true")
    wt_c.set_defaults(handler=handle_worktree_cleanup)

    # --- 旧 alias (1 リリース猶予、deprecation 警告付き) ---
    wt_new = sub.add_parser(
        "worktree-new",
        help="[DEPRECATED] Use `ai-ops worktree new`",
    )
    wt_new.add_argument("slug", help="Plan slug (also used in branch + worktree path)")
    wt_new.add_argument(
        "--type", dest="branch_type", default=DEFAULT_BRANCH_TYPE,
        choices=list(VALID_BRANCH_TYPES),
        help=f"Branch type prefix (default: {DEFAULT_BRANCH_TYPE})",
    )
    wt_new.add_argument(
        "--base", dest="base_branch", default="main",
        help="Base branch to branch from (default: main)",
    )
    wt_new.add_argument("--dry-run", action="store_true")
    wt_new.set_defaults(handler=handle_worktree_new)

    wt_cleanup = sub.add_parser(
        "worktree-cleanup",
        help="[DEPRECATED] Use `ai-ops worktree cleanup`",
    )
    wt_cleanup.add_argument(
        "--auto", action="store_true",
        help="Skip per-worktree confirmation; remove all eligible worktrees",
    )
    wt_cleanup.add_argument("--dry-run", action="store_true")
    wt_cleanup.set_defaults(handler=handle_worktree_cleanup)

    report_drift = sub.add_parser(
        "report-drift",
        help="Translate audit projects output into ai-ops repo sub-issues (ADR 0011)",
    )
    report_drift.add_argument(
        "--repo", default="tekitounix/ai-ops",
        help="ai-ops repo (owner/name) whose Issues host the dashboard "
             "(default: tekitounix/ai-ops)",
    )
    report_drift.add_argument(
        "--audit-json", type=Path, default=None,
        help="Read audit projects JSON from this path instead of running it inline",
    )
    report_drift.add_argument("--dry-run", action="store_true")
    report_drift.set_defaults(handler=handle_report_drift)

    # 統合: `ai-ops setup {ci,codeowners,ruleset}` (PR α)
    setup_p = sub.add_parser(
        "setup",
        help="Configure ai-ops integration in a managed project (ADR 0011)",
    )
    su_sub = setup_p.add_subparsers(dest="setup_component")

    su_ci = su_sub.add_parser(
        "ci", help="Open a PR adding `.github/workflows/ai-ops.yml`",
    )
    su_ci.add_argument("--project", type=Path, required=True)
    su_ci.add_argument(
        "--tier", default="D", choices=list(VALID_TIERS) + ["D"],
        help="Tier (A/B/C/D) — sets `tier:` input in the workflow caller",
    )
    su_ci.add_argument(
        "--ai-ops-ref", dest="ai_ops_ref", default="main",
        help="ai-ops branch / tag the workflow will install from (default: main)",
    )
    su_ci.add_argument("--dry-run", action="store_true")
    su_ci.set_defaults(handler=handle_setup_ci_workflow)

    su_co = su_sub.add_parser(
        "codeowners", help="Open a PR adding `.github/CODEOWNERS`",
    )
    su_co.add_argument("--project", type=Path, required=True)
    su_co.add_argument(
        "--owner", default=None,
        help="GitHub username to route reviews to (default: project's repo owner)",
    )
    su_co.add_argument("--dry-run", action="store_true")
    su_co.set_defaults(handler=handle_setup_codeowners)

    su_rs = su_sub.add_parser(
        "ruleset", help="Apply a tier ruleset via `gh api`",
    )
    su_rs.add_argument("--project", type=Path, required=True)
    su_rs.add_argument(
        "--tier", required=True, choices=list(VALID_TIERS),
        help="Tier (A/B/C) — selects the ruleset profile",
    )
    su_rs.add_argument("--dry-run", action="store_true")
    su_rs.set_defaults(handler=handle_setup_ruleset)

    su_eco = su_sub.add_parser(
        "ecosystem",
        help="Create the Ecosystem dashboard parent issue for a project (PR ε, ADR 0011)",
    )
    su_eco.add_argument(
        "--project-name", required=True,
        help="Project slug as it should appear in 'Ecosystem: <name>' issue title",
    )
    su_eco.add_argument(
        "--ai-ops-repo", dest="ai_ops_repo", default="tekitounix/ai-ops",
        help="ai-ops repo (owner/name) hosting the dashboard (default: tekitounix/ai-ops)",
    )
    su_eco.add_argument(
        "--owner", default=None,
        help="Optional GitHub username to assign as parent-issue owner",
    )
    su_eco.add_argument("--dry-run", action="store_true")
    su_eco.set_defaults(handler=handle_setup_ecosystem)

    # --- 旧 alias (1 リリース猶予、deprecation 警告付き) ---
    setup_ci = sub.add_parser(
        "setup-ci-workflow",
        help="[DEPRECATED] Use `ai-ops setup ci`",
    )
    setup_ci.add_argument(
        "--project", type=Path, required=True,
        help="Path to the managed project (must be a GitHub repo)",
    )
    setup_ci.add_argument(
        "--tier", default="D", choices=list(VALID_TIERS) + ["D"],
        help="Tier (A/B/C/D) — sets `tier:` input in the workflow caller",
    )
    setup_ci.add_argument(
        "--ai-ops-ref", dest="ai_ops_ref", default="main",
        help="ai-ops branch / tag the workflow will install from (default: main)",
    )
    setup_ci.add_argument("--dry-run", action="store_true")
    setup_ci.set_defaults(handler=handle_setup_ci_workflow)

    setup_co = sub.add_parser(
        "setup-codeowners",
        help="[DEPRECATED] Use `ai-ops setup codeowners`",
    )
    setup_co.add_argument(
        "--project", type=Path, required=True,
        help="Path to the managed project (must be a GitHub repo)",
    )
    setup_co.add_argument(
        "--owner", default=None,
        help="GitHub username to route reviews to (default: project's repo owner)",
    )
    setup_co.add_argument("--dry-run", action="store_true")
    setup_co.set_defaults(handler=handle_setup_codeowners)

    setup_rs = sub.add_parser(
        "setup-ruleset",
        help="[DEPRECATED] Use `ai-ops setup ruleset`",
    )
    setup_rs.add_argument(
        "--project", type=Path, required=True,
        help="Path to the managed project (must be a GitHub repo)",
    )
    setup_rs.add_argument(
        "--tier", required=True, choices=list(VALID_TIERS),
        help="Tier (A/B/C) — selects the ruleset profile",
    )
    setup_rs.add_argument("--dry-run", action="store_true")
    setup_rs.set_defaults(handler=handle_setup_ruleset)

    review_cost = sub.add_parser(
        "review-cost",
        help="Show monthly LLM-review cost summary from local cache (PR ε)",
    )
    review_cost.add_argument(
        "--month", default=None,
        help="Month to summarize as YYYY-MM (default: current month UTC)",
    )
    review_cost.set_defaults(handler=handle_review_cost)

    review = sub.add_parser(
        "review-pr",
        help="Review a PR against ai-ops contracts using an LLM (ADR 0012)",
    )
    review.add_argument(
        "--pr", type=int, required=True,
        help="Pull request number to review",
    )
    review.add_argument(
        "--repo", default=None,
        help="GitHub repo (owner/name); defaults to cwd's origin",
    )
    review.add_argument(
        "--provider", default="auto", choices=("auto", "anthropic", "openai"),
        help="LLM provider to use (default: auto = ANTHROPIC > OPENAI by env var)",
    )
    review.add_argument("--dry-run", action="store_true")
    review.set_defaults(handler=handle_review_pr)

    return parser


def handle_new(args: argparse.Namespace, root: Path) -> int:
    name = args.name or _ask("Project name") if args.interactive else args.name
    purpose = args.purpose or _ask("One-line purpose") if args.interactive else args.purpose
    if not name:
        print("Error: project name is required unless --interactive is used", file=sys.stderr)
        return 2
    if not purpose:
        print("Error: --purpose is required unless --interactive is used", file=sys.stderr)
        return 2

    spec = ProjectSpec(
        name=name,
        purpose=purpose,
        tier=args.tier,
        project_type=args.project_type,
        nix_level=args.nix_level,
        output=args.output,
    )
    prompt = build_project_prompt(spec, root=package_root())
    brief = draft_project_brief(spec)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(brief, encoding="utf-8")
        print(f"Wrote project brief draft: {args.output}")

    if args.dry_run:
        print(prompt)
        print("\n--- Draft brief ---\n")
        print(brief)
        return 0

    agent = resolve_agent(root, args.agent)
    result = agent.run(prompt, cwd=root)
    if agent.name == "prompt-only":
        print(result.text)
        print("\n--- Draft brief ---\n")
        print(brief)
        return 0

    print(result.text)
    print("\nAgent run finished. Review the proposal/output and current git status before continuing.")
    return 0


def handle_migrate(args: argparse.Namespace, root: Path) -> int:
    source_text = args.source or _ask("Source path") if args.interactive else args.source
    if not source_text:
        print("Error: source path is required unless --interactive is used", file=sys.stderr)
        return 2
    source = Path(source_text).expanduser().resolve()
    spec = MigrationSpec(source=source, tier=args.tier, nix_level=args.nix_level, output=args.output)
    prompt = build_migration_prompt(
        spec,
        root=package_root(),
        retrofit_nix=getattr(args, "retrofit_nix", False),
        update_harness=getattr(args, "update_harness", False),
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(prompt, encoding="utf-8")
        print(f"Wrote migration prompt: {args.output}")

    agent = resolve_agent(root, args.agent)
    if args.dry_run or agent.name == "prompt-only":
        print(prompt)
        return 0

    result = agent.run(prompt, cwd=root)
    print(result.text)
    print("\nAgent run finished. Review the proposal/output and current git status before continuing.")
    return 0


def handle_audit(args: argparse.Namespace, root: Path) -> int:
    if args.kind == "lifecycle":
        return run_lifecycle_audit(root)
    if args.kind == "nix":
        if args.propose:
            return run_nix_propose(args.propose.resolve())
        if args.report:
            return run_nix_report()
        return run_nix_audit(root)
    if args.kind == "security":
        return run_security_audit(root)
    if args.kind == "harness":
        target = (args.path.resolve() if args.path else root)
        return run_harness_audit(
            target,
            package_root(),
            strict=getattr(args, "strict", False),
        )
    if args.kind == "standard":
        target = (args.path.resolve() if args.path else None)
        return run_standard_audit(
            package_root(),
            project_root=target,
            since_ref=args.since,
        )
    if args.kind == "projects":
        return run_projects_audit(
            json_output=getattr(args, "json", False),
            priority_filter=getattr(args, "priority", "all"),
        )
    raise AssertionError(args.kind)


def handle_bootstrap(args: argparse.Namespace, root: Path) -> int:
    rc = run_install(tier_max=args.tier, dry_run=args.dry_run, yes=args.yes)
    if args.with_secrets:
        if not args.repo:
            print("Error: --with-secrets requires --repo OWNER/NAME", file=sys.stderr)
            return 2
        secrets_rc = run_install_secrets(
            repo=args.repo,
            anthropic_item=args.bw_anthropic_item,
            openai_item=args.bw_openai_item,
            bw_field=args.bw_field,
            dry_run=args.dry_run,
            yes=args.yes,
        )
        rc = rc or secrets_rc
    if args.with_pre_push_hook:
        project = (args.project or root).resolve()
        hook_rc = install_pre_push_hook(
            project=project, dry_run=args.dry_run, yes=args.yes,
        )
        rc = rc or hook_rc
    return rc


def handle_update(args: argparse.Namespace, _root: Path) -> int:
    return run_update(tier_max=args.tier, dry_run=args.dry_run)


def handle_promote_plan(args: argparse.Namespace, root: Path) -> int:
    return run_promote_plan(
        root=root,
        slug=args.slug,
        source=args.source,
        dry_run=args.dry_run,
    )


def handle_propagate(args: argparse.Namespace, root: Path) -> int:
    """統合 propagate handler。`--kind` で 3 種を振り分ける。"""
    runner = {
        "anchor": run_propagate_anchor,
        "init": run_propagate_init,
        "files": run_propagate_files,
    }[args.kind]
    return runner(
        ai_ops_root=root,
        project=args.project,
        all_projects=args.all_projects,
        dry_run=args.dry_run,
        auto_yes=args.auto_yes,
    )


def _deprecation_notice(old: str, new: str) -> None:
    """旧 subcommand 使用時に stderr へ deprecation 警告を出す。"""
    print(
        f"warning: `ai-ops {old}` is deprecated, use `ai-ops {new}` instead "
        "(removed in next minor release).",
        file=sys.stderr,
    )


def handle_propagate_anchor(args: argparse.Namespace, root: Path) -> int:
    _deprecation_notice("propagate-anchor", "propagate --kind anchor")
    return run_propagate_anchor(
        ai_ops_root=root,
        project=args.project,
        all_projects=args.all_projects,
        dry_run=args.dry_run,
        auto_yes=args.auto_yes,
    )


def handle_propagate_init(args: argparse.Namespace, root: Path) -> int:
    _deprecation_notice("propagate-init", "propagate --kind init")
    return run_propagate_init(
        ai_ops_root=root,
        project=args.project,
        all_projects=args.all_projects,
        dry_run=args.dry_run,
        auto_yes=args.auto_yes,
    )


def handle_propagate_files(args: argparse.Namespace, root: Path) -> int:
    _deprecation_notice("propagate-files", "propagate --kind files")
    return run_propagate_files(
        ai_ops_root=root,
        project=args.project,
        all_projects=args.all_projects,
        dry_run=args.dry_run,
        auto_yes=args.auto_yes,
    )


def handle_worktree_new(args: argparse.Namespace, root: Path) -> int:
    # 旧名 `worktree-new` 経由 (`args.command` で判定) なら deprecation 警告。
    if args.command == "worktree-new":
        _deprecation_notice("worktree-new", "worktree new")
    return run_worktree_new(
        slug=args.slug,
        branch_type=args.branch_type,
        base_branch=args.base_branch,
        dry_run=args.dry_run,
        cwd=root,
    )


def handle_worktree_cleanup(args: argparse.Namespace, root: Path) -> int:
    if args.command == "worktree-cleanup":
        _deprecation_notice("worktree-cleanup", "worktree cleanup")
    return run_worktree_cleanup(
        auto=args.auto,
        dry_run=args.dry_run,
        auto_archive=getattr(args, "auto_archive", False),
        cwd=root,
    )


def handle_report_drift(args: argparse.Namespace, root: Path) -> int:
    return run_report_drift(
        ai_ops_repo=args.repo,
        audit_json_path=args.audit_json,
        dry_run=args.dry_run,
    )


def handle_setup_ci_workflow(args: argparse.Namespace, root: Path) -> int:
    if args.command == "setup-ci-workflow":
        _deprecation_notice("setup-ci-workflow", "setup ci")
    return run_setup_ci_workflow(
        project=args.project.resolve(),
        tier=args.tier,
        ai_ops_ref=args.ai_ops_ref,
        dry_run=args.dry_run,
    )


def handle_setup_codeowners(args: argparse.Namespace, root: Path) -> int:
    if args.command == "setup-codeowners":
        _deprecation_notice("setup-codeowners", "setup codeowners")
    return run_setup_codeowners(
        project=args.project.resolve(),
        owner=args.owner,
        dry_run=args.dry_run,
    )


def handle_setup_ruleset(args: argparse.Namespace, root: Path) -> int:
    if args.command == "setup-ruleset":
        _deprecation_notice("setup-ruleset", "setup ruleset")
    return run_setup_ruleset(
        project=args.project.resolve(),
        tier=args.tier,
        dry_run=args.dry_run,
    )


def handle_setup_ecosystem(args: argparse.Namespace, root: Path) -> int:
    return run_setup_ecosystem(
        project_name=args.project_name,
        ai_ops_repo=args.ai_ops_repo,
        owner=args.owner,
        dry_run=args.dry_run,
    )


def handle_review_pr(args: argparse.Namespace, root: Path) -> int:
    return run_review_pr(
        pr=args.pr,
        repo=args.repo,
        dry_run=args.dry_run,
        provider=args.provider,
        cwd=root,
    )


def handle_review_cost(args: argparse.Namespace, root: Path) -> int:
    return run_review_cost(month=args.month)


def resolve_agent(root: Path, override: str | None):
    config = load_agent_config(root, override=override)
    name = config.default
    if name == "prompt-only":
        return PromptOnlyAgent()
    if name in config.commands:
        return SubprocessAgent(name, config.commands[name])
    print(f"Unknown agent: {name}; falling back to prompt-only", file=sys.stderr)
    return PromptOnlyAgent()


def _ask(label: str) -> str:
    return input(f"{label}: ").strip()
