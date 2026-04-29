# AGENTS.md — ai-ops

This repo is the cross-project AI operations source of truth. Keep it small. If a detail is recoverable from Git history, code, or command output, do not duplicate it here.

## Workspace

- All Git repositories live under `~/ghq/`.
- Get the user name with `git config --get ghq.user`; never hardcode it.
- Own projects: `~/ghq/github.com/$(git config --get ghq.user)/<repo>/`.
- External projects: `~/ghq/<host>/<org>/<repo>/`.
- Scratch work: `~/scratch/`, not a Git repo.
- Do not create repos under Desktop, Documents, or ad-hoc work directories.
- Cross-repo references in committed docs use URLs (`https://github.com/<owner>/<repo>/...`)。`~/ghq/...` は local working layout の説明にのみ使い、コミット済 doc 内の他 repo 参照には使わない。

## Lifecycle

Use `README.md` as the user-facing entrypoint.

```text
Intake -> Discovery -> Brief -> Proposal -> Confirm -> Agent Execute -> Verify -> Adopt
```

- New project brief: `templates/project-brief.md`.
- Migration brief: `templates/migration-brief.md`.
- Handoff brief: `templates/agent-handoff.md`.
- Canonical workflow: `docs/ai-first-lifecycle.md`.
- Detailed guide: `docs/project-addition-and-migration.md`.

## Plans

Use `docs/plans/<slug>/plan.md` for non-trivial execution-time plans that need handoff, multi-session continuity, or cross-agent review. Start from `templates/plan.md`, keep `Progress` / `Surprises & Discoveries` / `Decision Log` / `Outcomes & Retrospective` current, and archive completed plans under `docs/plans/archive/YYYY-MM-DD-<slug>/`. Do not store transient task state in `AGENTS.md`, and do not treat `~/.claude/plans/` or other user-local AI tool storage as canonical.

`ai-ops` is the Python CLI: installed console script, `python -m ai_ops`, or `nix run github:<owner>/ai-ops -- ...`.

Subcommands:

- `ai-ops new <name> --purpose "..."` — assemble prompt + Brief draft for a new project.
- `ai-ops migrate <path>` — read-only discovery + Brief for migrating an existing project.
- `ai-ops migrate <path> --retrofit-nix` — narrow scope: add `flake.nix` + `.envrc` to an already-managed project.
- `ai-ops bootstrap` — survey required tools (git / ghq / direnv / jq / gh / nix at tier 1; shellcheck / actionlint / gitleaks / fzf / rg at tier 2) and install missing ones with user confirmation (Operation Model).
- `ai-ops update` — survey present tools and update them with user confirmation.
- `ai-ops audit lifecycle` — self-audit for ai-ops itself (incl. Phase 8-D forbidden-pattern grep + README claim verification + Phase 9 plan hygiene warnings + optional OpenSSF Scorecard).
- `ai-ops audit nix` — current cwd Nix audit (Stage A/B/C rubric per ADR 0005).
- `ai-ops audit nix --report` — walk `ghq list -p` and print fleet-wide Nix gap table.
- `ai-ops audit nix --propose <path>` — emit Markdown retrofit proposal for one project.
- `ai-ops audit harness [--path PATH]` — detect harness drift (Phase 8-B, L3): missing / modified / extra harness files vs `.ai-ops/harness.toml`.
- `ai-ops audit standard --since REF [--path PATH]` — detect ADR (docs/decisions/) changes since a reference (Phase 8-C, L4).
- `ai-ops audit security` — secret scan (works in any cwd).
- `ai-ops check` — all audits + pytest.
- `ai-ops promote-plan <slug> [--source PATH] [--dry-run]` — read a user-selected local AI plan and propose a repo-local `docs/plans/<slug>/plan.md`; writing requires explicit confirmation.

`migrate` flags include `--retrofit-nix` (Nix-only) and `--update-harness` (harness drift remediation, AI agent narrows scope to file restoration / hash refresh).

`new` / `migrate` `--nix` flag: `auto` (default; AI decides via per-project rubric), `none` (justification required in brief), `devshell`, `apps`, `full`.

Reproducibility tools (Tier 1 includes `nix`) are installed only with explicit user confirmation per Operation Model. ai-ops does not silently mutate `~/.zshrc`, package managers, or OS schedulers — but it does propose installs via `bootstrap` / `update`.

When already running inside an AI agent, do not call another AI via `ai-ops --agent claude` or `ai-ops --agent codex`. Use docs directly, or use `--agent prompt-only` / `--dry-run` for prompt and discovery output only.

## Operation Model

Use Propose -> Confirm -> Execute for:

- destructive operations
- environment changes
- AI data substrate operations such as `~/.claude/projects/`
- visibility changes
- cross-cutting edits
- project-specific harness overwrite

One proposal requires one confirmation. Batch approval is forbidden. Read-only commands and local tests do not need confirmation.

## Safety

- Never commit `.env`, `*.key`, `*.pem`, credentials, customer data, or production secrets.
- Never push public visibility without explicit in-session confirmation.
- Never skip git hooks with `--no-verify` unless explicitly requested.
- Do not modify user environment files such as `~/.zshrc`, `~/.bashrc`, `~/.gitconfig`, `~/.config/*`, or OS scheduler files.
- Do not install launchd, cron, systemd, Task Scheduler, or background agents.
- Use `$HOME`, placeholders, or `git config --get ghq.user`; do not hardcode absolute user paths.
- Deleting tracked files is done as Git deletion, not by moving them into an in-repo archive.
- Prefer recovery-maximizing deletion: tracked file deletion via Git, then review with `git diff`; avoid `rm -rf`.

## Natural language

Default policy:

- Source code (identifiers / comments / tests)、commit messages、branch / tag 名、LICENSE: 英語。
- README / AGENTS.md / docs/、issues / PRs: 英語が default。日本語 primary を選ぶ場合は project-specific brief で明示する。

T1 (public) repo の場合は **`README.md` を英語にし、`README.<locale>.md` (例: `README.ja.md`) を sibling として併置する** のが業界標準 pattern。GitHub project page で auto-render されるのは `README.md` のみのため、最初の入口を英語にするのが国際 contributor を取り逃さない最低条件。各ファイル冒頭に language selector 1 行を置く。

working docs は日本語で運用しつつ、公開 surface (主 README) だけ英語にするのが最小コストで最大効果。AGENTS.md / docs/ / ADR の英語化は、需要が出てから段階的に sibling 併置する。

## Multi-agent

複数 AI agent を同 repo で並行運用する場合、各 AI tool の native worktree support を使う:

- Claude Code: `claude --worktree <name>` で `.claude/worktrees/<name>/` に独立 working tree が作られ、退出時に未 commit 変更が無ければ自動 cleanup。
- Codex: Codex App は worktree built-in。Codex CLI 単独なら `git worktree add ../<repo>.<branch> <branch>` で同等。

実用上限は 2-4 並列。それを超えると orchestration コストが parallelism のメリットを上回る。大規模並行時は integration branch を 1 本立てて段階的に main に取り込む。同一ファイルへの並行 edit は避け、agent ごとに担当ファイルを分離する。

`ai-ops` の各コマンドは worktree compatible で、実行 cwd を root として扱う。worktree 内から `ai-ops new` / `migrate` / `audit` / `check` をそのまま使える。

## Checks

Before reporting completion for this repo:

```sh
python -m ai_ops check
git diff --check
```

When Nix is available:

```sh
direnv exec . nix flake check
```

## See Also

- `README.md` — first entrypoint
- `docs/ai-first-lifecycle.md` — canonical workflow
- `docs/decisions/` — load-bearing ADRs only
