# AI運用の自己改善ループ

この ExecPlan は作業中に更新する living document である。作業が進むたびに `Progress`、`Surprises & Discoveries`、`Decision Log`、`Outcomes & Retrospective` を最新化する。

Plan path: `docs/plans/self-improvement-loop/plan.md`。採用後の archive path: `docs/plans/archive/YYYY-MM-DD-self-improvement-loop/`。

## Purpose / Big Picture

この変更の目的は、AI agent が作業後に得た知見を自然に次の運用へ反映できるようにしつつ、毎回の作業が無制限なプロセス改変にならないよう境界を作ることである。

完了後は、AI agent が非自明な作業を終える前に、何を current plan に残すべきか、何を durable docs / ADR / templates / audit / harness に採用すべきか、何を延期すべきかを判断できる状態にする。改善候補は plan の `Improvement Candidates` section で常時捕捉し、広範・破壊的・標準化を伴う変更は Propose -> Confirm -> Execute を通す。harness drift detection (`ai_ops/audit/harness.py`) は drift 検出を担うのみで、新規改善候補の inbox にはしない。

## Progress

- [x] (2026-05-01 03:11Z) 現在の lifecycle、plan、self-operation、harness、lifecycle audit を確認し、初版 plan を作成。
- [x] (2026-05-01 03:20Z) plan の作業言語が誤って英語になっていたため、日本語へ修正。
- [x] (2026-05-01 03:30Z) `AGENTS.md` の旧 language policy が誤りであることを受け、README.md だけを英語 default とする方針へ active docs / prompt を更新。
- [x] (2026-05-01 03:45Z) `ghq list -p` 配下の managed projects を read-only 走査し、language policy drift 候補を確認。
- [x] (2026-05-01 03:50Z) `ghq list -p` 全 12 repo にも旧 language policy exact scan を拡張し、`ai-ops audit projects --json` の現状を確認。
- [x] (2026-05-01 04:30Z) 初版 plan のセルフレビューで未決事項 5 件 (enum / single-source / inbox / 遡及 / WARN 閾値) を Decision Log に固定し、Improvement Candidates Schema を plan body に明記、Acceptance criteria を machine-checkable / human-reviewable に分離、Out of Scope を独立 section 化。
- [x] (2026-05-01 05:10Z) 実装着手時に `ai_ops/lifecycle/plans.py` の embedded string が fallback ではなく promote-plan 用 generator と判明。Decision Log の該当 entry を「schema consistency test で drift 防止」に修正。
- [x] (2026-05-01 05:20Z) `templates/plan.md` と `build_promoted_plan` 両方に `## Improvement Candidates` section を追加。
- [x] (2026-05-01 05:25Z) `docs/ai-first-lifecycle.md` に `## Improvement Capture` 節、`docs/self-operation.md` に `## Improvement Capture Loop` 節を追加。`AGENTS.md` の Plans section に 1 行 pointer 追加。
- [x] (2026-05-01 05:30Z) `ai_ops/audit/lifecycle.py:_check_plan_hygiene` に 2 WARN 追加 (Improvement Candidates 見出し欠如、Progress 完了 + Outcomes TBD)。`tests/test_audit.py` に focused test 3 件 + schema consistency test 1 件追加 (39 tests pass)。
- [x] (2026-05-01 05:35Z) 本 plan 自身に Improvement Candidates section を追加し dogfood。`python -m ai_ops check` clean、`git diff --check` clean。
- [ ] commit / Adopt 完了後、この plan を `docs/plans/archive/2026-05-01-self-improvement-loop/` に archive する。

## Surprises & Discoveries

- Observation: ai-ops には、repo-local plans、self-operation、harness drift detection、projects audit、ADR boundaries という必要な部品がすでに揃っている。
  Evidence: `README.md`、`docs/ai-first-lifecycle.md`、`docs/self-operation.md`、`templates/plan.md`、`ai_ops/audit/harness.py`、`ai_ops/audit/lifecycle.py`。

- Observation: 足りないのは大きな外部 framework ではなく、implementation 中の発見を適切な artifact へ振り分ける explicit adoption loop である。
  Evidence: `templates/plan.md` は progress と discoveries の更新を求めているが、improvement candidates と adoption boundaries を評価する dedicated section はまだ無い。

- Observation: lifecycle audit は Progress checkbox の欠落や stale active plan を警告するが、非自明な plan が outcomes や improvement capture を持つかまでは見ていない。
  Evidence: `ai_ops/audit/lifecycle.py` の `_check_plan_hygiene`。

- Observation: この plan は当初英語で作成されたが、今回の作業では日本語で書くべきだった。
  Evidence: ユーザーは日本語で依頼しており、対象となる lifecycle / self-operation docs も日本語を主に使っている。

- Observation: `AGENTS.md` の旧 language policy は、owner が日本語話者である現実と合っていなかった。
  Evidence: ユーザーが「私は日本語話者なので基本日本語」「README.md のみ英語を default」「完成していて公開を目的としている場合のみ重要度に応じて英語 docs を用意」と明示した。

- Observation: managed projects 6 件の active docs には、旧 ai-ops 方針の exact match は残っていなかった。
  Evidence: `.ai-ops/harness.toml` がある project と ai-ops 自身を対象に、`English by default` / `AGENTS.md should stay English` / `Working docs may use Japanese` / `README 英語化` 等を `rg` で検索した。

- Observation: `fastener-research` と `fx-llm-research` は、README.md 自体を日本語運用として明記しており、新方針を全 managed project に適用するなら drift 候補である。
  Evidence: `fastener-research/AGENTS.md` は `README.md` を working notes として日本語扱いし、T1 昇格時に `README.en.md` 追加または主 README 英訳を検討するとしている。`fx-llm-research/AGENTS.md` は T2 private 恒久として `README / AGENTS.md / docs / research notes: 日本語`、英語 sibling 不要と明記している。

- Observation: `mi_share`、`audio-dsp-docs`、`umipal` は、`README.md` を英語 entrypoint とし、README 以外を日本語中心にする方針で概ね整合している。
  Evidence: 各 repo の `README.md` head と `AGENTS.md` language policy を read-only で確認した。

- Observation: `ghq list -p` 全 12 repo に広げても、旧 language policy の exact hit はこの plan 自身の証跡以外には無かった。
  Evidence: managed scope と同じ `rg` pattern を全 `ghq list -p` repo に実行した。

- Observation: language policy とは別に、`ai-ops audit projects --json` は managed project の多くに harness drift を出している。
  Evidence: `umipal` は P0 / realign、`mi_share`、`audio-dsp-docs`、`fastener-research`、`fx-llm-research` は P1 / realign、`note-md` は P1 / migrate。これは今回の言語方針修正とは別 scope で、project ごとの confirmation が必要。

- Observation: 初版 plan のレビューで、実装直前に揺れる未決事項が 5 件残っていた: disposition / target の語彙、template schema の二重ソース、deferred candidate の集約場所、archived plans への遡及方針、lifecycle audit の WARN 閾値。
  Evidence: 同 plan の初版 (Decision Log 5 件時点) は target 列挙を散文で書きながら enum を固定していなかった。`ai_ops/lifecycle/plans.py` には embedded fallback がある (要 single-source 化)。`docs/plans/archive/` の遡及方針は本 plan に明示が無かった。
  Resolution: Decision Log に 5 件追加し、Plan of Work / Validation and Acceptance を更新した。

- Observation: 「harness が常に改善候補を捕捉する」と書くと、`.ai-ops/harness.toml` 自体が improvement notes の格納先かのように誤読される。
  Evidence: `ai_ops/audit/harness.py` は harness file の drift detection のみ。improvement notes を harness manifest に書く設計ではない。
  Resolution: Purpose section を「改善候補は plan の Improvement Candidates section で常時捕捉、harness drift detection は drift 検出のみを担う」と書き直した。

- Observation: 実装着手時に code を読み直したところ、`ai_ops/lifecycle/plans.py` の embedded string は `templates/plan.md` の fallback ではなく `promote-plan` 専用の独立 generator (slug / source path / 日付を埋め込む) だった。`ai_ops/_resources/templates/plan.md` は `setup.py` build hook が自動生成する複製。
  Evidence: `setup.py:5-6` (build hook が `templates/` を `_resources/` にコピー)。`pyproject.toml:27` (package-data 設定)。`plans.py:36-94` (`build_promoted_plan` の content は promotion-specific)。
  Resolution: 「embedded fallback 削除」Decision を「両 template に `Improvement Candidates` を追加し、schema consistency test で drift 防止」に修正。`_resources/` は build artifact なので手で書き換えない方針を Plan of Work step 1 に明記。

## Decision Log

- Decision: 自己改善は「常に捕捉し、選択的に採用する」と定義する。
  Rationale: 常時捕捉により drift を防ぎ、選択的採用により単発事例への過適合や予告なしの運用変更を防ぐ。
  Date/Author: 2026-05-01 / Codex

- Decision: 参照は浅く保ち、各 execution plan は単体で再開可能にする。
  Rationale: ユーザーの doc policy と、ai-ops の compact entrypoint + one-level playbook 方針に合う。
  Date/Author: 2026-05-01 / Codex

- Decision: この pass では full external spec framework を導入しない。
  Rationale: ADR 0008 は大きな workflow framework の導入を一度退けている。今回必要なのは既存 lifecycle 内の軽量 loop である。
  Date/Author: 2026-05-01 / Codex

- Decision: この plan は日本語で管理する。
  Rationale: 今回の作業言語が日本語であり、運用判断をユーザーが低コストで確認できることが重要である。owner が日本語話者である以上、運用 docs / plans は日本語を default とする。
  Date/Author: 2026-05-01 / Codex

- Decision: Natural language policy は、README.md のみ英語 default、運用 docs / AGENTS.md / issues / PRs / briefs / plans は日本語 default とする。
  Rationale: owner の主要言語に合わせるほうが運用コストが低く、README.md は GitHub の public first entrypoint として英語 default を保てば外部利用者も排除しにくい。README 以外の英語 docs は公開目的と重要度に応じて増やす。
  Date/Author: 2026-05-01 / Codex

- Decision: `Improvement Candidates` の `recommended adoption target` は次の enum に固定する: `current-plan` / `durable-doc` / `adr` / `template` / `audit` / `harness` / `test` / `deferred` / `rejected`。`disposition` は `open` / `adopted` / `deferred` / `rejected` / `superseded` の 5 値に固定する。
  Rationale: 自由記述だと plan ごとに語彙が揺れ、後で grep / aggregation できなくなる。enum を固定すれば lifecycle audit や将来的な report 生成が機械可能になる。
  Date/Author: 2026-05-01 / Codex

- Decision: plan template の正本は `templates/plan.md` (file) のみとする。`ai_ops/_resources/templates/plan.md` は `setup.py` の build hook が生成する複製で source of truth ではない。`ai_ops/lifecycle/plans.py:build_promoted_plan` は `templates/plan.md` の fallback ではなく `promote-plan` 専用の独立 generator (slug / source path / 日付を埋め込む) なので削除しない。両者は別 template だが schema (top-level 見出し集合) は揃える義務があり、`tests/test_packaging.py` または新 test で見出し一致を assert する。
  Rationale: 「fallback 削除」と当初書いたが、実 code を読み直したところ `build_promoted_plan` は fallback ではなく別目的の generator だった。物理 single-source 化は不可能 (substituted content が大幅に違う)。代わりに「schema consistency を test で担保」という形で同等の drift 防止を実現する。
  Date/Author: 2026-05-01 / Codex (revised after reading `plans.py`)

- Decision: `deferred` 状態の improvement candidate は、各 plan の `Improvement Candidates` section にとどめる。`docs/plans/_inbox.md` のような cross-plan inbox は今回は作らない。同じ candidate が複数 plan に重複した場合は、新しい plan で「prior plan の candidate を superseded として参照」する形で集約する。
  Rationale: inbox を作ると「inbox の hygiene を誰が見るか」という新しい責任が発生し、現状の lifecycle audit と Operation Model に追加の運用 surface が乗る。candidate が本当に重要なら独立した plan / ADR に昇格すれば十分で、軽い deferred は archived plan からの掘り起こしで足りる。3 plan 連続で同じ candidate が deferred されたら inbox 化を再検討する。
  Date/Author: 2026-05-01 / Codex

- Decision: archived plans (`docs/plans/archive/`) は新 schema を遡及適用しない。historical record として現状のまま保存する。
  Rationale: archive の本質は「その時点でどう判断したか」の固定。新 section を後付けすると当時の意思決定と区別がつかなくなる。lifecycle audit も active plan のみを対象にする。
  Date/Author: 2026-05-01 / Codex

- Decision: lifecycle audit の plan hygiene 強化は次の 2 条件のみを WARN とする: (a) active plan に `## Improvement Candidates` 見出しが無い、(b) Adopt 済み (= archive 候補) と判定できる plan の `Outcomes & Retrospective` が `TBD` のまま。それ以外 (candidate の中身、disposition enum 整合性) は今回は audit せず、人間レビューに委ねる。
  Rationale: 機械検査の閾値を低く保つことで、warning noise を最小化しつつ「section 自体の有無」だけを保証できる。enum 整合性 audit は schema 安定後に第二段で導入する。
  Date/Author: 2026-05-01 / Codex

## Outcomes & Retrospective

Shipped:

- `templates/plan.md` と `build_promoted_plan` 両方に `## Improvement Candidates` section + 6-field schema + enum 値定義を追加。
- `docs/ai-first-lifecycle.md` に `## Improvement Capture` 節 (1 段落)、`docs/self-operation.md` に `## Improvement Capture Loop` 節 (enum 振り分け checklist) を追加。
- `AGENTS.md` の Plans section に Improvement Candidates の言及 1 行と 2 docs への pointer 1 行を追加。loop の mechanics は AGENTS.md に持ち込まず、参照だけに留めた。
- `ai_ops/audit/lifecycle.py:_check_plan_hygiene` に 2 WARN 追加: `## Improvement Candidates` 見出し欠如、Progress 全 [x] かつ Outcomes が TBD。
- `tests/test_audit.py` に focused test 3 件 (新 WARN 2 件 + healthy plan は WARN しない) と schema consistency test 1 件 (templates/plan.md と build_promoted_plan の top-level 見出し集合一致) を追加。`python -m pytest tests/test_audit.py` 39 件 pass。
- 本 plan 自身に Improvement Candidates 4 件を記録し dogfood (plans.py 誤読、language policy drift、projects audit P1/P0、semantic audit 見送り)。

Verification:

- `python -m ai_ops check` → PASS 36 / WARN 0 / FAIL 0。
- `git diff --check` → clean。
- `tests/test_audit.py` → 39 passed。
- 新 WARN は本 plan に Improvement Candidates section を追加した後、消えることを確認。

What remains:

- 本 plan の commit + Adopt 完了後の archive。
- 他 project (`umipal` P0、`mi_share` 他 4 件 P1) の harness drift 是正は本 plan の Out of Scope。各 project の realignment / migration として個別 confirmation を経て対処。
- `Improvement Candidates` 中身の semantic audit (enum 整合性 / disposition 妥当性) は schema 安定後の第二段で再評価。

What should change in future plans:

- 実装着手前に必ず関連 source code を一度読み、Decision Log の前提を verify する。本 plan は initial review 段階で `ai_ops/lifecycle/plans.py` を読まずに「embedded fallback がある」と書き、実装着手時に修正する手戻りが発生した。templates/plan.md の `Plan of Work` 着手前に「前提となる code 読解」を 1 step 入れる運用を Improvement Capture Loop の deferred candidate として記録した。
- 言語方針のような cross-cutting policy 修正は、plan を書き始める前に CLAUDE.md / AGENTS.md を確認する。本 plan は冒頭で言語の方向転換が発生し、修正に 1 cycle 余計にかかった。

## Improvement Candidates

### plans.py の build_promoted_plan を「fallback」と誤認した

- Observation: 初版の Decision Log は `plans.py` に embedded fallback がある前提で書かれていたが、実際は promote-plan 専用の独立 generator だった。
- Evidence: `setup.py:5-6` (build hook が `templates/` を `_resources/` に複製)。`pyproject.toml:27` (package-data 設定)。`ai_ops/lifecycle/plans.py:36-94` (`build_promoted_plan` は slug / source path / 日付を埋め込む、generic fallback ではない)。
- Recommended adoption target: `current-plan`
- Confirmation needed: no — plan の Decision Log を書き換え済み。
- Verification: 本 plan の Decision Log の該当 entry に `(revised after reading plans.py)` を付記。
- Disposition: adopted — 同 plan 内で吸収。

### 言語方針の方向転換は active な再採用が必要だった

- Observation: 初版 plan は誤った language policy で書かれ、修正に 1 cycle 余計にかかった。
- Evidence: 本 plan の Progress (2026-05-01 03:20Z, 03:30Z) と Decision Log (74-87 行)。
- Recommended adoption target: `deferred`
- Confirmation needed: no — 個別 process 改善案として今回は採用しない。
- Verification: n/a
- Disposition: deferred — 単発事例なので、再現したら「作業開始時に CLAUDE.md / AGENTS.md の language policy を確認する」を audit / template 化を再検討。

### projects audit の P1 / P0 が複数残っている

- Observation: `umipal` が P0、`mi_share` / `audio-dsp-docs` / `fastener-research` / `fx-llm-research` / `note-md` が P1 で remediation 待ち。
- Evidence: `python -m ai_ops audit projects --json` (本 plan Artifacts and Notes 参照)。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — 各 project ごとに realignment / migration の confirmation が必要。
- Verification: 各 project で `ai-ops audit harness` / `ai-ops audit nix` が clean になる。
- Disposition: deferred — 本 plan の scope 外。別 session で project ごとに対処。

### lifecycle audit の semantic check は今回は導入見送り

- Observation: `Improvement Candidates` の中身 (enum 整合性、disposition 妥当性) を audit する案を検討したが、見送った。
- Evidence: 本 plan Decision Log の最終 entry (lifecycle audit の WARN 条件は 2 件のみ)。
- Recommended adoption target: `deferred`
- Confirmation needed: yes — 導入時は新 WARN noise が大きく、Operation Model に従う必要がある。
- Verification: schema が安定し、active plan 数が増えて enum drift が観察された段階で再検討。
- Disposition: deferred — 第二段で再評価。

## Context and Orientation

現在の relevant artifacts:

- `AGENTS.md` は cross-agent operation contract。transient task state は置かない。
- `docs/ai-first-lifecycle.md` は `Intake -> Discovery -> Brief -> Proposal -> Confirm -> Agent Execute -> Verify -> Adopt` を定義する。
- `docs/self-operation.md` は ai-ops 自身の dogfood procedure を定義する。
- `templates/plan.md` は active execution plan の schema。
- `ai_ops/audit/lifecycle.py` は ai-ops structural self-audit と plan hygiene warnings を担当する。
- `ai_ops/audit/harness.py` は project harness files と `.ai-ops/harness.toml` の drift を検出する。新たに得た運用知見を harness standard に採用すべきかは判断しない。

今回参照済みの external guidance:

- OpenAI GPT-5.5 guidance: outcome と success criteria を明確にし、product が要求しない詳細手順は減らす。ただし coding workflows では orchestration、acceptance criteria、test expectations、continuation rules が必要。
- Anthropic Claude guidance: success criteria と evals を prompt engineering 前に定義する。Claude は explicit scope と output constraints に literal に従う。review harness は model-specific validation が必要。
- Claude Skills guidance: instruction は concise にし、progressive disclosure を使い、深い nested references を避け、quality-critical tasks では validation loop を含める。
- FindSkill.ai: packaged skill template の参考にはなるが、ai-ops に大きな template body を増やす理由にはしない。

## Plan of Work

1. plan template に `Improvement Candidates` section を追加し、schema consistency を test で担保する。
   `templates/plan.md` (top-level、source of truth) と `ai_ops/lifecycle/plans.py:build_promoted_plan` の出力 (promote-plan 用の独立 generator) の両方に `## Improvement Candidates` section を追加する。`ai_ops/_resources/templates/plan.md` は build artifact なので手で書き換えない (`setup.py` が次回 build 時に自動同期する)。schema drift を防ぐため、`tests/test_packaging.py` (または `tests/test_audit.py`) に「`templates/plan.md` と `build_promoted_plan(...)` の top-level 見出し集合が一致する」 test を 1 件追加する。

2. `Improvement Candidates` section の schema を確定する。
   `templates/plan.md` 末尾に下記 `Improvement Candidates Schema` (本 plan body 参照) と同じ構造を埋め込み、各 candidate が次の 6 fields を持つようにする: `Observation` / `Evidence` / `Recommended adoption target` (enum) / `Confirmation needed` (yes/no + reason) / `Verification` / `Disposition` (enum)。enum 値は Decision Log の固定値を inline 列挙する。

3. lifecycle docs に self-improvement loop を追加する。
   `docs/ai-first-lifecycle.md` に `## Improvement Capture` 見出しを 1 つ追加し、`Agent Execute` / `Verify` / `Adopt` の中で discovery capture → triage → durable adoption / deferred の分岐を 1 段落で説明する。深い nested guidance は書かず、`templates/plan.md` と `docs/self-operation.md` への pointer に留める。

4. self-operation に dogfood rule を追加する。
   `docs/self-operation.md` に `## Improvement Capture Loop` 見出しを 1 つ追加し、ai-ops 自身の作業完了前に discoveries を `current-plan` / `durable-doc` / `adr` / `template` / `audit` / `harness` / `test` / `deferred` / `rejected` のどれに振るかを決める短い checklist を置く。広範・破壊的・harness standard / ADR change は Propose -> Confirm -> Execute を要求する点を明示する。

5. `AGENTS.md` は compact に保つ。
   `## Plans` セクションに 1 行だけ pointer を足す (例: `Improvement capture loop は docs/self-operation.md と templates/plan.md を参照`)。loop の詳細 mechanics は AGENTS.md には置かない。

6. lifecycle audit に最小 WARN を 2 件追加する。
   `ai_ops/audit/lifecycle.py` の `_check_plan_hygiene` に次の 2 条件を追加する: (a) active plan に `## Improvement Candidates` 見出しが無い場合 WARN、(b) active plan に `Outcomes & Retrospective` section があり中身が `TBD` のままで、かつ `Progress` の全 checkbox が `[x]` の場合 WARN。candidate 中身や enum 整合性の audit は導入しない。`tests/test_audit.py` に focused test 2 件を追加する。

7. 過剰採用を避ける。
   この pass では、後続 evidence が無い限り、`.ai-ops/harness.toml` semantics の変更、新コマンド追加、cross-plan inbox file の作成 (`docs/plans/_inbox.md` 等)、archived plans の遡及修正、外部 spec framework の導入は行わない。

## Improvement Candidates Schema

各 plan の `## Improvement Candidates` section は、`### <候補名>` を見出しとして 1 candidate ずつ並べ、次の 6 fields を持つ:

```markdown
### <候補名>

- Observation: <作業中に得た事実>
- Evidence: <ファイル / コマンド / output の参照>
- Recommended adoption target: <current-plan | durable-doc | adr | template | audit | harness | test | deferred | rejected>
- Confirmation needed: <yes | no> — <理由>
- Verification: <採用後に何で確認するか / `n/a`>
- Disposition: <open | adopted | deferred | rejected | superseded> — <短い理由・参照先>
```

enum 値の意味:

- `Recommended adoption target`: candidate を採用する場合の格納先。`current-plan` は同じ plan 内で完結する小修正、`durable-doc` は `docs/` 配下、`adr` は `docs/decisions/`、`template` は `templates/`、`audit` / `harness` / `test` は対応 module、`deferred` は今回採用しない、`rejected` は採用しない判断を残す。
- `Disposition`: candidate の現在状態。`open` は未判断、`adopted` は採用済み (adoption commit / PR を `Verification` に書く)、`deferred` は今回見送り (理由必須)、`rejected` は不採用 (理由必須)、`superseded` は別 plan / candidate に置き換え (参照先必須)。

該当する candidate が無い場合は `### (none this pass)` 1 行で良い。

## Concrete Steps

repository root から:

```sh
git status --short --branch
```

Expected: edits 前に unrelated local changes が無い。

編集候補:

- `templates/plan.md`
- `ai_ops/lifecycle/plans.py`
- `docs/ai-first-lifecycle.md`
- `docs/self-operation.md`
- possibly `AGENTS.md`
- possibly `ai_ops/audit/lifecycle.py`
- possibly `tests/test_audit.py`

その後:

```sh
python -m pytest tests/test_audit.py tests/test_cli.py
python -m ai_ops audit lifecycle
python -m ai_ops check
git diff --check
```

Nix が available で、現 session のコストとして妥当なら:

```sh
direnv exec . sh -c '
set -e
nix flake check --all-systems --no-build
nix build --no-link ".#checks.$(nix eval --impure --raw --expr builtins.currentSystem).all"
'
```

## Validation and Acceptance

Acceptance criteria は machine-checkable と human-reviewable に分けて記録する。

### Machine-checkable

- `templates/plan.md` に `## Improvement Candidates` 見出しが存在する (`grep -F '## Improvement Candidates' templates/plan.md`)。
- `templates/plan.md` 内に enum 列挙 `current-plan | durable-doc | adr | template | audit | harness | test | deferred | rejected` と `open | adopted | deferred | rejected | superseded` が両方存在する。
- `ai_ops/lifecycle/plans.py:build_promoted_plan` の出力に `## Improvement Candidates` 見出しが含まれる (`build_promoted_plan(slug="x", source_path=Path("/tmp/x"), source_text="")` を呼んで `'## Improvement Candidates' in result` を assert)。
- schema consistency test が存在し pass する: `templates/plan.md` の top-level 見出し集合 (`^## ...`) と `build_promoted_plan(...)` の top-level 見出し集合が一致する。
- `docs/ai-first-lifecycle.md` に `## Improvement Capture` 見出しが存在する。
- `docs/self-operation.md` に `## Improvement Capture Loop` 見出しが存在する。
- `tests/test_audit.py` に新 WARN 2 件分の test (見出し欠如、Outcomes TBD かつ Progress 完了) が存在し、`python -m pytest tests/test_audit.py` が pass する。
- `python -m ai_ops check` と `git diff --check` が pass する。

### Human-reviewable

- lifecycle docs の `Improvement Capture` 節が、plan / durable docs / ADR / templates / tests / audits / harness をいつ更新するかを 1 段落で説明している (深い nested guidance を作っていない)。
- `AGENTS.md` の追加は 1 行 pointer のみで、loop の mechanics を AGENTS.md 内に書いていない。
- 採用された Decision Log の enum / single-source / inbox 不要 / 遡及不要 / 最小 WARN の 5 決定がすべて実装に反映されている。

fail した場合は、どの criteria がどの理由で fail したかをこの plan の `Outcomes & Retrospective` に記録する。

## Out of Scope

この pass で意図的に触らないもの:

- `docs/plans/archive/` 配下の既存 plan への新 schema 遡及適用 (Decision Log: 遡及しない)。
- cross-plan deferred candidate inbox (`docs/plans/_inbox.md` 等) の作成 (Decision Log: 作らない、3 plan 連続重複で再検討)。
- `.ai-ops/harness.toml` semantics の拡張 (improvement notes を harness に書く、等)。
- `ai-ops` への新 subcommand 追加 (例: `ai-ops audit improvements`)。
- `Improvement Candidates` 中身の semantic audit (enum 整合性、disposition 妥当性) — 第二段で導入を再検討する。
- 他 project (`mi_share` / `umipal` / `audio-dsp-docs` / `fastener-research` / `fx-llm-research` / `note-md`) の harness drift 是正 — 各 project の realignment / migration として個別 confirmation を経て行う。
- 外部 spec framework (Spec Workflow MCP 等) の導入 — ADR 0008 の判断を維持。

## Idempotence and Recovery

この work は documentation-first であり、通常の Git diff review により reversible である。audit tightening が noisy warning を生む場合は、`git diff` を確認し、rule または template を調整してから focused tests を再実行する。`ai_ops/lifecycle/plans.py` の embedded fallback を消す変更は、`templates/plan.md` の package 同梱が壊れた場合 import error を起こすので、`pyproject.toml` の package-data 設定を変更前に確認し、変更後に `python -c "from ai_ops.lifecycle.plans import ...; ..."` で smoke 確認する。この plan 完了後の archive を除き、tracked files の削除や移動は行わない。

## Artifacts and Notes

Initial discovery commands:

```sh
git status --short --branch
find docs/plans -maxdepth 3 -type f | sort
rg -n "Progress|Surprises|Decision Log|Outcomes|PLAN_STALE|_check_plan_hygiene|lifecycle audit|self-operation|Adopt|harness" templates docs ai_ops tests -g '!**/__pycache__/**'
```

Result summary:

- working tree は `main...origin/main` の clean state から開始。
- この plan 作成前に active execution plans は無かった。
- 既存の plan hygiene checks は warning-only で、stale / malformed active plans に focused している。

Cross-project language drift audit:

```sh
git config --get ghq.user
ghq list -p
```

Managed scope used for this audit:

- `.ai-ops/harness.toml` がある project
- `ai-ops` 自身

対象:

- `/Users/tekitou/ghq/github.com/paasukusai/mi_share`
- `/Users/tekitou/ghq/github.com/tekitounix/ai-ops`
- `/Users/tekitou/ghq/github.com/tekitounix/audio-dsp-docs`
- `/Users/tekitou/ghq/github.com/tekitounix/fastener-research`
- `/Users/tekitou/ghq/github.com/tekitounix/fx-llm-research`
- `/Users/tekitou/ghq/github.com/tekitounix/umipal`

暫定判定:

- `mi_share`: aligned。README.md は英語、README.ja.md sibling、README 以外の project-owned docs は日本語。
- `ai-ops`: aligned after this plan's current edits。archived plan には旧判断が残るが historical record なので書き換えない。
- `audio-dsp-docs`: mostly aligned。README.md は英語 entrypoint、human-authored docs は日本語。ただし `AGENTS.md` 冒頭に awkward mixed-language sentence があり、別途 polish 候補。
- `fastener-research`: drift candidate。README.md を日本語 working note とし、public 化時に `README.en.md` 追加または主 README 英訳としている。
- `fx-llm-research`: drift candidate。T2 private 恒久として README.md も日本語、英語 sibling 不要としている。
- `umipal`: aligned。README.md / LICENSE / source identifier / commit subject / branch tag / CI / hook は英語、AGENTS/docs/plans は日本語。

Full `ghq list -p` exact scan:

- 12 repo を対象に旧 language policy exact patterns を検索。
- active source/docs の hit は無し。
- この plan 自身の evidence line だけが search terms を含むため hit した。これは drift ではない。

`python -m ai_ops audit projects --json` summary:

- command exit: 1 (P0/P1 が残っているため expected)
- P0: `umipal` (`harness_drift=true`, dirty/security signals)
- P1: `mi_share`, `audio-dsp-docs`, `fastener-research`, `fx-llm-research`, `note-md`
- P2/no immediate action: `ai-ops`, `knx3`, `ai-ops-*validation*`
- この audit は language-specific ではない。各 project の realignment / migration は `docs/projects-audit.md` に従い、project ごとに個別 confirmation が必要。

## Interfaces and Dependencies

この plan は以下に影響しうる:

- Plan template schema: `templates/plan.md` and `ai_ops/lifecycle/plans.py`
- Lifecycle documentation contract: `docs/ai-first-lifecycle.md`
- ai-ops dogfood procedure: `docs/self-operation.md`
- Lifecycle audit warning behavior: `ai_ops/audit/lifecycle.py`

runtime dependencies、external services、background automation、user-environment changes は追加しない。
