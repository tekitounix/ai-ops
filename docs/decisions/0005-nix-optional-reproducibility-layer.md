# ADR 0005: Nix as default reproducibility layer

> Status: Accepted (Amended 2026-04-29)
> Date: 2026-04-27 (Original), 2026-04-29 (Amended)

## Decision

Nix flake (project-level) を **default-required reproducibility layer** とする。
Python CLI は Nix なしで動くが、これは bootstrap fallback であって運用 entry ではない。

```text
Python CLI: Nix なしで動く (bootstrap fallback)
flake.nix:  devShell / apps / checks を宣言 (default-required for stack-bearing project)
flake.lock: Nix dependency universe を固定
```

採用判断は per-project rubric (Stage A/B/C) で機械決定。詳細は `docs/project-addition-and-migration.md` § Nix rubric。

## Scope

- **In-scope**: project-level `flake.nix` (devshell / apps / checks)
- **Out-of-scope**: NixOS、nix-darwin、Home Manager (= ADR 0002 「user 環境を変更しない」と矛盾するため不採用)

## Rules

- Nix 本体の install / update は `ai-ops bootstrap` / `ai-ops update` 経由で user 承認後に実行 (ADR 0002 amendment 整合)
- `nix.conf`、user-level direnv config を ai-ops が silently 変更しない
- `flake.lock` 更新は明示的 dependency update operation として扱う
- secret 値を Nix store に入れない
- destructive / hardware operations は `nix flake check` に入れない

## Per-project rubric (Stage A/B/C)

AI agent が JSON output を返す。

### Stage A: Hard gates (early exit)

| 条件 | signal | 結果 |
|---|---|---|
| archive | last commit > 18mo, no PR | none |
| scratch | `~/scratch/`, no remote, < 5 file | none |
| docs-only | 全 tracked が markdown/pdf | none / minimal |
| existing flake | `flake.nix` あり | preserve / amend |
| vendor too closed | GUI installer / license dongle | devshell with vendor outside closure |
| upstream fork | non-user org remote, mostly upstream commits | none |

### Stage B: Stack-aware default

| Stack signal | Level | Template |
|---|---|---|
| `xmake.lua` | devshell | `flake.nix.xmake` |
| `CMakeLists.txt` | devshell | `flake.nix.minimal` (cmake/ninja/clang を tools に追加) |
| 商用 SDK / vendor binary | devshell + overlay | `flake.nix.xmake` 派生 |
| `package.json` / `pnpm-lock.yaml` | devshell | `flake.nix.node` |
| `pyproject.toml` / `uv.lock` | devshell | `flake.nix.python` |
| `Cargo.toml` | devshell | `flake.nix.minimal` (cargo/rustc を tools に追加) |
| `go.mod` | devshell | `flake.nix.minimal` (go を tools に追加) |
| DSL (`*.ato` 等) | devshell minimal | `flake.nix.minimal` |

### Stage C: Score adjustment

Pros (+1〜+3): toolchain volatility / multi-developer / CI imperative steps / long-term maintenance / external contributor / release artifact / vendor binary / AI session 高頻度 / sandbox 需要 / tests / activity / LOC > 500

Cons (−1〜−5): dormant / scratch / docs-only / throwaway / system-tool only / vendor too closed / tiny project / single binary / strong existing repro layer / stale-not-archive / many top-level memo files

| Score | Action |
|---|---|
| ≥ +6 | promote (devshell → apps) |
| +2 〜 +5 | keep |
| 0 〜 +1 | borderline (brief で flag) |
| < 0 | demote to none (justification 必須) |

## Verification

```sh
python -m ai_ops audit nix              # cwd の flake.nix 妥当性 + rubric output
python -m ai_ops audit nix --report     # ghq list 全 walk、recommendation table
python -m ai_ops audit nix --propose <path>  # 単一 project の retrofit Markdown 提案
direnv exec . nix flake check --all-systems --no-build
direnv exec . sh -c 'nix build --no-link ".#checks.$(nix eval --impure --raw --expr builtins.currentSystem).all"'
```

## Amendment 2026-04-29

旧 Decision「Nix を optional but first-class」は採用率 3/45 と低迷、reproducibility claim と乖離。AI-first 前提 (= 学習コスト無視) と xmake project の system lib pin 必要性により、Nix flake を default-required に格上げ。Per-project rubric (Stage A/B/C) で機械判定、stack-bearing project は default `devshell`、archive / scratch / docs-only / fork は `none`。

## Related

- ADR 0001: AGENTS.md primary
- ADR 0002: portability first (silent installer 禁止 + user 承認付き install/update 許可、本 ADR と同時 amend)
- ADR 0006: AI-first project lifecycle (rubric は AI agent が operate)
- ADR 0007: Python canonical CLI (rubric 実装は `ai_ops/audit/nix.py`)
