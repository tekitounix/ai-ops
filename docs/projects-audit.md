# プロジェクト一括監査 (ghq 管理下の全プロジェクト)

> マスター運用ガイド: [`operation.md`](operation.md)。これはマルチプロジェクト監査 playbook の deep-dive。
>
> スコープ: ghq 管理下の全プロジェクトを列挙し、各プロジェクトの drift 信号を浮かび上がらせ、可逆性 / 緊急度で優先度を付け、各高優先度発見を適切な単一プロジェクト sub-flow (migrate / realign / relocate) にルーティングする。Read-only な Discovery → 優先度ソートされた Brief → 確認ごとに 1 プロジェクトずつ Execute、という進行。

## 使うべきとき

Quick start プロンプトの `Per github.com/tekitounix/ai-ops, audit my projects.` がこの playbook に到達する。エージェントは ai-ops を参照として読み、`ghq list -p` を walk し、優先度ソートされた Audit Brief を出力する。

この playbook は、プロジェクトごとの使用者確認なしには **いかなるプロジェクトも変更しない**。新規作業には Quick start の最初のプロンプト、単一の作業ツリー対象には 2 番目のプロンプト (`align this project`) を使う。

## 運用モデル

```text
Phase 1 Discovery (read-only、全プロジェクト)
  -> Phase 2 Brief (優先度ソート表 + 推奨)
  -> Phase 3 Execute (プロジェクトごと、sub-flow ごと、確認ごと)
  -> Phase 4 Verify (触れたプロジェクトの Discovery を再実行)
```

action が必要な各プロジェクトは独自の Propose → Confirm → Execute サイクルを得る。複数プロジェクトに跨る一括承認は AGENTS.md §Operation Model で禁止されている。Brief が durable state なので、セッション中断 / 再開がサポートされる。

## Phase 1 — Discovery (CLI 経由の read-only)

エージェントは canonical な収集器を呼ぶ — 個別の `find` / `git` 起動から表を組み立てない。CLI は決定的でバージョン管理されており、AI エージェントとスケジュールジョブ (cron / CI) で同じ出力が出る。

```sh
# エージェントが推論するための機械可読ビュー。
python -m ai_ops audit projects --json > /tmp/projects-audit.json

# 使用者が一目で見るには:
python -m ai_ops audit projects
```

各行は優先度と sub-flow 割当を駆動する 9 信号を持つ。

| キー | 意味 |
|---|---|
| `loc` | path が `~/ghq/<host>/<owner>/<repo>/` 配下なら `ok`、それ以外は `DRIFT` |
| `mgd` | `.ai-ops/harness.toml` が存在すれば `yes`、ai-ops 自身は `src`、それ以外は `no` |
| `nix` | `present` / `missing` / `n/a` (n/a は docs-only repo) |
| `sec` | secret 名称ファイル数 (`.env`、`*.key`、`*.pem`、`id_rsa` 等。`.env.example` 等は除外) |
| `dirty` | uncommitted state 行数 (`git status --porcelain`) |
| `last_commit_human` | `git log -1 --format=%ar` (例: "1 day ago") |
| `todo` | TODO / FIXME / WIP / TBD のテキスト出現数 (rg ベース。rg が無ければ 0) |
| `agents_md` | ルートに AGENTS.md が存在 |
| `policy_drift` | `ok` / `stale` / `diverged` / `ahead-and-behind` / `no-anchor` / `n/a` — 管理対象プロジェクト自身の `templates/plan.md` と active plan を ai-ops canonical schema (`^## ` 見出し集合) と比較。`n/a` = 未管理または ai-ops 自身。`no-anchor` = `harness.toml.ai_ops_sha` が無い。`stale` = canonical に存在する section がプロジェクトに無い。`diverged` = プロジェクトに余分な section がある。`ahead-and-behind` = 両方。AGENTS.md は意図的に対象外 (プロジェクト固有の契約)。 |
| `pending_propagation_prs` | プロジェクトの GitHub repo で head branch が `ai-ops/` で始まる open PR の数 (`ai-ops propagate-anchor` または `ai-ops propagate-init` が作った PR)。`-1` は `gh` が無く count 不明。`0` は伝播作業が無い状態。監査を安く保つため、polling は管理対象プロジェクトのみ。 |
| `remote_anchor_synced` | `true` / `false` / `null` — `origin/<default-branch>` の `.ai-ops/harness.toml` が `ai_ops_sha == 現 ai-ops HEAD` を持つか。`true` = 伝播完了、`false` = anchor-sync PR が必要、`null` = 判定不能 (`gh` 無し、fetch 失敗、または default branch に manifest 無し)。`true` の時、ローカル `harness_drift` が True でも優先度 P1 に昇格しない (使用者は pull するだけで足りる)。 |
| `workflow_tier` | `A` / `B` / `C` / `D` — ADR 0009 に従って宣言された workflow tier。`A` = trunk-based ソロ、`B` = 管理 feature-branch + PR、`C` = 本番 / 公開でレビューあり、`D` = ad-hoc スパイク (`harness.toml` に `workflow_tier` 欄が無い場合の default)。 |
| `tier_violations` | 宣言 tier からの逸脱の人間可読文字列リスト。空リスト = clean。default では安価な検出のみ (long-lived branch、manifest が default branch に無い等)。`INFO:` で始まる文字列は表示するが優先度は上げない (Tier D で「manifest が default branch に無い」notice が INFO 扱いなのは、使用者がその状態を明示的に受け入れたため)。 |

加えて CLI が一度だけ計算する derived フラグが 3 つ: `has_stack`、`is_docs_only`、`harness_drift`。ファイル名のみ — secret の **値** は決して開かない (CLI の `_count_secret_files` は名称ベース)。

### 推論中に単一の優先度に絞る

```sh
python -m ai_ops audit projects --json --priority P0   # 即時 action のみ
python -m ai_ops audit projects --json --priority P1   # 計画 action のみ
```

### 終了コード (cron / CI 用)

`ai-ops audit projects` は (フィルタ後の) 出力に P0 または P1 行が残れば `1`、それ以外は `0` を返す。夜間 cron で走らせて rc=1 にアラートを設定すれば、drift が現れた瞬間に浮上する。

## Phase 2 — Audit Brief

Brief はエージェントが CLI の JSON 出力から組み立てる Markdown ドキュメント。タイトル「Projects Audit Brief」、日付スタンプ付き、セッション残り中はチャットに固定。

### 優先度割当 (CLI が計算)

| 優先度 | トリガー |
|---|---|
| **P0** | `loc=DRIFT` (プロジェクトが `~/ghq/` 外) または `sec≥1` (secret 名称ファイル存在) |
| **P1** | stack を持つプロジェクトで `nix=missing`、または `mgd=yes` で harness drift、または `mgd=yes` で `policy_drift` ∈ {`stale`, `diverged`, `ahead-and-behind`, `no-anchor`}、または `mgd=yes` で INFO 以外の `tier_violations` あり、または最終 commit が 540 日 (約 18 ヶ月) 以上前なのに stack が稼働中 |
| **P2** | 観測のみ: clean な管理対象、validation fixture (`mgd=no` で意図的)、進行中の dirty 作業、TODO 滞留 |

プロジェクトの優先度は該当する最高位。JSON は各プロジェクトを 1 度だけリストする。

### sub-flow 割当 (これも CLI が計算)

| 条件 | `sub_flow` |
|---|---|
| `loc=DRIFT` | `relocate` → `docs/project-relocation.md` |
| `loc=ok` AND `mgd=no` AND stack または非 docs ソースあり | `migrate` → `docs/project-addition-and-migration.md` |
| `loc=ok` AND `mgd=yes` AND drift 信号 (`nix=missing+has_stack`、`harness_drift`、または `policy_drift` ∈ {`stale`, `diverged`, `ahead-and-behind`, `no-anchor`}) | `realign` → `docs/realignment.md` |
| それ以外 | `no-op` |

Validation / fixture リポジトリ (`mgd=no` で意図的、しばしば `~/ghq/local/...`) は default で P2、Brief には `no-op` としてリストされる。使用者が明示的に sub-flow に opt-in した場合のみ対象になる。

### Brief 構造 (エージェントが JSON から組み立てる)

```markdown
# Projects Audit Brief — YYYY-MM-DD

Source: `python -m ai_ops audit projects --json`
Total: <N> projects (managed=<X>, P0=<a>, P1=<b>, P2=<c>)

## P0 — immediate action (<a> projects)
| project | path | loc | sec | sub-flow | reason |
| ...     | ...  | ... | ... | ...      | ...    |

## P1 — planned action (<b> projects)
| project | path | nix | harness_drift | last | sub-flow | reason |

## P2 — observation only (<c> projects)
- 短いサマリー。何かが目立つのでなければ行ごとの表は不要。
```

表内の reason テキストは具体的なトリガーを引用する (例: "loc=DRIFT (~/work/foo)"、"nix=missing + has_stack=true (package.json)"、"harness_drift=true (3 modified files)")。Brief は各優先度を駆動した正確な信号を浮上させ、使用者が sub-flow を承認する前に意図を確認できるようにする。

## Phase 3 — Execute (プロジェクトごと、確認ごと)

エージェントは Brief を優先度順に walk する — まず全 P0 行、次に P1 行。P2 行は観測のみで自動実行されることはない。action が必要な各行に対して:

1. プロジェクトの path と優先度を発火させた具体的な drift 信号と共に sub-flow を提案する。
2. 個別の使用者確認 (`yes` / `defer` / `skip`) を待つ。ai-ops 運用モデルは一括承認を禁じている。1 確認 = 1 プロジェクトの sub-flow。
3. `yes` のとき、リンクされた playbook を全部追う — その playbook 自身の Phase 1-4 も含む。本監査は sub-flow ステップを skip / 簡略化しない。
4. `defer` / `skip` のとき、後のセッションが拾えるよう Brief に選択を記録する。

Brief が durable state。セッションが中断 (context 圧迫、使用者離席、部分実行) しても、Brief は完了 / 延期 / 保留を示し、次のエージェント起動は同じ Quick start プロンプトでそこから再開できる。

## Phase 4 — Verify (触れたプロジェクトの Discovery を再実行)

Phase 3 の後 (または意図的な一時停止後)、エージェントは触れた全プロジェクトに対して Phase 1 Discovery を再実行し、delta 表を出す。

```text
| project | pri before | pri after | result        |
|---------|------------|-----------|---------------|
| <name>  | P0         | P2        | passed        |
| <name>  | P1         | P1        | partial — see brief |
```

Phase 3 を駆動したのと同じ優先度ロジックは、触れたプロジェクトに対して **P2 以下** に解決しなければならない。なお P0 / P1 のままのものは Brief に理由付きで deferred として記録され、次の監査サイクルの入口になる。

## 制約

- Phase 1 はファイル名、git メタデータ、テキストソースのパターンしか読まない。secret の **値** は決して開かない。
- 各 P0 / P1 プロジェクトは独自の Propose → Confirm → Execute を得る。複数プロジェクトに跨る一括承認は禁止 (AGENTS.md §Operation Model)。
- sub-flow 実行はリンクされた playbook に完全に委譲する。本監査は relocation / migration / realignment ステップを重複定義しない。sub-flow 自身の destructive ステップが確認を要求する場合 (例: relocation Step 2 の `mv`)、その確認は本監査セッション内で提示される。
- Validation / fixture リポジトリ (`mgd=no` で意図的、しばしば `~/ghq/local/...`) は default で P2、使用者が明示的に opt-in しない限り drift カウントから除外。
- Phase 4 は Phase 1 ロジックをそのまま再利用する。別途 "verify" 手順は無し。触れたプロジェクトは P2 以下に落ちなければならない。
- Brief は durable。エージェントは Phase 3 の各 step に対して結果 (`done` / `deferred` / `skipped`) を Brief に書き込まずに次へ進めない。中断後の再開は loss-free。

## 関連

- `AGENTS.md` §Workspace — `~/ghq/` が canonical
- `AGENTS.md` §Operation Model — Propose → Confirm → Execute、一括禁止
- `docs/realignment.md` — 単一プロジェクトの realign sub-flow
- `docs/project-addition-and-migration.md` — 単一プロジェクトの migrate sub-flow
- `docs/project-relocation.md` — 単一プロジェクトの relocate sub-flow
- `ai-ops audit nix --report` — 全プロジェクトを横断する nix-gap サブセット (legacy column-only ビュー)
- `ai-ops audit harness --path <P> --strict` — P1 分類で使われるプロジェクトごとの harness drift
