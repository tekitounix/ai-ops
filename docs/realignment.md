# Realignment

> Master operation guide: [`operation.md`](operation.md). This is the deep-dive on the realign sub-flow for projects that have drifted from ai-ops's ideal state.

運用しているプロジェクトが理想からずれて、開発が進めにくくなった時に、ai-ops のモデルを参照して矯正・改善するための agent 向け手順書である。新規プロジェクト作成や初回移行は対象外で、それぞれ [docs/ai-first-lifecycle.md](ai-first-lifecycle.md) と [docs/project-addition-and-migration.md](project-addition-and-migration.md) を使う。

## When to Use

次の signal が複数当てはまる時に使う。

- AGENTS.md / README / ADR / lifecycle 文書のいずれかが古いまたは欠落している。
- TODO / FIXME / TBD / WIP が active doc / source / test に滞留している。
- `docs/plans/` に未 archive の active plan が残ったまま放置されている。
- check / audit / CI が落ちる、または当該プロジェクトに「release-ready の定義」が無い。
- harness、設定、ADR の決定が実装まで伝播していない。
- 役割境界 (AI / user / CLI) が現状と一致していない。
- repo の物理 location が `~/ghq/<host>/<owner>/<repo>/` 外にある (e.g. `~/work/`, `~/Documents/`)。 物理移行手順は [docs/project-relocation.md](project-relocation.md) に従う。

## Operating Model

3 相に強制する。Phase 3 の human confirmation までは file を 1 byte も書き換えない。AGENTS.md の Operation Model (Propose -> Confirm -> Execute) と Safety を遵守する。

```text
Phase 1 Discovery (read-only)  ->  Phase 2 Realignment Brief  ->  Phase 3 Execute on confirmation
```

## Phase 1 - Discovery (read-only)

ai-ops を reference として読み込む。GitHub の URL を fetch する。

- https://github.com/tekitounix/ai-ops/blob/main/AGENTS.md
- https://github.com/tekitounix/ai-ops/blob/main/docs/ai-first-lifecycle.md
- https://github.com/tekitounix/ai-ops/blob/main/docs/self-operation.md
- https://github.com/tekitounix/ai-ops/tree/main/templates/
- https://github.com/tekitounix/ai-ops/tree/main/docs/decisions/

現プロジェクトの実態を read-only で観察する。

```sh
git ls-files
git log --since="6 months ago" --oneline | head -50
rg -n --hidden -g '!.git' -e 'TODO|FIXME|TBD|WIP|not implemented|coming soon' .
find docs -maxdepth 3 -type f 2>/dev/null

# repo physical location が ghq 配下か確認
# (ghq 外なら relocation drift signal、playbook は project-relocation.md)
realpath . | grep -q "^$HOME/ghq/" && echo "ghq compliant" || echo "DRIFT: not under ~/ghq/"
```

`ai-ops` CLI が install 済みなら次も走らせる (任意 cwd で動作する)。

```sh
ai-ops audit lifecycle    # ai-ops 自身向け self-audit。他 project では skip 可
ai-ops audit security
ai-ops audit harness
ai-ops audit standard --since <main-or-equivalent-base-ref>
ai-ops audit nix
```

該当 project が `ghq list -p` 配下なら、`ai-ops audit projects --json` を実行し、対象 project の `policy_drift`、`workflow_tier`、`tier_violations` field を確認する。`policy_drift` が `stale` / `diverged` / `ahead-and-behind` / `no-anchor` のいずれかなら本 realignment で remediation 提案に含める。`workflow_tier` が宣言されていない、または `tier_violations` が non-empty なら、Phase 2 の P0 doc-only セクションで tier 宣言/見直し提案に含める。

`audit standard --since` の base ref が不明な場合は、最新 release tag、`origin/main`、あるいは「最後に大きな整備をしたと思われる commit」から選ぶ。判断根拠を Brief に残す。

この相では何も書き換えない。secret value は読まない。secret らしいファイル名 / pattern は値を開かず Risk として扱う。

## Phase 2 - Realignment Brief

返答として 1 つの Markdown ドキュメントを出す。タイトルは "Realignment Brief"。Brief は次の構造を持つ。

1. **Current state snapshot** - 現状の構造、tier、AI tooling の有無、lifecycle 適合度、check / CI の状態を簡潔に。
2. **Drift signals observed** - 具体的な evidence (欠落 file、stale plan、未記録の ADR、滞留 TODO、audit fail、契約破れ)。Fact / Inference / Risk で分類する。
3. **Ideal-state delta** - ai-ops モデルとの差分。何が足りないか、何が余分か、何が乖離しているか。
4. **Proposed remediation** - 可逆性で 3 段に分ける。
   - **P0 doc-only**: AGENTS.md、README、ADR、lifecycle 文書、self-operation 相当の運用書、`workflow_tier` 宣言(ADR 0009: `.ai-ops/harness.toml` に `workflow_tier = "A"|"B"|"C"|"D"` を追加。Discovery で観察した signal — managed 状態、public/private、recent contributor 数、long-lived branch の有無、direct push の習慣 — を根拠に tier を提案し、user 確認後に追記する PR を立てる)。
   - **P1 structural**: templates、`docs/plans/` 構造、audit hook、`.gitignore`、`docs/brief-YYYYMMDD.md`、policy drift remediation (`audit projects` の `policy_drift` が `stale` / `diverged` / `ahead-and-behind` の場合: 自前 `templates/plan.md` または active plan に canonical schema を採用。`no-anchor` の場合: まず `.ai-ops/harness.toml` の `ai_ops_sha` を anchor として確立する harness sync を Phase 0 として先行)。
   - **P2 behavioral**: CI、Nix retrofit、harness alignment、packaging、test coverage。
   - 各 item には target paths / nature (add | edit | rm) / reversibility (Git revert / config rollback / data 損失リスク) を書く。
5. **Out-of-scope** - 観測したが今回は触らない drift と、その理由。
6. **Verification plan** - どの check を、どの順で走らせるか。

`templates/migration-brief.md` の Fact / Inference / Risk / User decision / AI recommendation の分類を Brief 内でも使う。

Brief を出したら停止する。何も実行しない。

## Phase 3 - Execute on Confirmation

非自明な remediation や、複数 scope を並行で進める場合は、`ai-ops worktree new <slug>` で隔離 worktree を作って実行することを推奨(ADR 0010)。1 scope : 1 plan : 1 branch : 1 worktree の binding により、後の review と cleanup がしやすくなる。実用上の上限は 1 repo あたり 3〜5 worktree。



human が P0 / P1 / P2 を **個別に** approve するのを待つ。batch approval (一度の y/N で複数 scope を承認) は AGENTS.md Operation Model で禁じられている。

各 approval ごとに:

1. その scope だけを execute する。
2. 対応する verification subset を走らせる。
3. diff summary を再提示する。
4. 次の approval を待つ。

実行中に予期しない state を発見したら、削除や上書きで「消す」のではなく原因を追う (AGENTS.md Safety)。tracked file の削除は `git rm` 経由で行い、in-repo archive 移動で代替しない。

## Constraints (Non-Negotiable)

AGENTS.md の Safety から引き写したもの。違反する操作は agent 側で拒否する。

- push、force-push、published history の rewrite は明示指示が無い限り禁止。
- `--no-verify` で git hook を skip しない。
- `~/.zshrc` / `~/.bashrc` / `~/.gitconfig` / `~/.config/*` / OS scheduler を変更しない。
- `.env` / `*.key` / `*.pem` / 顧客データ / 本番 secret は commit しない。
- cross-repo reference は committed doc 内では https URL を使う。`~/ghq/...` は local working layout の説明のみ。
- 言語: owner が日本語話者なので、運用 docs / AGENTS.md / issues / PRs / briefs / plans は日本語を default とする。source identifier / commit / branch 名 / LICENSE は英語。`README.md` だけは public first entrypoint として英語 default。完成していて公開を目的とする project では、重要度に応じて英語 docs を追加し、必要なら `README.ja.md` 等を sibling として併置する。

## Verification

P0 / P1 / P2 の最後の execute 後に通す共通 gate。プロジェクト固有の追加 check は brief の Verification plan に書く。

```sh
git status --short --branch
git diff --check
# ai-ops が install 済みなら
ai-ops check
# Nix が available なら
direnv exec . nix flake check --all-systems --no-build
```

`ai-ops check` が無いプロジェクトでは、当該プロジェクトの canonical check command (`AGENTS.md` の Checks に記述されているはず) で代替する。CI が remote と同じ commit で success していることも確認する。

## See Also

- [AGENTS.md](../AGENTS.md) - Operation Model、Safety、Lifecycle、natural language policy
- [docs/ai-first-lifecycle.md](ai-first-lifecycle.md) - 8-step lifecycle
- [docs/self-operation.md](self-operation.md) - ai-ops 自身の dogfood loop と release gate
- [docs/project-addition-and-migration.md](project-addition-and-migration.md) - 新規追加と初回移行
- [templates/migration-brief.md](../templates/migration-brief.md) - Brief schema
- [templates/plan.md](../templates/plan.md) - Execution plan schema
