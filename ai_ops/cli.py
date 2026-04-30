from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ai_ops.agents.prompt_only import PromptOnlyAgent
from ai_ops.agents.subprocess import SubprocessAgent
from ai_ops.audit.fleet import run_fleet_audit
from ai_ops.audit.harness import run_harness_audit
from ai_ops.audit.lifecycle import run_lifecycle_audit
from ai_ops.audit.nix import run_nix_audit, run_nix_propose, run_nix_report
from ai_ops.audit.security import run_security_audit
from ai_ops.audit.standard import run_standard_audit
from ai_ops.bootstrap import run_install, run_update
from ai_ops.checks.runner import run_check
from ai_ops.config import load_agent_config
from ai_ops.lifecycle.migration import build_migration_prompt
from ai_ops.lifecycle.plans import run_promote_plan
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
        choices=("lifecycle", "nix", "security", "harness", "standard", "fleet"),
        default="lifecycle",
    )
    audit.add_argument(
        "--report",
        action="store_true",
        help="Nix only: walk ghq list -p and print fleet survey",
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
        help="Fleet only: emit JSON instead of the text table",
    )
    audit.add_argument(
        "--priority",
        choices=("P0", "P1", "P2", "all"),
        default="all",
        help="Fleet only: filter rows by priority (default: all)",
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
    if args.kind == "fleet":
        return run_fleet_audit(
            json_output=getattr(args, "json", False),
            priority_filter=getattr(args, "priority", "all"),
        )
    raise AssertionError(args.kind)


def handle_bootstrap(args: argparse.Namespace, _root: Path) -> int:
    return run_install(tier_max=args.tier, dry_run=args.dry_run)


def handle_update(args: argparse.Namespace, _root: Path) -> int:
    return run_update(tier_max=args.tier, dry_run=args.dry_run)


def handle_promote_plan(args: argparse.Namespace, root: Path) -> int:
    return run_promote_plan(
        root=root,
        slug=args.slug,
        source=args.source,
        dry_run=args.dry_run,
    )


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
