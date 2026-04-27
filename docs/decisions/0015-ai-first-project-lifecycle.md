# ADR 0015: AI-first project lifecycle

> Status: Accepted
> Date: 2026-04-27
> Context: ai-ops は当初、移行 scripts / templates / ADR の集合として成長した。しかし既存 project の移行は機械的には決められず、新規 project も最初の repo 形状が product intent、機密境界、検証方法、AI operating rules に依存する。ai-ops は「万能 scaffold」ではなく、AI agent が project-specific な brief を作り、承認後に project-specific に実行する lifecycle system であるべきだと判断した。

## 決定

ai-ops の canonical workflow を次に定める。

```text
Intake -> Discovery -> Brief -> Design Review -> Confirm -> Agent Execute -> Verify -> Adopt
```

非自明な新規作成と既存移行では、AI agent は先に brief を作る。

- 新規 project: `templates/project-brief.md`
- 既存 migration: `templates/migration-brief.md`
- fresh session / 別 agent 引き継ぎ: `templates/agent-handoff.md`

brief は必ず Fact / Inference / Risk / User decision / AI recommendation を分ける。user が承認した後、AI agent が通常の開発ツールで実行する。

## 役割分担

| 担い手 | 役割 |
|---|---|
| User | 事業判断、公開範囲、機密境界、長期優先順位を決める |
| AI agent | 観察、推論、リスク整理、project-specific な提案を行う |
| Python CLI | OS 差を吸収し、discovery、prompt assembly、agent invocation、check/audit を提供する |
| Audits | stale docs、claim drift、secret risk、harness drift を検出する |
| Nix | optional な再現可能 operations layer を提供する |

`ai-ops` CLI は product strategy を発明しない。AI は戦略を推論できるが、承認なしに確定しない。実装言語と command surface は ADR 0016 が定める。

## Agent portability

canonical instructions は tool-specific config ではなく Markdown と Python 製 `ai-ops` CLI に置く。

- `AGENTS.md` が cross-project source of truth。
- `CLAUDE.md` は Claude Code 向けの `@AGENTS.md` adapter だけでよい。
- Codex、Claude Code、Cursor、その他の AI は、同じ `README.md`、`AGENTS.md`、`docs/ai-first-lifecycle.md`、`templates/*.md`、`ai-ops` CLI から再開できる必要がある。
- `.claude/settings.json` や hooks は defense in depth であり、canonical source of truth ではない。

## 実装

- `docs/ai-first-lifecycle.md`: canonical workflow
- `templates/*.md`: project / migration / handoff brief
- `ai_ops/`: Python canonical implementation
- `ai-ops new`: project intake, brief generation, agent invocation
- `ai-ops migrate`: migration discovery, brief generation, agent invocation
- OS-specific `scripts/ai-ops.*` adapters are not part of the target design
- `ai-ops audit lifecycle`: lifecycle surface audit
- `ai-ops check`: Nix 非依存 verification entrypoint
- `flake.nix`: optional reproducible wrapper

## 結果

Positive:

- Claude Code / Codex など複数 AI agent で同じ workflow を使える。
- 新規作成と既存移行が同じ判断モデルで扱える。
- 古い migration-era docs が active truth として残るリスクを audit できる。
- CLI と AI の責務境界が明確になる。

Negative:

- 軽微な project には brief が重い。したがって brief 必須は非自明な creation / migration に限定する。
- `--brief` mode は Markdown field の validation であり、AI の判断品質そのものは保証しない。

Neutral:

- Nix は optional のまま。Nix 未導入環境では Python CLI を使う。
- Claude Code 固有の advanced harness は reference として残るが、standard にはしない。

## 検証

採用時点で以下を確認する。

```sh
python -m ai_ops check
python -m ai_ops audit lifecycle
python -m ai_ops new brief-smoke --purpose "brief validation smoke" --dry-run
direnv exec . nix flake check
```

実 project validation は対象プロジェクトごとの proposal と Git history に残す。

## 関連

- ADR 0001: AGENTS.md primary
- ADR 0004: portability first
- ADR 0014: Nix optional reproducibility layer
- ADR 0016: Python canonical CLI
- `docs/ai-first-lifecycle.md`
