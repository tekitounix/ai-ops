from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ai_ops.agents.prompt_only import PromptOnlyAgent
from ai_ops.agents.subprocess import SubprocessAgent
from ai_ops.audit.lifecycle import run_lifecycle_audit
from ai_ops.audit.nix import run_nix_audit
from ai_ops.audit.security import run_security_audit
from ai_ops.checks.runner import run_check
from ai_ops.config import load_agent_config
from ai_ops.lifecycle.migration import build_migration_prompt
from ai_ops.lifecycle.project import build_project_prompt, draft_project_brief
from ai_ops.models import MigrationSpec, ProjectSpec
from ai_ops.paths import package_root


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 0
    target_root = Path.cwd().resolve()
    return args.handler(args, target_root)


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
    new.add_argument("--nix", dest="nix_level", choices=("none", "devshell", "apps", "full"), default="none")
    new.add_argument("--output", type=Path)
    new.add_argument("--dry-run", action="store_true")
    new.set_defaults(handler=handle_new)

    migrate = sub.add_parser("migrate", help="Prepare an AI-first migration prompt")
    migrate.add_argument("source", nargs="?")
    migrate.add_argument("--agent")
    migrate.add_argument("--interactive", action="store_true")
    migrate.add_argument("--tier", choices=("T1", "T2", "T3"), default="T3")
    migrate.add_argument("--nix", dest="nix_level", choices=("none", "devshell", "apps", "full"), default="none")
    migrate.add_argument("--output", type=Path)
    migrate.add_argument("--dry-run", action="store_true")
    migrate.set_defaults(handler=handle_migrate)

    check = sub.add_parser("check", help="Run ai-ops repository checks")
    check.set_defaults(handler=lambda _args, root: run_check(root))

    audit = sub.add_parser("audit", help="Run read-only audits")
    audit.add_argument("kind", nargs="?", choices=("lifecycle", "nix", "security"), default="lifecycle")
    audit.set_defaults(handler=handle_audit)
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
    prompt = build_migration_prompt(spec, root=package_root())
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
        return run_nix_audit(root)
    if args.kind == "security":
        return run_security_audit(root)
    raise AssertionError(args.kind)


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
