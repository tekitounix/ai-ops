# ai-ops Self-Operation

> Master operation guide: [`operation.md`](operation.md). This is the deep-dive on ai-ops's own dogfood loop (self-management as a managed project).

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

## Worktree-based Parallel Work (ADR 0010)

非自明な作業を並行で進める / 進行中の作業を別ブランチで隔離したい場合、`ai-ops worktree-new <slug>` を使う。これは sibling 配置(`<repo-parent>/<repo-name>.<slug>/`)で git worktree を作成し、`<type>/<slug>` ブランチを切り、`docs/plans/<slug>/plan.md` の skeleton を seed する。1 plan : 1 branch : 1 worktree の binding が前提。

実用上の上限は 1 repo あたり 3〜5 worktree。これ以上は context-switching cost が並列化のメリットを上回る(2026 業界 best practice)。

完了後は `ai-ops worktree-cleanup` で「PR がマージされて、かつ plan が archived 済み」の worktree を一括 / 個別確認の上で削除。両方の signal が必要なのは Safety のため(片方だけだと誤削除リスクが高い)。

## Improvement Capture Loop

ai-ops 自身の作業を Adopt する前に、active plan の `## Improvement Candidates` を triage する。各 candidate は次の enum に振り分ける:

- `current-plan` — 同 plan 内で吸収する小修正。
- `durable-doc` — `docs/` 配下 (`ai-first-lifecycle.md` / `self-operation.md` / `realignment.md` / `projects-audit.md` 等)。
- `adr` — public contract / operation model / safety policy / CLI 責任 / reproducibility model の変更。`docs/decisions/` に新 ADR を起こす。
- `template` — `templates/` 配下 (plan / brief / handoff)。
- `audit` / `harness` / `test` — `ai_ops/audit/` / `ai_ops/_resources/` (build artifact、手で書かない) / `tests/` の対応 module。
- `deferred` — 今回は採用しない (理由必須)。次 plan で再評価。
- `rejected` — 採用しないと判断 (理由必須)。

`adr` / `harness` semantics 変更 / 既存 audit rule の厳格化 / 新 subcommand 追加は、AGENTS.md Operation Model の Propose -> Confirm -> Execute を必ず通す。`current-plan` / `durable-doc` / `template` / `test` の小幅追加は通常 commit で良い。同じ candidate が 3 plan 連続で `deferred` になった場合は、`docs/plans/_inbox.md` 化または独立 plan / ADR への昇格を検討する。

## File Hygiene

Tracked files are source of truth. Generated files such as `.direnv/`, `.pytest_cache/`, `__pycache__/`, `build/`, `*.egg-info/`, and `ai_ops/_resources/` are not source of truth and must stay ignored.

When doing a repository-wide file review, classify tracked files one by one by role, necessity, and placement. Generated / ignored files may be reviewed by deterministic category instead of reading binary cache contents.

Latest baseline review: `docs/plans/archive/2026-04-29-ai-ops-self-operation/file-audit.md`.
