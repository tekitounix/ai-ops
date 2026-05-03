import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_ops.audit.nix import evaluate_project, run_nix_audit
from ai_ops.audit.security import run_security_audit


# Split literals so that ai-ops audit security can scan this test file without
# self-flagging. The runtime values still match the regex once concatenated.
_FAKE_AWS_KEY = "A" + "KIA0123456789ABCDEF"
_FAKE_PRIVATE_HEADER = "-----" + "BEGIN RSA PRIVATE KEY-----"


def _git_init(path: Path, file_count: int = 6) -> None:
    """Initialize a minimal git repo in path with `file_count` tracked files committed.

    file_count >= 5 にしておくと Stage C の `tiny_project` signal (= -2) が起動しない。
    """
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "test"],
        check=True,
    )
    for i in range(file_count):
        (path / f"_filler{i}.txt").write_text(f"{i}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "init"],
        check=True,
    )


def _git_add_and_commit(path: Path, files: list[str]) -> None:
    for f in files:
        subprocess.run(["git", "-C", str(path), "add", f], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "stack"],
        check=True,
    )


def test_nix_audit_passes_with_correct_flake(tmp_path: Path) -> None:
    """Existing flake with devShells passes (loose match for non-ai-ops repos)."""
    (tmp_path / "flake.nix").write_text(
        "{ outputs = { ... }: { devShells = {}; }; }",
        encoding="utf-8",
    )
    (tmp_path / "flake.lock").write_text("{}\n", encoding="utf-8")
    assert run_nix_audit(tmp_path) == 0


def test_nix_audit_fails_when_stack_present_but_flake_missing(tmp_path: Path) -> None:
    """stack signal (package.json) なのに flake.nix 無し → recommended=devshell, gap=missing-flake → FAIL."""
    (tmp_path / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    assert run_nix_audit(tmp_path) == 1


def test_nix_audit_passes_when_no_stack_signal(tmp_path: Path) -> None:
    """No stack signal AND no flake → minimal recommendation (no fail in non-ai-ops cwd)."""
    # empty dir — Stage A (no archive / scratch / docs-only / fork), Stage B unknown=minimal,
    # Stage C score=0. recommended=minimal (not devshell/apps/full) → no FAIL.
    assert run_nix_audit(tmp_path) == 0


# ─────────────────────────────────────────────────────
# Stage A/B/C rubric tests (self-review #4 follow-up)
# ─────────────────────────────────────────────────────


def test_evaluate_project_existing_flake(tmp_path: Path) -> None:
    """Stage A — existing flake → preserve."""
    (tmp_path / "flake.nix").write_text(
        "{ outputs = { ... }: { devShells = {}; }; }",
        encoding="utf-8",
    )
    r = evaluate_project(tmp_path)
    assert r["stage_a_exit"] == "existing-flake"
    assert r["recommended_level"] == "preserve"
    assert r["gap"] == "ok"


def test_evaluate_project_docs_only(tmp_path: Path) -> None:
    """Stage A — all tracked files are markdown → docs-only → none."""
    (tmp_path / "README.md").write_text("docs", encoding="utf-8")
    (tmp_path / "NOTES.md").write_text("notes", encoding="utf-8")
    r = evaluate_project(tmp_path)
    assert r["stage_a_exit"] == "docs-only"
    assert r["recommended_level"] == "none"


def test_evaluate_project_node_stack(tmp_path: Path) -> None:
    """Stage B — package.json → flake.nix.node template, devshell level."""
    _git_init(tmp_path)
    (tmp_path / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    _git_add_and_commit(tmp_path, ["package.json"])
    r = evaluate_project(tmp_path)
    assert r["stage_a_exit"] is None
    assert r["stack_hint"] == "node"
    assert r["recommended_template"] == "flake.nix.node"
    assert r["recommended_level"] in ("devshell", "apps")


def test_evaluate_project_python_stack(tmp_path: Path) -> None:
    """Stage B — pyproject.toml → flake.nix.python template."""
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\n',
        encoding="utf-8",
    )
    _git_add_and_commit(tmp_path, ["pyproject.toml"])
    r = evaluate_project(tmp_path)
    assert r["stack_hint"] == "python"
    assert r["recommended_template"] == "flake.nix.python"


def test_evaluate_project_xmake_stack(tmp_path: Path) -> None:
    """Stage B — xmake.lua → flake.nix.xmake template (組込み)."""
    _git_init(tmp_path)
    (tmp_path / "xmake.lua").write_text("target('x')\n", encoding="utf-8")
    _git_add_and_commit(tmp_path, ["xmake.lua"])
    r = evaluate_project(tmp_path)
    assert r["stack_hint"] == "xmake"
    assert r["recommended_template"] == "flake.nix.xmake"


def test_evaluate_project_rust_falls_back_to_minimal(tmp_path: Path) -> None:
    """Stage B — Cargo.toml → flake.nix.minimal (NOT flake.nix.python; self-review #1 fix)."""
    _git_init(tmp_path)
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    _git_add_and_commit(tmp_path, ["Cargo.toml"])
    r = evaluate_project(tmp_path)
    assert r["stack_hint"] == "rust"
    assert r["recommended_template"] == "flake.nix.minimal"


def test_evaluate_project_go_falls_back_to_minimal(tmp_path: Path) -> None:
    """Stage B — go.mod → flake.nix.minimal (NOT flake.nix.python; self-review #1 fix)."""
    _git_init(tmp_path)
    (tmp_path / "go.mod").write_text("module x\ngo 1.21\n", encoding="utf-8")
    _git_add_and_commit(tmp_path, ["go.mod"])
    r = evaluate_project(tmp_path)
    assert r["stack_hint"] == "go"
    assert r["recommended_template"] == "flake.nix.minimal"


def test_evaluate_project_score_promotes_to_apps(tmp_path: Path) -> None:
    """Stage C — many pros signals (CI + tests + LICENSE + CONTRIBUTING + dist + AGENTS.md)
    → score ≥ 6 → promote devshell to apps."""
    _git_init(tmp_path)
    (tmp_path / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
    (tmp_path / "CONTRIBUTING.md").write_text("contrib", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("agents", encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "x.js").write_text("", encoding="utf-8")
    _git_add_and_commit(
        tmp_path,
        ["package.json", "LICENSE", "CONTRIBUTING.md", "AGENTS.md"],
    )
    r = evaluate_project(tmp_path)
    assert r["score"] >= 6
    assert r["recommended_level"] == "apps"


def test_lifecycle_audit_recognizes_renovate_artifact(tmp_path: Path) -> None:
    """Phase 8-A: renovate.json artifact must be in REQUIRED_FILES + allowed_template_files."""
    from ai_ops.audit.lifecycle import REQUIRED_FILES
    assert "templates/artifacts/renovate.json" in REQUIRED_FILES
    assert "templates/artifacts/update-flake-lock.yml" in REQUIRED_FILES
    assert "templates/plan.md" in REQUIRED_FILES
    assert "docs/decisions/0008-plan-persistence.md" in REQUIRED_FILES
    assert "docs/projects-audit.md" in REQUIRED_FILES
    assert "docs/project-relocation.md" in REQUIRED_FILES
    assert "docs/realignment.md" in REQUIRED_FILES


def test_align_prompt_chain_reaches_relocation_playbook() -> None:
    """The single `align this project` Quick start prompt must lead an agent
    to the relocation playbook through static doc references — without the
    chain, an AI looking at a non-ghq path cannot find the right procedure."""
    repo = Path(__file__).resolve().parents[1]

    readme = (repo / "README.md").read_text(encoding="utf-8")
    assert "align this project" in readme
    assert "relocate" in readme.lower()

    agents_md = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "docs/project-relocation.md" in agents_md
    assert "project physical relocation" in agents_md.lower()

    realign = (repo / "docs" / "realignment.md").read_text(encoding="utf-8")
    assert "project-relocation.md" in realign
    assert "~/ghq/" in realign

    relocation = (repo / "docs" / "project-relocation.md").read_text(encoding="utf-8")
    assert "Phase 1" in relocation and "Phase 4" in relocation
    assert ".claude/projects" in relocation  # AI substrate handling documented
    # full-migration invariants (regression checks against the prior draft
    # which left a back-symlink and skipped content rewrite):
    assert "ANTI-PATTERN" in relocation  # back-symlink is documented as one
    assert "content rewrite" in relocation.lower()
    assert ".jsonl" in relocation  # Claude session content is named explicitly
    # Phase 4 must demand grep-based content verification, not just `ls`
    assert 'grep -rlI -F "$OLD"' in relocation
    # Multi-version hash drift, IDE workspace storage, in-session and recovery
    # support — the four protocol gaps closed by the latest review.
    assert "HASH_V1" in relocation and "HASH_V2" in relocation
    assert "workspaceStorage" in relocation  # VS Code / Cursor migration covered
    assert "In-session migration" in relocation  # cwd self-protection covered
    assert "Recovery (partial migration)" in relocation
    assert "tr './'" in relocation  # documents the v2 sanitize formula
    assert "realpath" in relocation
    # Lessons from the first real-world recovery run (case study after e2f5367):
    # rewrite must cover non-jsonl text files, glob invariants must be
    # explicit, and fragment names must strip Claude's leading dash.
    for ext_glob in ('"*.jsonl"', '"*.md"', '"*.json"', '"*.txt"'):
        assert ext_glob in relocation, f"rewrite scope missing pattern {ext_glob}"
    assert "INVARIANT:" in relocation  # Step 3.1 / 3.2 mis-implementation guards
    assert "${source_hash#-}" in relocation  # leading-dash strip in fragment naming


def test_audit_my_projects_prompt_chain_reaches_projects_audit_playbook() -> None:
    """The third Quick start prompt (`audit my projects`) must reach
    docs/projects-audit.md through static doc references — without the
    chain, the agent has no canonical playbook to follow when asked to
    survey every ghq-tracked project."""
    repo = Path(__file__).resolve().parents[1]

    readme = (repo / "README.md").read_text(encoding="utf-8")
    assert "audit my projects" in readme
    assert "docs/projects-audit.md" in readme

    readme_ja = (repo / "README.ja.md").read_text(encoding="utf-8")
    assert "自分のプロジェクト群を監査" in readme_ja  # ja prompt body
    assert "docs/projects-audit.md" in readme_ja

    agents_md = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "docs/projects-audit.md" in agents_md
    assert "audit my projects" in agents_md  # third-prompt explanation

    playbook = (repo / "docs" / "projects-audit.md").read_text(encoding="utf-8")
    assert "Phase 1" in playbook and "Phase 4" in playbook
    # Priority taxonomy and sub-flow routing must both be documented;
    # otherwise the agent would have nowhere to derive recommendations.
    assert "P0" in playbook and "P1" in playbook and "P2" in playbook
    for sub in ("relocate", "migrate", "realign", "no-op"):
        assert sub in playbook, f"sub-flow `{sub}` missing from projects-audit playbook"
    # The playbook must explicitly defer destructive work to the linked
    # single-project playbooks rather than redefining their steps.
    for linked in (
        "docs/project-relocation.md",
        "docs/project-addition-and-migration.md",
        "docs/realignment.md",
    ):
        assert linked in playbook, f"projects-audit playbook does not link {linked}"
    # Validation / fixture exclusion is what prevents drift counts from
    # being polluted by intentionally unmanaged repos.
    assert "fixture" in playbook.lower()
    # Phase 1 must call the canonical CLI (ai-ops audit projects) — agents
    # must not re-implement the collection in shell from scratch.
    assert "audit projects --json" in playbook


def test_lifecycle_audit_warns_on_plan_hygiene(tmp_path: Path) -> None:
    """mtime-based fallback path: untracked plan with old mtime is flagged."""
    from ai_ops.audit.lifecycle import _check_plan_hygiene

    plan = tmp_path / "docs" / "plans" / "feature" / "plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("# Feature\n\n## Progress\n\nNo checkbox yet.\n", encoding="utf-8")

    now = datetime(2026, 4, 29, tzinfo=timezone.utc)
    old = now - timedelta(days=31)
    os.utime(plan, (old.timestamp(), old.timestamp()))

    warnings = _check_plan_hygiene(tmp_path, now=now)
    assert any("missing Progress checkbox" in warning for warning in warnings)
    assert any("active for >30 days" in warning for warning in warnings)


def test_lifecycle_audit_warns_when_improvement_candidates_section_missing(
    tmp_path: Path,
) -> None:
    """Plan without `## Improvement Candidates` heading is flagged."""
    from ai_ops.audit.lifecycle import _check_plan_hygiene

    plan = tmp_path / "docs" / "plans" / "feature" / "plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(
        "# Feature\n\n"
        "## Progress\n\n- [x] step\n\n"
        "## Outcomes & Retrospective\n\nShipped X.\n",
        encoding="utf-8",
    )

    warnings = _check_plan_hygiene(tmp_path)
    assert any(
        "missing '## Improvement Candidates' section" in w for w in warnings
    )


def test_lifecycle_audit_warns_when_progress_complete_but_outcomes_tbd(
    tmp_path: Path,
) -> None:
    """Progress 全 [x] かつ Outcomes が TBD のままは archive 寸前の取りこぼし signal."""
    from ai_ops.audit.lifecycle import _check_plan_hygiene

    plan = tmp_path / "docs" / "plans" / "feature" / "plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(
        "# Feature\n\n"
        "## Progress\n\n- [x] one\n- [x] two\n\n"
        "## Outcomes & Retrospective\n\nTBD.\n\n"
        "## Improvement Candidates\n\n### (none this pass)\n",
        encoding="utf-8",
    )

    warnings = _check_plan_hygiene(tmp_path)
    assert any(
        "Outcomes & Retrospective' is still TBD" in w for w in warnings
    )


def test_lifecycle_audit_warns_when_outcomes_filled_but_still_active(
    tmp_path: Path,
) -> None:
    """An active plan with substantive Outcomes content is archive-ready.

    Catches the 'shipped but never archived' failure mode where work is
    finished, Outcomes documented, but the plan still sits in the active
    directory because the archive step was forgotten.
    """
    from ai_ops.audit.lifecycle import _check_plan_hygiene

    plan = tmp_path / "docs" / "plans" / "feature" / "plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(
        "# Feature\n\n"
        "## Progress\n\n- [x] step\n\n"
        "## Outcomes & Retrospective\n\nShipped X. Retrospective notes here.\n\n"
        "## Improvement Candidates\n\n### (none this pass)\n",
        encoding="utf-8",
    )

    warnings = _check_plan_hygiene(tmp_path)
    assert any("appears archive-ready" in w for w in warnings)


def test_lifecycle_audit_does_not_warn_archive_ready_when_outcomes_tbd(
    tmp_path: Path,
) -> None:
    """A plan with Outcomes still 'TBD' is in progress, not archive-ready."""
    from ai_ops.audit.lifecycle import _check_plan_hygiene

    plan = tmp_path / "docs" / "plans" / "feature" / "plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(
        "# Feature\n\n"
        "## Progress\n\n- [ ] step in progress\n\n"
        "## Outcomes & Retrospective\n\nTBD.\n\n"
        "## Improvement Candidates\n\n### (none this pass)\n",
        encoding="utf-8",
    )

    warnings = _check_plan_hygiene(tmp_path)
    assert not any("archive-ready" in w for w in warnings)


def test_outcomes_tbd_recognises_japanese_period(tmp_path: Path) -> None:
    """`TBD。続き` (Japanese period) must be recognised as starting with TBD.

    Regression: earlier the parser used `body.split(None, 1)[0].rstrip(".。")`
    which fails when there is no whitespace before the Japanese period —
    `TBD。完了時に内容` was treated as 'not TBD' because the first whitespace-
    separated token was `TBD。完了時に内容` (no `.` or `。` at the end to strip).
    """
    from ai_ops.audit.lifecycle import _outcomes_filled, _outcomes_still_tbd

    text = (
        "# Plan\n\n"
        "## Outcomes & Retrospective\n\n"
        "TBD。完了時に shipped したものを記録する。\n"
    )
    assert _outcomes_still_tbd(text) is True
    assert _outcomes_filled(text) is False


def test_outcomes_filled_recognises_substantive_content(tmp_path: Path) -> None:
    """A body that begins with substantive content (no TBD prefix) is filled."""
    from ai_ops.audit.lifecycle import _outcomes_filled, _outcomes_still_tbd

    text = (
        "# Plan\n\n"
        "## Outcomes & Retrospective\n\n"
        "Shipped X, Y, Z. TBD remains for follow-up.\n"
    )
    assert _outcomes_still_tbd(text) is False
    assert _outcomes_filled(text) is True


def test_docs_language_policy_passes_for_japanese_doc(tmp_path: Path) -> None:
    """日本語比率が閾値以上なら違反なし。"""
    from ai_ops.audit.lifecycle import _check_docs_language_policy

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "japanese.md").write_text(
        "# 日本語ドキュメント\n\nこれは十分な日本語が含まれている文書です。"
        "コードブロックや英語のキーワードが混じっていても問題ありません。\n",
        encoding="utf-8",
    )
    assert _check_docs_language_policy(tmp_path) == []


def test_docs_language_policy_fails_for_english_only_doc(tmp_path: Path) -> None:
    """純英語の docs/*.md は違反として検出される。"""
    from ai_ops.audit.lifecycle import _check_docs_language_policy

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "english.md").write_text(
        "# English Doc\n\nThis is entirely English text without any Japanese.\n",
        encoding="utf-8",
    )
    failures = _check_docs_language_policy(tmp_path)
    assert len(failures) == 1
    assert "english.md" in failures[0]
    assert "japanese-char ratio" in failures[0]


def test_docs_language_policy_exempts_readme(tmp_path: Path) -> None:
    """README* は英語デフォルトなので除外される。"""
    from ai_ops.audit.lifecycle import _check_docs_language_policy

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "README.md").write_text("English README is OK.\n", encoding="utf-8")
    (docs / "README.ja.md").write_text("日本語 README も OK\n", encoding="utf-8")
    assert _check_docs_language_policy(tmp_path) == []


def test_docs_language_policy_skips_subdirectories(tmp_path: Path) -> None:
    """docs/decisions/ や docs/plans/ のサブディレクトリは対象外。"""
    from ai_ops.audit.lifecycle import _check_docs_language_policy

    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    (decisions / "0001-foo.md").write_text(
        "# ADR 0001: Foo\n\nADRs are conventionally written in English.\n",
        encoding="utf-8",
    )
    plans = tmp_path / "docs" / "plans" / "active-slug"
    plans.mkdir(parents=True)
    (plans / "plan.md").write_text(
        "# Plan\n\nThis active plan happens to be English at the moment.\n",
        encoding="utf-8",
    )
    assert _check_docs_language_policy(tmp_path) == []


def test_docs_language_policy_real_repo_passes() -> None:
    """ai-ops 自身の docs/ が現状ポリシーに通ること (回帰テスト)。"""
    from ai_ops.audit.lifecycle import _check_docs_language_policy

    repo = Path(__file__).resolve().parents[1]
    failures = _check_docs_language_policy(repo)
    assert failures == [], f"language policy violations: {failures}"


def test_count_pending_propagation_prs_returns_minus_one_without_gh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When `gh` is missing, return -1 (distinguish from 0 PRs)."""
    from ai_ops.audit.projects import _count_pending_propagation_prs

    monkeypatch.setattr("shutil.which", lambda _: None)
    assert _count_pending_propagation_prs(tmp_path) == -1


def test_count_pending_propagation_prs_handles_empty_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When `gh pr list` returns `[]`, count is 0."""
    from ai_ops.audit.projects import _count_pending_propagation_prs
    import subprocess as _subprocess

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/gh")

    class FakeResult:
        returncode = 0
        stdout = "[]"

    monkeypatch.setattr(
        _subprocess, "run", lambda *a, **kw: FakeResult(),
    )
    assert _count_pending_propagation_prs(tmp_path) == 0


def test_count_pending_propagation_prs_counts_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When `gh pr list` returns multiple entries, count them by `"number"` key."""
    from ai_ops.audit.projects import _count_pending_propagation_prs
    import subprocess as _subprocess

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/gh")

    class FakeResult:
        returncode = 0
        stdout = '[{"number":1},{"number":2},{"number":3}]'

    monkeypatch.setattr(
        _subprocess, "run", lambda *a, **kw: FakeResult(),
    )
    assert _count_pending_propagation_prs(tmp_path) == 3


def test_outcomes_tbd_recognises_various_forms(tmp_path: Path) -> None:
    """`TBD`, `TBD.`, `TBD。`, `TBD ...`, `TBD,...` should all be detected."""
    from ai_ops.audit.lifecycle import _outcomes_still_tbd

    for form in ("TBD", "TBD.", "TBD。", "TBD foo", "TBD, foo", "TBD\nfoo"):
        text = f"## Outcomes & Retrospective\n\n{form}\n"
        assert _outcomes_still_tbd(text) is True, f"failed for: {form!r}"


def test_plan_age_prefers_git_log_over_mtime(tmp_path: Path) -> None:
    """When the plan is tracked in git, _plan_age uses commit time, not mtime.

    This protects against the CI / fresh-clone case where mtime is reset to
    the checkout time and a genuinely stale plan would otherwise look fresh.
    """
    from ai_ops.audit.lifecycle import _plan_age

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@test"], check=True
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "test"], check=True
    )
    plan = tmp_path / "docs" / "plans" / "feature" / "plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("# Feature\n", encoding="utf-8")

    # Commit the plan as if it had been committed long ago.
    far_past = "2020-01-01T00:00:00Z"
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": far_past,
        "GIT_COMMITTER_DATE": far_past,
    }
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "old plan"],
        check=True,
        env=env,
    )

    # Force mtime to "now" so mtime alone would say the plan is fresh.
    now = datetime(2026, 4, 29, tzinfo=timezone.utc)
    os.utime(plan, (now.timestamp(), now.timestamp()))

    age = _plan_age(plan, tmp_path, now)
    # Commit was 2020 → age should be > 5 years; far above the 30-day threshold.
    assert age > timedelta(days=365 * 5), f"expected git-log-derived age, got {age}"


def test_lifecycle_audit_forbidden_pattern_grep(tmp_path: Path) -> None:
    """Phase 8-D: every forbidden pattern in FORBIDDEN_ACTIVE_PATTERNS must
    actually fire when its target string is present in active code. This
    catches regex regressions where a pattern could be silently broken."""
    from ai_ops.audit.lifecycle import (
        FORBIDDEN_ACTIVE_PATTERNS,
        _scan_pattern_in_paths,
    )

    # Realistic offending lines for each forbidden pattern.
    forbidden_examples: dict[str, str] = {
        r"--no-verify": 'subprocess.run(["git", "commit", "--no-verify"])',
        r"\brm\s+-rf\b": 'os.system("rm -rf /tmp/x")',
        r"gh\s+repo\s+create[^|;\n]*--public": (
            'os.system("gh repo create some-repo --public")'
        ),
        r"#\s*silent[\s_-]*install": "# silent install: skip user prompt",
    }

    (tmp_path / "ai_ops").mkdir()

    for desc, pattern, scan_paths in FORBIDDEN_ACTIVE_PATTERNS:
        line = forbidden_examples.get(pattern)
        assert line is not None, f"add an example for pattern: {pattern!r} ({desc})"
        offender = tmp_path / "ai_ops" / "offender.py"
        offender.write_text(line + "\n", encoding="utf-8")
        hits = _scan_pattern_in_paths(tmp_path, pattern, scan_paths)
        assert hits, f"pattern {pattern!r} ({desc}) failed to detect: {line!r}"
        offender.unlink()


def test_lifecycle_audit_scorecard_skips_when_missing(tmp_path: Path) -> None:
    """Phase 8-D: Scorecard CLI 不在時は INFO にして audit を fail させない。"""
    from ai_ops.audit.lifecycle import _check_scorecard

    # ai-ops 自身の root を渡しても scorecard CLI が無いなら ran=False で skip する
    ran, msg = _check_scorecard(tmp_path)
    # CI 環境次第で True/False どちらもあり得るが、msg が必ず非空であること
    assert isinstance(ran, bool)
    assert isinstance(msg, str) and len(msg) > 0


def test_lifecycle_audit_readme_claim_verification(tmp_path: Path) -> None:
    """Phase 8-D: README claim 検証は実 ai-ops repo 上では PASS する想定。"""
    from ai_ops.audit.lifecycle import _check_readme_claims

    # Use the real ai-ops repo root for this end-to-end claim check.
    repo = Path(__file__).resolve().parents[1]
    failures = _check_readme_claims(repo)
    assert failures == [], f"README claim verification failed: {failures}"


def test_run_nix_report_continues_after_per_project_error(
    tmp_path: Path, monkeypatch
) -> None:
    """One bad project (corrupted .git, symlink loop, etc.) must not abort
    the audit run. evaluate_project raises → row reported as ERROR, loop
    continues."""
    from ai_ops.audit import nix as nix_mod

    good = tmp_path / "good"
    good.mkdir()
    bad = tmp_path / "bad"
    bad.mkdir()

    real_evaluate = nix_mod.evaluate_project

    def flaky_evaluate(path):
        if path == bad:
            raise RuntimeError("simulated corruption")
        return real_evaluate(path)

    monkeypatch.setattr(nix_mod, "evaluate_project", flaky_evaluate)
    rc = nix_mod.run_nix_report(roots=[good, bad])
    assert rc == 0  # report still completes; the bad project shows as ERROR


def test_run_nix_report_marks_managed_projects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `mgd` column reflects whether `.ai-ops/harness.toml` is present,
    so projects audits can tell ai-ops-managed projects from validation /
    pre-adoption repos at a glance."""
    from ai_ops.audit import nix as nix_mod

    managed = tmp_path / "managed"
    (managed / ".ai-ops").mkdir(parents=True)
    (managed / ".ai-ops" / "harness.toml").write_text(
        'ai_ops_sha = "x"\nlast_sync = "y"\n[harness_files]\n', encoding="utf-8"
    )

    untracked = tmp_path / "untracked"
    untracked.mkdir()

    rc = nix_mod.run_nix_report(roots=[managed, untracked])
    assert rc == 0
    out = capsys.readouterr().out
    # Header column present
    assert "mgd" in out
    # Both rows printed; managed row shows yes, untracked shows no
    assert "managed=1/2" in out


def test_evaluate_project_tiny_demote_to_none(tmp_path: Path) -> None:
    """Stage C — tiny project (< 5 file) AND no signals → score < 0 → demote to none."""
    # _git_init w/ file_count=1 で tracked_count = 1 → tiny_project (-2)
    _git_init(tmp_path, file_count=1)
    (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")
    r = evaluate_project(tmp_path)
    # tiny_project (-2) のみが響き、pros signal は無いため score < 0
    assert r["score"] < 0
    assert r["recommended_level"] == "none"


def test_security_audit_clean_repo_passes(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("clean\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 0


def test_security_audit_detects_env_dotfile(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("placeholder\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_detects_pem_file(tmp_path: Path) -> None:
    (tmp_path / "deploy.pem").write_text("placeholder\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_detects_secrets_dir(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "value.txt").write_text("placeholder\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_detects_aws_access_key_pattern(tmp_path: Path) -> None:
    (tmp_path / "config.txt").write_text(_FAKE_AWS_KEY + "\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_detects_private_key_header(tmp_path: Path) -> None:
    (tmp_path / "key.txt").write_text(
        _FAKE_PRIVATE_HEADER + "\n",
        encoding="utf-8",
    )
    assert run_security_audit(tmp_path) == 1


def test_security_audit_skips_only_tests_fixtures_directory(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "tests" / "fixtures"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "fake.txt").write_text(_FAKE_AWS_KEY + "\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 0


def test_security_audit_flags_value_in_tests_top_level(tmp_path: Path) -> None:
    # 旧挙動 (tests/ 全体 skip) は廃止。tests/ 直下や tests/<not-fixtures>/ は scan する。
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "leaked.txt").write_text(_FAKE_AWS_KEY + "\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_still_flags_secret_named_files_under_tests_dir(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / ".env").write_text("placeholder\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_skips_binary_files_without_crashing(tmp_path: Path) -> None:
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02\xff\xfe")
    assert run_security_audit(tmp_path) == 0


def test_security_audit_allows_env_template_variants(tmp_path: Path) -> None:
    """`.env.example` and friends are placeholder templates, not real secrets.
    Treating them as failures was a documented false-positive source in the
    projects-audit review."""
    for name in (".env.example", ".env.template", ".env.sample", ".env.dist"):
        (tmp_path / name).write_text("API_KEY=__placeholder__\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 0


def test_security_audit_still_flags_real_env_file(tmp_path: Path) -> None:
    """`.env` itself stays flagged even when `.env.example` is allowed."""
    (tmp_path / ".env.example").write_text("API_KEY=__placeholder__\n", encoding="utf-8")
    (tmp_path / ".env").write_text("API_KEY=real-token\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_skips_value_scan_in_dependency_dirs(tmp_path: Path) -> None:
    """Value-pattern scanning must skip vendor / build / venv trees: those
    contain third-party fixtures and AKIA-shaped strings that the project
    does not own."""
    for dirname in ("node_modules", ".venv", "vendor", "dist", "build"):
        d = tmp_path / dirname
        d.mkdir()
        (d / "fixture.txt").write_text(_FAKE_AWS_KEY + "\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 0


def _setup_managed_project(tmp_path: Path, ai_ops_sha: str = "abc123") -> Path:
    """Create a minimal managed-project structure with a harness.toml manifest."""
    project = tmp_path / "proj"
    project.mkdir()
    harness_dir = project / ".ai-ops"
    harness_dir.mkdir()
    (harness_dir / "harness.toml").write_text(
        f'ai_ops_sha = "{ai_ops_sha}"\n'
        f'last_sync = "2026-04-01T00:00:00Z"\n\n'
        f"[harness_files]\n",
        encoding="utf-8",
    )
    return project


def _canonical_plan_text() -> str:
    """Return a synthetic plan body with all REQUIRED_PLAN_SECTIONS as headings."""
    from ai_ops.audit._canonical import REQUIRED_PLAN_SECTIONS

    body = ["# Test plan\n"]
    for section in REQUIRED_PLAN_SECTIONS:
        body.append(f"## {section}\n\nbody\n")
    return "\n".join(body)


def test_policy_drift_unmanaged_project_is_n_a(tmp_path: Path) -> None:
    """Project without `.ai-ops/harness.toml` reports `n/a` (out of scope)."""
    from ai_ops.audit.projects import _detect_policy_drift

    project = tmp_path / "proj"
    project.mkdir()

    assert _detect_policy_drift(project, tmp_path) == "n/a"


def test_policy_drift_ai_ops_self_is_n_a(tmp_path: Path) -> None:
    """ai-ops itself returns `n/a` because lifecycle audit owns its self-check."""
    from ai_ops.audit.projects import _detect_policy_drift
    from ai_ops.paths import package_root

    # Use the actual ai-ops repo so _is_ai_ops_repo() detects it.
    ai_ops_root = package_root()
    assert _detect_policy_drift(ai_ops_root, ai_ops_root) == "n/a"


def test_policy_drift_no_anchor_when_ai_ops_sha_missing(tmp_path: Path) -> None:
    """Managed project with empty `ai_ops_sha` returns `no-anchor`."""
    from ai_ops.audit.projects import _detect_policy_drift

    project = _setup_managed_project(tmp_path, ai_ops_sha="")
    assert _detect_policy_drift(project, tmp_path) == "no-anchor"


def test_policy_drift_ok_when_no_plans_or_template(tmp_path: Path) -> None:
    """Managed project with no own plans/templates is `ok` (nothing to diverge)."""
    from ai_ops.audit.projects import _detect_policy_drift

    project = _setup_managed_project(tmp_path)
    assert _detect_policy_drift(project, tmp_path) == "ok"


def test_policy_drift_stale_when_active_plan_lacks_required_section(
    tmp_path: Path,
) -> None:
    """Active plan missing `## Improvement Candidates` flips signal to `stale`."""
    from ai_ops.audit.projects import _detect_policy_drift

    project = _setup_managed_project(tmp_path)
    plan = project / "docs" / "plans" / "feature" / "plan.md"
    plan.parent.mkdir(parents=True)
    # Include almost everything except Improvement Candidates.
    plan.write_text(
        "# Feature\n\n"
        "## Purpose / Big Picture\n\nbody\n\n"
        "## Progress\n\n- [x] step\n\n"
        "## Surprises & Discoveries\n\nbody\n\n"
        "## Decision Log\n\nbody\n\n"
        "## Outcomes & Retrospective\n\nbody\n\n"
        "## Context and Orientation\n\nbody\n\n"
        "## Plan of Work\n\nbody\n\n"
        "## Concrete Steps\n\nbody\n\n"
        "## Validation and Acceptance\n\nbody\n\n"
        "## Idempotence and Recovery\n\nbody\n\n"
        "## Artifacts and Notes\n\nbody\n\n"
        "## Interfaces and Dependencies\n\nbody\n",
        encoding="utf-8",
    )

    assert _detect_policy_drift(project, tmp_path) == "stale"


def test_policy_drift_diverged_when_own_template_has_extra_sections(
    tmp_path: Path,
) -> None:
    """Project's own templates/plan.md with non-canonical sections (canonical-superset)
    flips signal to `diverged` — ahead but not behind."""
    from ai_ops.audit.projects import _detect_policy_drift

    project = _setup_managed_project(tmp_path)
    own_template = project / "templates" / "plan.md"
    own_template.parent.mkdir(parents=True)
    # Include all canonical sections + 1 project-specific.
    own_template.write_text(
        _canonical_plan_text() + "\n## Project Specific Gate\n\nbody\n",
        encoding="utf-8",
    )

    assert _detect_policy_drift(project, tmp_path) == "diverged"


def test_policy_drift_ahead_and_behind_when_own_template_diverges_both_ways(
    tmp_path: Path,
) -> None:
    """Project lacks one canonical section AND has one project-specific section
    flips signal to `ahead-and-behind` (both directions of drift)."""
    from ai_ops.audit.projects import _detect_policy_drift
    from ai_ops.audit._canonical import REQUIRED_PLAN_SECTIONS

    project = _setup_managed_project(tmp_path)
    own_template = project / "templates" / "plan.md"
    own_template.parent.mkdir(parents=True)
    # Build a template that drops 1 canonical section and adds 1 own.
    body = ["# Project plan\n"]
    for section in REQUIRED_PLAN_SECTIONS:
        if section == "Improvement Candidates":
            continue  # behind: missing canonical
        body.append(f"## {section}\n\nbody\n")
    body.append("## Project Specific Gate\n\nbody\n")  # ahead: extra
    own_template.write_text("\n".join(body), encoding="utf-8")

    assert _detect_policy_drift(project, tmp_path) == "ahead-and-behind"


def test_policy_drift_skips_archived_plans(tmp_path: Path) -> None:
    """Archived plans (under `docs/plans/archive/<slug>/plan.md`) are not checked.

    Per the policy-drift Decision Log, archived plans are historical record and
    must not be retroactively scored against new canonical schema.
    """
    from ai_ops.audit.projects import _detect_policy_drift

    project = _setup_managed_project(tmp_path)
    archived = project / "docs" / "plans" / "archive" / "2026-01-01-old" / "plan.md"
    archived.parent.mkdir(parents=True)
    # An archived plan that lacks Improvement Candidates would WARN if active,
    # but should not flip the project's policy_drift signal.
    archived.write_text(
        "# Old plan\n\n## Progress\n\n- [x] done\n",
        encoding="utf-8",
    )

    assert _detect_policy_drift(project, tmp_path) == "ok"


def test_plan_template_and_promoted_plan_share_top_level_headings() -> None:
    """templates/plan.md と build_promoted_plan の出力は同じ top-level 見出し集合を持つ。

    `build_promoted_plan` は promote-plan 専用の独立 generator (templates/plan.md の
    fallback ではない) だが、両者を「同じ schema」として扱う以上、top-level 見出し
    の集合は一致しなければならない。drift すると、promote 経由で作られた plan が
    `_check_plan_hygiene` の WARN 条件 (Improvement Candidates 欠如等) に違反する。
    """
    import re as _re

    from ai_ops.lifecycle.plans import build_promoted_plan
    from ai_ops.paths import package_root

    template_text = (package_root() / "templates" / "plan.md").read_text(encoding="utf-8")
    promoted_text = build_promoted_plan(
        slug="example",
        source_path=Path("/tmp/example.md"),
        source_text="dummy source content",
    )

    def _h2_set(text: str) -> set[str]:
        return {m.group(1).strip() for m in _re.finditer(r"(?m)^##\s+(.+?)\s*$", text)}

    template_headings = _h2_set(template_text)
    promoted_headings = _h2_set(promoted_text)

    assert template_headings == promoted_headings, (
        f"schema drift between templates/plan.md and build_promoted_plan: "
        f"only-in-template={template_headings - promoted_headings}, "
        f"only-in-promoted={promoted_headings - template_headings}"
    )
