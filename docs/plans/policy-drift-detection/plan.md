# ai-ops policy drift detection for managed projects

この ExecPlan は作業中に更新する living document である。作業が進むたびに `Progress`、`Surprises & Discoveries`、`Decision Log`、`Outcomes & Retrospective`、`Improvement Candidates` を最新化する。

Plan path: `docs/plans/policy-drift-detection/plan.md`。採用後の archive path: `docs/plans/archive/YYYY-MM-DD-policy-drift-detection/`。

## Purpose / Big Picture

`feat(lifecycle): add self-improvement capture loop` (commit 4258902) で ai-ops 自身に improvement loop を入れたが、改善結果は managed projects に自動波及しない。現在の波及経路は (1) 新規 plan 作成時に templates を snapshot、(2) realignment session で agent が docs を fetch、(3) `ai-ops audit harness` の file-level drift 検出、しかなく、**template schema / lifecycle guidance / AGENTS.md pointer の policy drift は不可視**である。

完了後は、`ai-ops audit projects` を走らせるだけで「ai-ops canonical と各 managed project の policy 差分」が priority-sorted table の 1 column として見えるようになる。検出のみ、修正は既存 `docs/realignment.md` の Phase 1→2→3 を per-project confirmation で通す。auto-write、新 file 形式、新 subcommand、background scheduler は導入しない。

## Progress

- [x] (2026-05-01 06:00Z) `audit projects` / `audit harness` / `audit standard` の現 implementation と JSON shape、`harness.toml` schema、umipal 独自 `templates/plan.md` の divergence、commit 規約を read-only で discovery。
- [x] (2026-05-01 06:30Z) 設計判断 (auto-write 禁止 / harness.toml の `ai_ops_sha` を anchor 流用 / path-based propagation 検出 / 既存 active plan は遡及しない / severity 分類は v2 deferred) を Decision Log に固定。
- [x] (2026-05-01 07:00Z) self-review で 3 refinement 確定: AGENTS.md を policy_drift 対象から外す (project-specific 契約書なので canonical 強制は overreach) / detector 関数は `projects.py`・定数は `_canonical.py` (circular import 回避) / `no-anchor` enum 値を追加 (`stale` と区別、独立 actionable signal)。Decision Log に追記。
- [x] (2026-05-01 07:30Z) `ai_ops/audit/_canonical.py` 新規 (`REQUIRED_PLAN_SECTIONS` + `CANONICAL_LIFECYCLE_PATHS` + `CANONICAL_LIFECYCLE_DIR_PREFIXES`)。templates/plan.md の見出し集合と完全一致を python smoke で確認。
- [x] (2026-05-01 07:35Z) `ai_ops/audit/lifecycle.py:_check_plan_hygiene` を `_canonical.REQUIRED_PLAN_SECTIONS` 利用に refactor。挙動不変、既存 39 tests pass。
- [x] (2026-05-01 07:50Z) `ai_ops/audit/projects.py` に `policy_drift` field + `_detect_policy_drift()` 関数 + severity / sub-flow / JSON / table 統合。
- [x] (2026-05-01 08:00Z) `tests/test_audit.py` に focused test 7 件 (unmanaged / ai-ops self / no-anchor / ok no-plans / stale / diverged / ahead-and-behind / archived plan skip) を追加。`tests/test_audit_projects.py::test_p2_for_clean_managed_project_under_ghq` を実 ai-ops HEAD SHA 利用に更新 (空 ai_ops_sha が新 `no-anchor` 判定で P1 になるため)。
- [x] (2026-05-01 08:10Z) `docs/realignment.md` Phase 1 / Phase 2 Brief に policy drift remediation を追記、`docs/projects-audit.md` の signal 表に `policy_drift` 追加 (8 → 9 signals)、severity 表と sub-flow 表に新 trigger を追記。
- [x] (2026-05-01 08:15Z) `python -m ai_ops check` PASS、67 audit tests pass。実 use 確認: 7 managed projects のうち umipal (P0) / mi_share (P1) / fx-llm-research (P1) で `policy_drift=stale` 検出、audio-dsp-docs / fastener-research は active plan 無しで `ok`、ai-ops 自身と unmanaged 5 件は `n/a`。
- [ ] commit / Adopt 完了後、この plan を `docs/plans/archive/2026-05-01-policy-drift-detection/` に archive する。

## Surprises & Discoveries

- Observation: `harness.toml` には既に `ai_ops_sha` (project が同期した ai-ops commit SHA) と `last_sync` (ISO-8601 UTC) が格納されており、`audit standard --since` は default でこの SHA を ref に使っている。
  Evidence: `ai_ops/audit/harness.py:42-66` (`HarnessManifest` schema)、`ai_ops/audit/standard.py:106-111` (ref 解決順位 `--since` → `harness.toml.ai_ops_sha` → `HEAD~100`)。
  Implication: 新 file 形式や version pin file を導入しなくて良い。policy drift も同 anchor で「project が認識している ai-ops 状態」と「現 HEAD」を比較できる。

- Observation: `audit projects` は既に 11 種類の signal (loc / mgd / nix / sec / dirty / last_commit_age / todo / agents_md / has_stack / is_docs_only / harness_drift) を計算し、P0 / P1 / P2 の severity 分類と relocate / migrate / realign / no-op の sub-flow routing を持っている。
  Evidence: `ai_ops/audit/projects.py:75-94` (`ProjectSignals`)、`:322-335` (severity)、`:337-367` (sub-flow)。
  Implication: 新 signal を 1 つ足すだけで既存 priority table と Brief routing にそのまま乗る。新 subcommand 不要。

- Observation: ai-ops の commit 規約に「managed project に影響する変更」を示す tag は存在しない (`[propagate]` / `[managed]` / `BREAKING` 全てゼロ hit)。
  Evidence: `git log --oneline | head -50` の subject pattern を grep。
  Implication: v1 では path-based heuristic (`templates/` / `docs/ai-first-lifecycle.md` / `docs/self-operation.md` / `docs/realignment.md` / `docs/projects-audit.md` / `AGENTS.md` / `docs/decisions/*` を touch する commit を propagation-relevant とみなす) を採用する。明示 tag は v2 deferred。

- Observation: umipal の独自 `templates/plan.md` は ai-ops canonical から `## Improvement Candidates` を欠き、`Context and Orientation` の位置が異なる。divergence の rationale は AGENTS.md に記録されていない。
  Evidence: umipal `templates/plan.md` (12 top-level 見出し) vs ai-ops canonical (13 top-level 見出し、`Improvement Candidates` 追加分)。umipal `AGENTS.md` には独自完了 contract (`docs/completion-contract.yaml`、F1-F15 / P1-P8 gates) は記録があるが plan.md divergence の理由は無い。
  Implication: umipal は「ahead-and-behind」ケースの実 reference になる。policy drift detection は単なる stale 判定だけでなく、`ahead` / `behind` / `ahead-and-behind` を区別できる必要がある (が、v1 は最小実装として「set 一致 vs 不一致」で良い)。

- Observation: `ai-ops audit lifecycle` の `_check_plan_hygiene` は ai-ops 自身の active plan に対して `## Progress` checkbox と `## Improvement Candidates` 見出し有無を WARN しているが、managed projects の plan には適用されない (各 project 構造が違うため、これは設計上正しい)。
  Evidence: `ai_ops/audit/lifecycle.py:201-262` (`_check_plan_hygiene`)、`docs/ai-first-lifecycle.md` 注記「`ai-ops audit lifecycle` は ai-ops 自身の self-audit、新規 project の audit には使わない」。
  Implication: managed project 側の plan schema 検査は `audit projects` の policy drift signal が担うべき。lifecycle audit との二重実装を避けるため、required sections の定義は 1 箇所 (`ai_ops/audit/_canonical.py` のような新 module) に集約する。

## Decision Log

- Decision: managed projects に対する **auto-write は導入しない**。検出のみ、修正は既存 `docs/realignment.md` の Phase 1 (read-only discovery) → Phase 2 (Brief) → Phase 3 (per-scope confirmation execute) を経る。
  Rationale: AGENTS.md Safety と Operation Model に整合。各 project には deviate 権がある (umipal の独自 template のように、context-specific な選択がある)。auto-write は conflict 解決責任を ai-ops に集中させ、project 側の judgment を奪う。Cross-cutting edits は Propose -> Confirm -> Execute、これは batch 不可。
  Date/Author: 2026-05-01 / Codex

- Decision: version anchor は `harness.toml` の既存 `ai_ops_sha` field を流用する。新 file (`.ai-ops/policy.toml` 等) は作らない。
  Rationale: `audit standard --since` がすでに同 anchor を使っており、infrastructure を二重化しない。policy drift も「project が認識している ai-ops 状態 (= harness sync 時点の SHA) 以降に canonical paths が変わったか」で判定できる。
  Date/Author: 2026-05-01 / Codex

- Decision: 「propagation-relevant」commit は **path-based heuristic** で判定する。canonical paths = `templates/**` / `docs/ai-first-lifecycle.md` / `docs/self-operation.md` / `docs/realignment.md` / `docs/projects-audit.md` / `docs/project-addition-and-migration.md` / `docs/project-relocation.md` / `AGENTS.md` / `docs/decisions/**`。これらを touch する commit が「project へ propagate する可能性がある」候補。commit 規約 (subject の `[propagate]` tag 等) は v1 では導入せず、v2 deferred。
  Rationale: 既存 commit に retroactive tag は付けられない。path heuristic は false-positive (touch しただけで実質変更が無い) はあるが false-negative (propagate すべきなのに見えない) は最小化できる。tag 規約は author discipline に依存し、v1 で強制すると「tag 忘れ → 静かに drift」を生む。
  Date/Author: 2026-05-01 / Codex

- Decision: managed projects の **既存 active plan は遡及更新しない**。新 plan 作成時に新 schema を採用、既存 plan は historical context として保存。
  Rationale: 直前の `self-improvement-loop` plan で archived plans の遡及不要を確定したのと同 logic。実装途中の plan に schema を後付けすると Decision Log / Outcomes が schema 後付けに見える。policy drift signal は「次の plan から canonical schema を使う」ための realignment trigger として機能すれば良い。
  Date/Author: 2026-05-01 / Codex

- Decision: severity は v1 では **policy_drift = P1 一律** とする。mandatory / recommended / informational の意味的分類は v2 deferred。
  Rationale: `harness_drift = P1` と並列の扱いで一貫性が出る。drift の重要度 weighting は実 use 後に評価。今 segmenting すると過剰設計。
  Date/Author: 2026-05-01 / Codex

- Decision: comparison は v1 では **top-level 見出し集合 (`^## ...`) の set diff** に限定する。section 内容の semantic diff は v2 deferred。
  Rationale: 見出し集合の一致は最低限の schema consistency を保証する (`## Improvement Candidates` の有無のような binary な drift を捕捉できる)。section 内容の文字列比較は false-positive が爆発するため、必要になったときに improvement candidate として追加する。
  Date/Author: 2026-05-01 / Codex

- Decision: required canonical 定義は **`ai_ops/audit/_canonical.py` (新 module)** に集約する。`audit lifecycle` の `_check_plan_hygiene` と `audit projects` の policy drift detector は同 module を import する。
  Rationale: 二重実装を避けるため (今回追加する canonical schema 知識は `_check_plan_hygiene` も使うべき)。`_canonical.py` には `REQUIRED_PLAN_SECTIONS`, `CANONICAL_LIFECYCLE_PATHS` の小さな定数を置く。detector 関数本体は signal を持つ module (`projects.py`) に置き、constants だけが共有 module に住む形にすることで circular import を回避する。
  Date/Author: 2026-05-01 / Codex

- Decision: severity = **detection layer は P1 一律**、remediation 重要度は realignment Brief の P0/P1/P2 が担う 2 層構造に固定する。
  Rationale: detection signal は「この project を見るべきか」を coarse に伝える役割、Brief は「何を直すべきか」を fine に分類する役割。同じ axis を 2 度分類すると drift item ごとの真の重要度 (security ADR vs style update) が detector 側にロジックを増やす。これは Brief の責務と重複する。Decision 5 の「v1 で severity 一律」を恒久化し、v2 でも segmenting しない方針として確定。
  Date/Author: 2026-05-01 / Codex (refined after self-review)

- Decision: comparison は **top-level 見出し集合の set diff + 必須 predicate (見出し存在 check)** に限定する。見出し順序の差は drift として検出しない。section 内容の semantic diff は v2 deferred。
  Rationale: 見出し順序 = style、機能を破らない。set membership = schema 一致の最低保証。content semantic diff は false-positive が爆発する。`_check_plan_hygiene` も同じ predicate (見出し存在) を使っているため `_canonical.REQUIRED_PLAN_SECTIONS` で完全に共有できる。
  Date/Author: 2026-05-01 / Codex (refined after self-review)

- Decision: managed projects の **AGENTS.md は policy_drift の対象外** とする。
  Rationale: managed project の AGENTS.md は project-specific な運用契約書であり、ai-ops の AGENTS.md の copy ではない。canonical 文字列 (e.g., 「Improvement capture loop」pointer) を強制するのは overreach。harness drift audit が既に file hash で AGENTS.md を tracking しているのと役割が違う (harness audit は「manifest と一致しているか」、policy drift は「canonical schema を満たすか」)。policy drift の対象は `templates/plan.md` (project 独自版) と active plans の見出し集合 schema に限定する。
  Date/Author: 2026-05-01 / Codex (refined after self-review)

- Decision: enum 値に **`"no-anchor"`** を追加する: `"ok"` / `"stale"` / `"diverged"` / `"ahead-and-behind"` / `"no-anchor"` / `"n/a"`。
  Rationale: `harness.toml` はあるが `ai_ops_sha` が空・無効な場合、技術的に「比較不能」状態。`stale` (古い) と区別すべき独立 actionable signal。`no-anchor` は「まず anchor を立てる realignment が必要」を明示する。realignment Brief 内で「Phase 0: anchor 確立」step が手動で書ける。
  Date/Author: 2026-05-01 / Codex (refined after self-review)

- Decision: propagation 検出方式を **path-based heuristic で恒久化**。`[propagate]` tag は v2 でも opt-in 補強用 enhancement として位置付け、強制しない。
  Rationale: false-positive (有界・可視・低コスト) と false-negative (無限・不可視・高コスト) の非対称性が決定的。author discipline 依存の tag 規約は構造的に false-negative リスクを抱える。Decision 3 (v1 path-based) を恒久化し、tag は補強としてのみ使う方針に格上げ。
  Date/Author: 2026-05-01 / Codex (refined after self-review)

## Outcomes & Retrospective

Shipped:

- `ai_ops/audit/_canonical.py` 新規 (canonical schema 集約 module): `REQUIRED_PLAN_SECTIONS` (13 見出し) / `CANONICAL_LIFECYCLE_PATHS` (11 path) / `CANONICAL_LIFECYCLE_DIR_PREFIXES` (`docs/decisions/`)。
- `ai_ops/audit/projects.py` に `policy_drift` field 追加 + `_detect_policy_drift()` 関数 + severity / sub-flow / JSON output / table column 統合。enum: `ok` / `stale` / `diverged` / `ahead-and-behind` / `no-anchor` / `n/a`。
- `ai_ops/audit/lifecycle.py:_check_plan_hygiene` を `_canonical.REQUIRED_PLAN_SECTIONS` 経由参照に refactor (二重実装防止)。
- `tests/test_audit.py` に focused test 8 件追加 (unmanaged / ai-ops self / no-anchor / ok no-plans / stale / diverged / ahead-and-behind / archived skip)。`tests/test_audit_projects.py` の既存 test 1 件を実 ai-ops HEAD SHA 使用に更新 (空 SHA が `no-anchor` で P1 化するため)。
- `docs/realignment.md` Phase 1 / Phase 2 Brief に policy drift remediation を slot in。`no-anchor` ケースは「Phase 0: anchor 確立」を Brief に明示。
- `docs/projects-audit.md` の signal 表 (8 → 9)、severity 表、sub-flow 表に新 trigger を追記。

Verification:

- `python -m ai_ops check` → PASS、`git diff --check` → clean。
- `python -m pytest tests/test_audit.py tests/test_audit_projects.py` → 67 passed。
- `python -m ai_ops audit projects --json` 実 use: 7 managed projects のうち 3 件 (umipal / mi_share / fx-llm-research) で `policy_drift=stale` を正しく検出。残り 2 managed projects は active plan が無く `ok`、ai-ops 自身は `n/a` (mgd=src)、unmanaged 5 件は `n/a`。signal が discriminating で false-positive ゼロ。
- 既存 `_check_plan_hygiene` の挙動: refactor 後も 39 tests pass で挙動不変を確認。

What remains:

- 本 plan の commit + push + Adopt 完了後の archive。
- Improvement Candidates の deferred items (severity 意味的分類 / `[propagate]` tag 規約 / semantic content diff / `--signal` filter / umipal 個別 remediation) は v2 以降で実 use evidence に基づいて再評価。

What should change in future plans:

- 既存 test の **暗黙の workaround を policy 変更が破る** ケースを着手前に grep で洗い出す。本 plan では `tests/test_audit_projects.py` の「empty `ai_ops_sha` で SHA drift 回避」workaround が新 `no-anchor` 判定で破綻し、実装後の test 失敗で初めて気付いた。Plan of Work step に「既存 test が同 field の workaround を持っていないか pre-flight check」を入れると着手手戻りが減る。これを次 plan の Improvement Candidates 用 dogfood として記録した。

## Improvement Candidates

### severity 分類 (mandatory / recommended / informational)

- Observation: 今は policy drift を一律 P1 にしているが、security ADR 変更は P0 相当、style の prose 更新は P2 以下とすべきケースが将来出る。
- Evidence: 本 plan Decision Log の severity 一律 decision、`audit projects` の既存 P0 (loc DRIFT / sec >= 1) 例。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — severity 変更は P1 → P0 への昇格を含むため per-project realignment の発火条件が変わる。
- Verification: 実 use で「P1 一律だと優先度が分からない」というユーザー fb / 観測が出た時点で再評価。
- Disposition: deferred — v2 で実 use の evidence を見て分類軸を決める。

### commit subject `[propagate]` tag 規約

- Observation: path heuristic は内部 refactor (canonical paths を touch するが実質 propagate 不要) で false-positive を出す。author 明示の tag があれば精度が上がる。
- Evidence: 現状の commit log (`[propagate]` 0 hit、規約なし)。本 plan Decision Log で path-based を選んだ理由。
- Recommended adoption target: `deferred`
- Confirmation needed: no — tag 採用は ai-ops 自身の commit 規約変更で済み、managed project 側に影響しない。
- Verification: path heuristic で false-positive が観測 (e.g., 「templates 内の typo 修正で全 project が realignment 通知される」) されたら採用検討。
- Disposition: deferred — false-positive が実害になってから対応。

### umipal の独自 `templates/plan.md` 整理

- Observation: umipal は ai-ops canonical から `## Improvement Candidates` を欠き、`Context and Orientation` を移動している。divergence の rationale が AGENTS.md に無い。
- Evidence: umipal `templates/plan.md` (12 見出し) vs ai-ops canonical (13 見出し)。umipal `AGENTS.md` の調査結果。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — umipal の realignment session として個別 confirmation 必要。
- Verification: 本 plan の policy drift signal が完成後、umipal で `ai-ops audit projects` を実行 → drift surface → realignment Brief 提示 → user confirmation。
- Disposition: deferred — 本 plan の scope は ai-ops 側の検出機構の追加で、umipal の remediation は別 session で対処。

### section 内容の semantic diff

- Observation: 見出し集合一致だけでは「同じ見出しだが中身が大幅に変わった」case を見逃す (e.g., `## Plan of Work` の手順が canonical で大きく変わったが見出し名は同じ)。
- Evidence: 本 plan Decision Log の comparison 範囲を「top-level 見出し集合」に限定した記述。
- Recommended adoption target: `deferred`
- Confirmation needed: no — 検出のみの追加。
- Verification: 「見出しは合っているのに guidance が古い」という drift が実 use で観測されたら、subsection 見出し (`^### ...`) や key phrase の grep による diff を追加検討。
- Disposition: deferred — false-negative を観測してから対応。

### realignment 適用が必要な project の sweep view

- Observation: `audit projects` は priority-sorted table を出すが、「policy drift がある project だけ抽出」する CLI flag は無い。
- Evidence: `ai_ops/audit/projects.py` の既存 flag (`--json`、`--priority {P0,P1,P2,all}`)。
- Recommended adoption target: `deferred`
- Confirmation needed: no — 出力 filter の追加のみ。
- Verification: managed project が増えて table が長くなり、policy drift だけ見たいニーズが出たら `--signal policy-drift` のような flag を検討。
- Disposition: deferred — 現状 7 managed projects で table が長すぎるわけではない。

### 既存 test の暗黙 workaround を pre-flight で検出する手順

- Observation: 本 plan では `tests/test_audit_projects.py::test_p2_for_clean_managed_project_under_ghq` が「空 `ai_ops_sha` で SHA drift 回避」という暗黙 workaround を持っており、新 `no-anchor` 判定が P1 を発火させて test が落ちた。Plan of Work で事前に grep していれば回避できた。
- Evidence: 本 plan What should change セクション、commit 修正の理由 (test fix が必要だった)。
- Recommended adoption target: `template`
- Confirmation needed: no — 次 plan の Plan of Work に 1 step 足すだけ。
- Verification: 次に signal field を追加 / 変更する plan で、関連 module の既存 test を grep してから実装に入る pre-flight check が機能するか観察。
- Disposition: open — 次の signal 追加 plan で運用検証する。templates/plan.md の Plan of Work 例示にも入れるか検討。

## Context and Orientation

現在の relevant artifacts:

- `ai_ops/audit/projects.py` — `audit projects` の本体。`ProjectSignals` dataclass に signal 追加点。
- `ai_ops/audit/harness.py:42-66` — `HarnessManifest` schema。`ai_ops_sha` field が version anchor。
- `ai_ops/audit/standard.py:106-111` — `--since` ref 解決ロジック。policy drift も同じ anchor を使う。
- `ai_ops/audit/lifecycle.py:201-262` — `_check_plan_hygiene`。required plan sections の判定 logic は `_canonical.py` に集約後、ここから import する。
- `docs/realignment.md` — Phase 1 audit list と Phase 2 Brief の P0/P1/P2 構造。policy drift は P1 structural として slot in。
- `docs/projects-audit.md` — `audit projects` の use ガイド。新 signal の説明を追加する。
- `templates/plan.md` — canonical schema (13 top-level 見出し)。

参照済みの設計原則:

- AGENTS.md Safety: tracked files の auto-modify 禁止、background scheduler install 禁止。
- AGENTS.md Operation Model: cross-cutting edits は Propose -> Confirm -> Execute、batch 不可。
- ADR 0008: 大きな external workflow framework は退けた前例。本 plan も既存 audit を拡張するだけで新 framework を入れない。

## Plan of Work

1. `ai_ops/audit/_canonical.py` を新規追加し、`REQUIRED_PLAN_SECTIONS` (現 canonical の `^## ` 見出し集合) と `CANONICAL_LIFECYCLE_PATHS` (path-based propagation 判定用) を tuple / frozenset として定義。AGENTS.md pointer 集合は出さない (Decision: AGENTS.md は対象外)。
2. `ai_ops/audit/lifecycle.py:_check_plan_hygiene` を `_canonical.REQUIRED_PLAN_SECTIONS` を使うように refactor (現 hardcode された `## Improvement Candidates` 検査を const 化)。挙動は変わらない。
3. `ai_ops/audit/projects.py` の `ProjectSignals` に `policy_drift: str` field を追加 (値 enum: `"ok"` / `"stale"` / `"diverged"` / `"ahead-and-behind"` / `"no-anchor"` / `"n/a"`)。
4. `_detect_policy_drift(project_root, ai_ops_root)` 関数を `projects.py` に追加。判定ロジック:
   - project が unmanaged (`harness.toml` 無し) → `"n/a"`
   - project が ai-ops 自身 (`mgd == "src"`) → `"n/a"` (lifecycle audit が責任を持つ)
   - `harness.toml` 読み込み時に `ai_ops_sha` が空・無効 → `"no-anchor"` (比較不能、anchor 確立が先決)
   - 以下を順に check:
     - project の `templates/plan.md` が存在し、top-level 見出し集合が canonical と異なる → drift
     - project の `docs/plans/*/plan.md` (active のみ、archive 除外) のいずれかが `REQUIRED_PLAN_SECTIONS` を欠く → drift
   - drift の方向 (`ahead` = project にあるが canonical に無い見出し、`behind` = canonical にあるが project に無い見出し) を集計し、`stale` (behind のみ) / `diverged` (どちらか一方の片寄り) / `ahead-and-behind` (両方) に分類。drift 無し → `"ok"`。
5. severity / sub-flow ロジックを更新:
   - `policy_drift in ("stale", "diverged", "ahead-and-behind", "no-anchor")` かつ現 P が P2 → P1 に昇格
   - sub-flow は managed project なら `realign` (既存と整合)
6. `--json` 出力に `policy_drift` field を追加。
7. table 出力に新 column を追加 (短縮表記、e.g., `pdr` で `ok` / `stl` / `div` / `a&b` / `noa` / `n/a`)。
8. `tests/test_audit.py` に focused tests を追加:
   - unmanaged project → `n/a`
   - managed project が canonical と一致 → `ok`
   - managed project が `## Improvement Candidates` を欠く active plan を持つ → `stale`
   - managed project に独自見出しがある (umipal 相当) → `ahead-and-behind`
   - managed project の `harness.toml` に `ai_ops_sha` 欠落 → `no-anchor`
   - ai-ops 自身 → `n/a`
9. `docs/realignment.md` Phase 1 の audit リストに「`ai-ops audit projects` の `policy_drift` column を確認」を追加 (新コマンドではないので 1 行追記で済む)。
10. `docs/realignment.md` Phase 2 Brief の P1 structural セクションに「policy drift remediation: canonical schema を満たさない自前 templates / active plans の更新提案」を追記。`no-anchor` ケースは「Phase 0: anchor 確立 (`ai_ops_sha` を harness.toml に書き込む harness sync 経由)」を Brief に明示する。
11. `docs/projects-audit.md` の signal 解説に `policy_drift` を追加。

## Concrete Steps

repository root から:

```sh
git status --short --branch
```

Expected: 本 plan ファイル以外に unrelated local changes が無い。

編集候補:

- `ai_ops/audit/_canonical.py` (新規)
- `ai_ops/audit/projects.py`
- `ai_ops/audit/lifecycle.py` (canonical const への refactor のみ)
- `tests/test_audit.py`
- `docs/realignment.md`
- `docs/projects-audit.md`

その後:

```sh
python -m pytest tests/test_audit.py
python -m ai_ops audit lifecycle
python -m ai_ops audit projects --json | jq '.[] | {path, mgd, policy_drift, sub_flow}'
python -m ai_ops check
git diff --check
```

Expected: pytest pass、`audit projects --json` の各 entry に `policy_drift` field がある、umipal を含む managed projects で `policy_drift != "ok"` が観測される。

Nix が available なら最終確認に:

```sh
direnv exec . sh -c '
set -e
nix flake check --all-systems --no-build
nix build --no-link ".#checks.$(nix eval --impure --raw --expr builtins.currentSystem).all"
'
```

## Validation and Acceptance

### Machine-checkable

- `ai_ops/audit/_canonical.py` が存在し、`REQUIRED_PLAN_SECTIONS` と `CANONICAL_LIFECYCLE_PATHS` を export する。AGENTS.md pointer 集合は出さない (Decision で対象外)。
- `ai_ops/audit/projects.py` の `ProjectSignals` dataclass に `policy_drift: str` field がある。
- `ai-ops audit projects --json` の各 entry に `policy_drift` key が含まれ、値が `"ok"` / `"stale"` / `"diverged"` / `"ahead-and-behind"` / `"no-anchor"` / `"n/a"` のいずれか。
- `tests/test_audit.py` に新 test (unmanaged → `n/a` / canonical match → `ok` / Improvement Candidates 欠如 → `stale` / 独自見出し → `ahead-and-behind` / `ai_ops_sha` 欠落 → `no-anchor` / ai-ops self → `n/a`) が存在し、`python -m pytest tests/test_audit.py` 全 pass。
- `ai_ops/audit/lifecycle.py:_check_plan_hygiene` が `_canonical.REQUIRED_PLAN_SECTIONS` を import して使い、`_check_plan_hygiene` 内に hardcoded された `Improvement Candidates` 文字列が無い (canonical const 経由で参照)。
- `python -m ai_ops check` PASS / FAIL = 0 / 0、`git diff --check` clean。

### Human-reviewable

- `docs/realignment.md` の Phase 1 audit list と Phase 2 Brief の P1 structural セクションに policy drift remediation が記載されている。
- `docs/projects-audit.md` の signal 解説に `policy_drift` が含まれ、enum 値の意味が説明されている。
- `audit projects` の table 出力に新 column が追加され、既存 column と幅が破綻していない (Windows / narrow terminal でも reasonable に表示される)。

fail した場合は、どの criteria がどの理由で fail したかをこの plan の `Outcomes & Retrospective` に記録する。

## Out of Scope

この pass で意図的に触らないもの (各項目は対応する Improvement Candidate を Decision Log で deferred として記録済み):

- managed projects の tracked files への auto-write (新コマンド `ai-ops sync` 等)
- 新 file 形式 (`.ai-ops/policy.toml`、独立 version pin file 等) の追加
- 新 subcommand (`ai-ops audit policy`、`ai-ops sync` 等)
- 既存 active plan の遡及 schema 適用 (新 plan 作成時から canonical schema を使う運用)
- severity の意味的分類 (mandatory / recommended / informational)
- commit subject `[propagate]` tag 規約の導入
- section 内容の semantic diff (見出し集合一致のみで判定する)
- `audit projects` 出力 filter (`--signal policy-drift` 等)
- managed projects に対する CI / scheduler の install (AGENTS.md Safety)
- umipal / fx-llm-research / mi_share 等の個別 remediation (本 plan の scope は検出機構のみ、各 project の realignment は別 session で confirmation 経由)

## Idempotence and Recovery

この work は (1) 新 module 追加、(2) 既存 module の field / 関数追加、(3) doc 追記が中心で、Git diff review により reversible である。`_check_plan_hygiene` の refactor は挙動不変なので既存 test (`tests/test_audit.py:test_lifecycle_audit_warns_when_improvement_candidates_section_missing` 等) で regression 検知できる。`audit projects` の table column 追加が既存 user の output parsing を破壊する risk があるため、初回実装後に `python -m ai_ops audit projects` の出力を 1 度確認する。

`ai_ops/_resources/` は build artifact なので手で書かない (setup.py が build 時に同期する)。

## Artifacts and Notes

Discovery summary (報告内容を保存):

- `ai-ops audit projects` 既存 signal: 11 項目、severity P0/P1/P2、sub-flow relocate/migrate/realign/no-op (`ai_ops/audit/projects.py:75-94, 322-367`)。
- `harness.toml` schema: `ai_ops_sha`, `last_sync`, `[harness_files]` (`ai_ops/audit/harness.py:42-66`)。`audit standard --since` は default で `harness.toml.ai_ops_sha` を使う (`ai_ops/audit/standard.py:106-111`)。
- `realignment.md` Phase 2 Brief: P0 doc-only / P1 structural / P2 behavioral の三段構造、Phase 1 audit list は 5 commands。
- umipal 独自 `templates/plan.md`: canonical 13 見出しのうち `## Improvement Candidates` を欠く、`Context and Orientation` の位置が異なる。AGENTS.md に rationale 記録なし。
- ai-ops commit subject 規約: `[propagate]` / `[managed]` / `BREAKING` 全て 0 hit。conventional commit prefix (`feat(scope):` 等) のみ。

Managed projects scope (本 plan で signal 対象になる):

- `paasukusai/mi_share` (managed, harness drift あり)
- `tekitounix/audio-dsp-docs` (managed, docs-only)
- `tekitounix/fastener-research` (managed)
- `tekitounix/fx-llm-research` (managed, T2 private 永久)
- `tekitounix/umipal` (managed, 独自 templates/plan.md あり)

skip (本 plan で `n/a` 扱い):

- `tekitounix/ai-ops` (`mgd == "src"`、lifecycle audit 担当)
- `tekitounix/knx3` (unmanaged、harness.toml なし)
- `tekitounix/note-md` (unmanaged)
- `local/tekitounix/ai-ops-*validation*` 4 件 (validation fixtures、`docs/projects-audit.md` で fixture として exclude されている)

## Interfaces and Dependencies

この plan は以下に影響しうる:

- `audit projects` の JSON output schema (新 `policy_drift` field 追加、既存 field は変更なし)
- `audit projects` の table output (新 column 追加、column 順序変更なし)
- `audit projects` の severity 計算 (P2 → P1 昇格条件追加)
- `realignment.md` の Brief 構造 (P1 structural に新 remediation 種類追加)
- `_check_plan_hygiene` の internal implementation (canonical const 集約 refactor、挙動不変)

新規 runtime dependencies、external services、background automation、user-environment changes は追加しない。
