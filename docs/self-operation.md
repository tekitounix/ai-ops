# ai-ops Self-Operation

この文書は、ai-ops 自身を ai-ops の管理対象として運用し続けるための最小ループである。永続ルールは `AGENTS.md`、長期判断は `docs/decisions/`、実行中の非自明な作業は `docs/plans/<slug>/plan.md` に置く。

## Operating Loop

ai-ops 自身の変更は、通常の Lifecycle を dogfood する。

```text
Intake -> Discovery -> Brief/Plan -> Proposal -> Confirm -> Execute -> Verify -> Adopt
```

- 小さな単発修正は、読解、実装、検証、commit/PR 説明で足りる。
- CLI behavior、public docs、ADR、templates、Nix、CI、packaging、security audit に触れる変更は、必要に応じて `docs/plans/<slug>/plan.md` を作る。
- `AGENTS.md` には transient state を置かない。作業が終わった plan は `docs/plans/archive/YYYY-MM-DD-<slug>/` に移す。

## Release-Ready Gate

ai-ops を「完成 / release-ready」と言う前に、次を確認する。

```sh
git status --short --branch
python -m ai_ops check
git diff --check
direnv exec . sh -c '
set -e
nix flake check --all-systems --no-build
nix build --no-link ".#checks.$(nix eval --impure --raw --expr builtins.currentSystem).all"
'
```

加えて、GitHub 上の latest `main` CI が同じ commit で success していることを確認する。CI がまだ走っていない、または remote と local の `HEAD` が違う場合は release-ready と言わない。

## Drift Review

非自明な変更の前後で、次の drift signal を見る。

- `rg -n --hidden -g '!/.git' -e 'TODO|FIXME|TBD|WIP|not implemented|coming soon' .`
- `find docs/plans -maxdepth 3 -type f | sort`
- `python -m ai_ops audit lifecycle`
- `python -m ai_ops audit nix`
- `python -m ai_ops audit security`

Template 内の `TBD` は expected placeholder として扱う。active docs、README、CLI help、tests に残った未完了 marker は修正または明示的な plan 化が必要。

## Dogfood Checks

Release 前または lifecycle 周りを変更した時は、少なくとも以下の dry-run / smoke を行う。

```sh
python -m ai_ops new dogfood --purpose "dogfood project" --agent prompt-only --dry-run
python -m ai_ops migrate . --agent prompt-only --dry-run
python -m ai_ops migrate . --retrofit-nix --agent prompt-only --dry-run
python -m ai_ops promote-plan dogfood --source /path/to/local-plan.md --dry-run
```

`promote-plan` の source は user-selected local plan に限る。ai-ops は `~/.claude/`、`~/.cursor/`、`~/.codex/` 等を silently scan しない。

## Change Thresholds

- ADR: public contract、operation model、safety policy、CLI responsibility、reproducibility model を変える。
- Plan: 複数 file / 複数 session / cross-agent review / migration が必要。
- Test: CLI behavior、audit rule、prompt assembly、packaging、OS-specific behavior を変える。
- README / docs: user-facing entrypoint、operator-facing procedure、release-ready claim を変える。

## File Hygiene

Tracked files are source of truth. Generated files such as `.direnv/`, `.pytest_cache/`, `__pycache__/`, `build/`, `*.egg-info/`, and `ai_ops/_resources/` are not source of truth and must stay ignored.

When doing a repository-wide file review, classify tracked files one by one by role, necessity, and placement. Generated / ignored files may be reviewed by deterministic category instead of reading binary cache contents.

Latest baseline review: `docs/plans/archive/2026-04-29-ai-ops-self-operation/file-audit.md`.
