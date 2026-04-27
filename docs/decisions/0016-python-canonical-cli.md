# ADR 0016: Python canonical CLI for cross-platform lifecycle operations

> Status: Accepted
> Date: 2026-04-27
> Context: ai-ops initially grew through Bash executors and later added `scripts/ai-ops.sh` / `.ps1` / `.cmd` launchers. That unified the command surface, but did not make the implementation itself cross-platform. Native Windows still depended on Bash through Git Bash or WSL, and core lifecycle behavior remained split across shell scripts. For ai-ops to be a durable cross-project operations tool, the canonical implementation must not depend on OS-specific shell semantics.

## Decision

The canonical implementation of `ai-ops` will be a Python CLI.

Shell, PowerShell, and CMD adapter files are not part of the target design. User-facing commands and Nix apps point at the Python CLI.

Target structure:

```text
ai_ops/
  __main__.py
  cli.py
  config.py
  agents/
    claude.py
    codex.py
    prompt_only.py
    subprocess.py
  lifecycle/
    project.py
    migration.py
  audit/
    lifecycle.py
    nix.py
    security.py
  checks/
    runner.py
```

The user-facing command surface is:

```sh
ai-ops new <name> --purpose "<one-line-purpose>"
ai-ops migrate <path>
ai-ops check
ai-ops audit <kind>
```

`ai-ops new` and `ai-ops migrate` support:

- no required positional argument in interactive mode
- `--agent <name>` to override configured default
- `--agent prompt-only` to generate prompt/brief without invoking an AI CLI
- `--dry-run` to show the assembled prompt/brief without invoking an AI CLI

## Agent configuration

Default agent selection is configuration, not hardcoded behavior.

Config precedence:

1. CLI flag: `--agent <name>`
2. repo-local `ai-ops.toml`
3. user-local `$XDG_CONFIG_HOME/ai-ops/config.toml` or platform equivalent
4. built-in default: `prompt-only`

Minimal config:

```toml
[agent]
default = "prompt-only"

[agents.claude]
command = ["claude"]

[agents.codex]
command = ["codex"]
```

Agent adapters pass prompts to existing AI CLIs and relay their output. The CLI itself does not try to mechanically create or migrate projects; project creation and migration are agent-led because the correct target shape depends on the project.

## AI execution contract

The CLI owns repeatable orchestration: configuration resolution, read-only discovery, prompt assembly, prompt-only output, checks, and audits.

```text
Discovery -> Prompt assembly -> Agent proposal -> User confirm -> Agent execution -> Verify
```

AI output is advisory until user confirmation. A proposal must state commands, target paths, files to create/update, risk, rollback, and verification. After confirmation, the active AI agent executes with its own tools under `AGENTS.md` rules.

## Consequences

Positive:

- Cross-platform behavior is implemented once in Python instead of duplicated across shell dialects.
- Windows no longer requires Git Bash or WSL for core operations.
- AI invocation becomes configurable and testable.
- `prompt-only` keeps the lifecycle usable without any installed AI CLI.
- Nix remains useful as a reproducible wrapper but no longer defines the primary runtime model.

Negative:

- Existing shell-era docs and audits must be cleaned so the active path is not ambiguous.
- Python packaging, version policy, and subprocess behavior become part of the harness surface.

Neutral:

- `ghq`, `git`, `gh`, and optional `nix` remain external CLIs invoked by Python.
- Existing brief templates remain valid.
- Existing shell scripts are not user-facing lifecycle entrypoints.

## Verification

Required before declaring parity:

```sh
python -m ai_ops --help
python -m ai_ops new --help
python -m ai_ops migrate --help
python -m ai_ops check
python -m ai_ops audit lifecycle
python -m pytest
nix flake check
```

At least one smoke test must run on each supported OS family:

- macOS
- Linux
- Windows PowerShell without Git Bash dependency for core CLI behavior

## Related

- ADR 0004: portability first
- ADR 0014: Nix optional reproducibility layer
- ADR 0015: AI-first project lifecycle
- `docs/ai-first-lifecycle.md`
