"""ai-ops review-pr のテスト (ADR 0012).

外部呼び出し (`gh`、LLM API、ファイル I/O) は monkeypatch で差し替え、
review.py 内部のロジック (context 組立 / レスポンス parse / dry-run の挙動 /
状態の return) を検証する。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_ops import review


def _fake_completed(stdout: str = "", returncode: int = 0):
    class FakeResult:
        pass

    r = FakeResult()
    r.stdout = stdout
    r.stderr = ""
    r.returncode = returncode
    return r


# ---------- _parse_llm_response ----------


def test_parse_response_success() -> None:
    raw = json.dumps({"state": "success", "summary": "looks good", "body": "**OK**"})
    result = review._parse_llm_response(raw)
    assert result.state == "success"
    assert result.summary == "looks good"
    assert "**OK**" in result.body


def test_parse_response_strips_markdown_fence() -> None:
    raw = "```json\n" + json.dumps({"state": "failure", "summary": "x", "body": "y"}) + "\n```"
    result = review._parse_llm_response(raw)
    assert result.state == "failure"


def test_parse_response_unparseable_returns_neutral() -> None:
    result = review._parse_llm_response("not json at all")
    assert result.state == "neutral"
    assert "not parseable" in result.summary.lower()


def test_parse_response_invalid_state_falls_back_to_neutral() -> None:
    raw = json.dumps({"state": "approve", "summary": "s", "body": "b"})
    result = review._parse_llm_response(raw)
    assert result.state == "neutral"


def test_parse_response_truncates_summary_to_140() -> None:
    long_summary = "x" * 200
    raw = json.dumps({"state": "success", "summary": long_summary, "body": "b"})
    result = review._parse_llm_response(raw)
    assert len(result.summary) == 140


# ---------- review_with_llm: API キー無しは neutral ----------


def test_review_skips_when_no_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ctx = review.PRContext(
        repo="o/r", number=1, head_sha="abc", base_ref="main",
        title="t", body="b", author="a", diff="",
        agents_md="", adrs={}, harness_toml=None, plan_md=None,
    )
    result = review.review_with_llm(ctx, provider="auto")
    assert result.state == "neutral"
    assert "no LLM API key" in result.summary


def test_review_uses_anthropic_when_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-a")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Nix sandbox では Path.home() = /homeless-shelter で書き込めないので
    # cost cache の append と budget read を mock で無効化する。
    monkeypatch.setattr(review, "_append_cost_entry", lambda *a, **kw: None)
    monkeypatch.setattr(review, "_load_review_config", lambda cwd: review.ReviewConfig())
    called: dict[str, Any] = {}

    def fake_anthropic(model, system, user, key):
        called["provider"] = "anthropic"
        called["key"] = key
        return (
            json.dumps({"state": "success", "summary": "ok", "body": "ok"}),
            1234,  # input tokens
            56,    # output tokens
        )

    monkeypatch.setattr(review, "_call_anthropic", fake_anthropic)
    monkeypatch.setattr(review, "_call_openai", lambda *a, **kw: pytest.fail("openai must not be called"))
    ctx = review.PRContext(
        repo="o/r", number=1, head_sha="abc", base_ref="main",
        title="t", body="b", author="a", diff="",
        agents_md="A", adrs={}, harness_toml=None, plan_md=None,
    )
    result = review.review_with_llm(ctx, provider="auto")
    assert called["provider"] == "anthropic"
    assert called["key"] == "key-a"
    assert result.state == "success"
    # cost footer が body に追記されている
    assert "ai-ops AI Review" in result.body
    assert "input=1,234 tok" in result.body
    assert "output=56 tok" in result.body


def test_review_falls_back_to_openai_when_only_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "key-o")
    monkeypatch.setattr(review, "_append_cost_entry", lambda *a, **kw: None)
    monkeypatch.setattr(review, "_load_review_config", lambda cwd: review.ReviewConfig())
    called: dict[str, Any] = {}

    def fake_openai(model, system, user, key):
        called["provider"] = "openai"
        return (
            json.dumps({"state": "success", "summary": "ok", "body": "ok"}),
            500, 30,
        )

    monkeypatch.setattr(review, "_call_anthropic", lambda *a, **kw: pytest.fail("anthropic must not be called"))
    monkeypatch.setattr(review, "_call_openai", fake_openai)
    ctx = review.PRContext(
        repo="o/r", number=1, head_sha="abc", base_ref="main",
        title="t", body="b", author="a", diff="",
        agents_md="A", adrs={}, harness_toml=None, plan_md=None,
    )
    result = review.review_with_llm(ctx, provider="auto")
    assert called["provider"] == "openai"
    assert result.state == "success"
    assert "input=500 tok" in result.body


# ---------- gather_context: gh 経由のデータ収集 ----------


def test_gather_context_returns_none_when_pr_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review, "_fetch_pr", lambda repo, pr: None)
    assert review.gather_context("o/r", 1) is None


def test_gather_context_assembles_from_gh_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review, "_fetch_pr", lambda repo, pr: {
        "number": pr,
        "headRefOid": "deadbeef",
        "baseRefName": "main",
        "title": "Test PR",
        "body": "PR body",
        "author": {"login": "u"},
    })
    monkeypatch.setattr(review, "_fetch_pr_diff", lambda repo, pr: "diff goes here")
    monkeypatch.setattr(review, "_list_adrs_at_ref", lambda repo, ref: ["0001-foo.md"])

    files: dict[str, str | None] = {
        "AGENTS.md": "AGENTS contents",
        ".ai-ops/harness.toml": "ai_ops_sha = 'abc'\n",
        "docs/decisions/0001-foo.md": "ADR foo",
    }

    def fake_fetch(repo, ref, path):
        return files.get(path)

    monkeypatch.setattr(review, "_fetch_file_at_ref", fake_fetch)

    ctx = review.gather_context("o/r", 42)
    assert ctx is not None
    assert ctx.repo == "o/r"
    assert ctx.number == 42
    assert ctx.head_sha == "deadbeef"
    assert ctx.title == "Test PR"
    assert ctx.author == "u"
    assert ctx.diff == "diff goes here"
    assert "AGENTS contents" in ctx.agents_md
    assert ctx.harness_toml is not None and "ai_ops_sha" in ctx.harness_toml
    assert "docs/decisions/0001-foo.md" in ctx.adrs
    # plan は diff に出てこないので None
    assert ctx.plan_md is None


def test_gather_context_loads_plan_when_in_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review, "_fetch_pr", lambda repo, pr: {
        "number": pr,
        "headRefOid": "deadbeef",
        "baseRefName": "main",
        "title": "t",
        "body": "",
        "author": {"login": "u"},
    })
    diff = "diff --git a/docs/plans/my-feature/plan.md b/docs/plans/my-feature/plan.md\n"
    monkeypatch.setattr(review, "_fetch_pr_diff", lambda repo, pr: diff)
    monkeypatch.setattr(review, "_list_adrs_at_ref", lambda repo, ref: [])

    fetched: list[tuple[str, str]] = []

    def fake_fetch(repo, ref, path):
        fetched.append((ref, path))
        if path == "docs/plans/my-feature/plan.md":
            return "# Plan\n\n## Outcomes\n\nDone.\n"
        if path == "AGENTS.md":
            return "agents"
        return None

    monkeypatch.setattr(review, "_fetch_file_at_ref", fake_fetch)
    ctx = review.gather_context("o/r", 1)
    assert ctx is not None
    assert ctx.plan_md is not None
    assert "Outcomes" in ctx.plan_md
    # plan は head ref から取られる
    assert ("deadbeef", "docs/plans/my-feature/plan.md") in fetched


# ---------- run_review_pr: dry-run / 投稿経路 ----------


def test_run_review_pr_dry_run_does_not_post(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(review, "_gh_available", lambda: True)
    monkeypatch.setattr(review, "_resolve_repo", lambda cwd: "o/r")
    fake_ctx = review.PRContext(
        repo="o/r", number=7, head_sha="sha", base_ref="main",
        title="t", body="b", author="a", diff="d",
        agents_md="A", adrs={}, harness_toml=None, plan_md=None,
    )
    monkeypatch.setattr(review, "gather_context", lambda repo, pr: fake_ctx)
    monkeypatch.setattr(review, "review_with_llm", lambda ctx, provider="auto", cwd=None, model_override=None, pr_labels=None: review.ReviewResult(
        state="success", summary="ok", body="### Review body",
    ))

    posted: dict[str, bool] = {"comment": False, "status": False}

    def boom_comment(*a, **kw):
        posted["comment"] = True
        return True

    def boom_status(*a, **kw):
        posted["status"] = True
        return True

    monkeypatch.setattr(review, "post_pr_comment", boom_comment)
    monkeypatch.setattr(review, "post_status_check", boom_status)

    rc = review.run_review_pr(pr=7, repo="o/r", dry_run=True, cwd=Path.cwd())
    assert rc == 0
    assert posted["comment"] is False
    assert posted["status"] is False
    out = capsys.readouterr().out
    assert "Review body" in out


def test_run_review_pr_posts_comment_and_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review, "_gh_available", lambda: True)
    monkeypatch.setattr(review, "_resolve_repo", lambda cwd: "o/r")
    fake_ctx = review.PRContext(
        repo="o/r", number=7, head_sha="sha", base_ref="main",
        title="t", body="b", author="a", diff="d",
        agents_md="A", adrs={}, harness_toml=None, plan_md=None,
    )
    monkeypatch.setattr(review, "gather_context", lambda repo, pr: fake_ctx)
    monkeypatch.setattr(review, "review_with_llm", lambda ctx, provider="auto", cwd=None, model_override=None, pr_labels=None: review.ReviewResult(
        state="failure", summary="bad", body="# Issues",
    ))

    captured: dict[str, Any] = {}

    def fake_comment(repo, pr, body):
        captured["comment"] = (repo, pr, body)
        return True

    def fake_status(repo, sha, state, description):
        captured["status"] = (repo, sha, state, description)
        return True

    monkeypatch.setattr(review, "post_pr_comment", fake_comment)
    monkeypatch.setattr(review, "post_status_check", fake_status)

    rc = review.run_review_pr(pr=7, repo="o/r", dry_run=False, cwd=Path.cwd())
    assert rc == 0
    assert captured["comment"] == ("o/r", 7, "# Issues")
    assert captured["status"] == ("o/r", "sha", "failure", "bad")


def test_run_review_pr_returns_2_when_no_gh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review, "_gh_available", lambda: False)
    rc = review.run_review_pr(pr=1, repo="o/r", dry_run=True, cwd=Path.cwd())
    assert rc == 2


def test_run_review_pr_returns_2_when_repo_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review, "_gh_available", lambda: True)
    monkeypatch.setattr(review, "_resolve_repo", lambda cwd: None)
    rc = review.run_review_pr(pr=1, repo=None, dry_run=True, cwd=Path.cwd())
    assert rc == 2


# ---------- _detect_plan_path ----------


def test_detect_plan_path_finds_first_plan_in_diff() -> None:
    diff = "+++ b/docs/plans/my-slug/plan.md\n+ content\n"
    assert review._detect_plan_path(diff) == "docs/plans/my-slug/plan.md"


def test_detect_plan_path_returns_none_when_no_plan() -> None:
    diff = "+++ b/some/other/file.py\n"
    assert review._detect_plan_path(diff) is None


# ---------- cost monitor (PR α) ----------


def test_estimate_cost_known_model() -> None:
    """既知 model は cost を返す。"""
    # claude-sonnet-4-6: input $3/MTok, output $15/MTok
    cost = review._estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 100_000)
    assert cost == pytest.approx(3.0 + 1.5)  # 3 + 100k × 15/MTok


def test_estimate_cost_unknown_model_returns_none() -> None:
    assert review._estimate_cost_usd("nonexistent-model", 1000, 100) is None


def test_format_cost_footer_known_model() -> None:
    footer = review._format_cost_footer("claude-sonnet-4-6", 24_938, 412)
    assert "claude-sonnet-4-6" in footer
    assert "input=24,938 tok" in footer
    assert "output=412 tok" in footer
    assert "estimated_cost=$" in footer


def test_format_cost_footer_unknown_model() -> None:
    footer = review._format_cost_footer("foo", 100, 10)
    assert "n/a (unknown model)" in footer


# ---------- PR ε: monthly budget cap + cache ----------


def test_review_skipped_when_budget_exceeded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`monthly_usd_limit` を超えていたら LLM を呼ばずに neutral skip。"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-a")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(review, "_load_review_config", lambda cwd: review.ReviewConfig(monthly_usd_limit=1.00))
    monkeypatch.setattr(review, "_read_monthly_total_usd", lambda month=None: 1.50)

    def boom_anthropic(*a, **kw):
        pytest.fail("anthropic must not be called when budget is exceeded")

    monkeypatch.setattr(review, "_call_anthropic", boom_anthropic)
    ctx = review.PRContext(
        repo="o/r", number=1, head_sha="abc", base_ref="main",
        title="t", body="b", author="a", diff="",
        agents_md="A", adrs={}, harness_toml=None, plan_md=None,
    )
    result = review.review_with_llm(ctx, provider="auto", cwd=tmp_path)
    assert result.state == "neutral"
    assert "budget exceeded" in result.summary.lower()


def test_review_records_cost_to_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """LLM 呼び出し後に月次キャッシュへ追記される。"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-a")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(review, "_load_review_config", lambda cwd: review.ReviewConfig())

    appended: list[dict] = []

    def fake_append(repo, pr, model, in_tok, out_tok, cost):
        appended.append({
            "repo": repo, "pr": pr, "model": model,
            "input": in_tok, "output": out_tok, "cost": cost,
        })

    monkeypatch.setattr(review, "_append_cost_entry", fake_append)
    monkeypatch.setattr(
        review, "_call_anthropic",
        lambda *a, **kw: (
            json.dumps({"state": "success", "summary": "ok", "body": "ok"}),
            1000, 50,
        ),
    )
    ctx = review.PRContext(
        repo="o/r", number=42, head_sha="abc", base_ref="main",
        title="t", body="b", author="a", diff="",
        agents_md="A", adrs={}, harness_toml=None, plan_md=None,
    )
    review.review_with_llm(ctx, provider="auto", cwd=tmp_path)
    assert len(appended) == 1
    assert appended[0]["repo"] == "o/r"
    assert appended[0]["pr"] == 42
    assert appended[0]["input"] == 1000
    assert appended[0]["output"] == 50


def test_read_monthly_budget_from_harness_toml(tmp_path: Path) -> None:
    (tmp_path / ".ai-ops").mkdir()
    (tmp_path / ".ai-ops" / "harness.toml").write_text(
        '[review_budget]\nmonthly_usd_limit = 5.0\n',
        encoding="utf-8",
    )
    assert review._read_monthly_budget_usd(tmp_path) == 5.0


def test_read_monthly_budget_env_overrides_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".ai-ops").mkdir()
    (tmp_path / ".ai-ops" / "harness.toml").write_text(
        '[review_budget]\nmonthly_usd_limit = 5.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_OPS_REVIEW_BUDGET_USD_MONTH", "1.5")
    assert review._read_monthly_budget_usd(tmp_path) == 1.5


def test_read_monthly_budget_returns_none_without_config(tmp_path: Path) -> None:
    assert review._read_monthly_budget_usd(tmp_path) is None


# ---------- PR ζ: ReviewConfig + skip + model auto ----------


def test_review_config_disabled_skips(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-a")
    (tmp_path / ".ai-ops").mkdir()
    (tmp_path / ".ai-ops" / "harness.toml").write_text(
        '[review]\nenabled = false\n', encoding="utf-8",
    )
    monkeypatch.setattr(review, "_call_anthropic",
                        lambda *a, **kw: pytest.fail("must not be called"))
    ctx = review.PRContext(
        repo="o/r", number=1, head_sha="abc", base_ref="main",
        title="t", body="b", author="a", diff="",
        agents_md="A", adrs={}, harness_toml=None, plan_md=None,
    )
    result = review.review_with_llm(ctx, provider="auto", cwd=tmp_path)
    assert result.state == "neutral"
    assert "disabled" in result.summary.lower()


def test_review_skip_label_triggers_neutral(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-a")
    (tmp_path / ".ai-ops").mkdir()
    (tmp_path / ".ai-ops" / "harness.toml").write_text(
        '[review]\nenabled = true\nskip_label_patterns = ["no-review"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(review, "_call_anthropic",
                        lambda *a, **kw: pytest.fail("must not be called"))
    ctx = review.PRContext(
        repo="o/r", number=1, head_sha="abc", base_ref="main",
        title="t", body="b", author="a", diff="",
        agents_md="A", adrs={}, harness_toml=None, plan_md=None,
    )
    result = review.review_with_llm(
        ctx, provider="auto", cwd=tmp_path,
        pr_labels=["enhancement", "no-review"],
    )
    assert result.state == "neutral"
    assert "no-review" in result.summary


def test_review_skip_path_patterns_when_all_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-a")
    (tmp_path / ".ai-ops").mkdir()
    (tmp_path / ".ai-ops" / "harness.toml").write_text(
        '[review]\nenabled = true\nskip_path_patterns = ["**/*.lock"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(review, "_call_anthropic",
                        lambda *a, **kw: pytest.fail("must not be called"))
    diff = "+++ b/flake.lock\n+ change\n+++ b/poetry.lock\n+ change\n"
    ctx = review.PRContext(
        repo="o/r", number=1, head_sha="abc", base_ref="main",
        title="t", body="b", author="a", diff=diff,
        agents_md="A", adrs={}, harness_toml=None, plan_md=None,
    )
    result = review.review_with_llm(ctx, provider="auto", cwd=tmp_path)
    assert result.state == "neutral"
    assert "skip_path_patterns" in result.summary


def test_review_path_partial_match_does_not_skip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-a")
    (tmp_path / ".ai-ops").mkdir()
    (tmp_path / ".ai-ops" / "harness.toml").write_text(
        '[review]\nenabled = true\nskip_path_patterns = ["**/*.lock"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(review, "_append_cost_entry", lambda *a, **kw: None)
    monkeypatch.setattr(review, "_call_anthropic",
                        lambda *a, **kw: (
                            json.dumps({"state": "success", "summary": "ok", "body": "ok"}),
                            100, 10,
                        ))
    diff = "+++ b/flake.lock\n+ change\n+++ b/main.py\n+ change\n"
    ctx = review.PRContext(
        repo="o/r", number=1, head_sha="abc", base_ref="main",
        title="t", body="b", author="a", diff=diff,
        agents_md="A", adrs={}, harness_toml=None, plan_md=None,
    )
    result = review.review_with_llm(ctx, provider="auto", cwd=tmp_path)
    assert result.state == "success"


def test_choose_model_auto_for_security_label() -> None:
    cfg = review.ReviewConfig()
    assert review._choose_model_auto(["security"], 100, cfg) == "claude-opus-4-7"


def test_choose_model_auto_for_docs_label_small_diff() -> None:
    cfg = review.ReviewConfig()
    assert review._choose_model_auto(["docs"], 50, cfg) == "claude-haiku-4-5-20251001"


def test_choose_model_auto_default_when_no_signal() -> None:
    cfg = review.ReviewConfig(default_model="claude-sonnet-4-6")
    assert review._choose_model_auto(["enhancement"], 1000, cfg) == "claude-sonnet-4-6"


def test_load_review_config_reads_full_block(tmp_path: Path) -> None:
    (tmp_path / ".ai-ops").mkdir()
    (tmp_path / ".ai-ops" / "harness.toml").write_text(
        '[review]\n'
        'enabled = true\n'
        'monthly_usd_limit = 3.5\n'
        'per_pr_usd_limit = 0.20\n'
        'default_model = "claude-haiku-4-5-20251001"\n'
        'skip_label_patterns = ["a", "b"]\n'
        'skip_path_patterns = ["**/*.md"]\n'
        'on_label = "review:request"\n',
        encoding="utf-8",
    )
    cfg = review._load_review_config(tmp_path)
    assert cfg.enabled is True
    assert cfg.monthly_usd_limit == 3.5
    assert cfg.per_pr_usd_limit == 0.20
    assert cfg.default_model == "claude-haiku-4-5-20251001"
    assert cfg.skip_label_patterns == ("a", "b")
    assert cfg.skip_path_patterns == ("**/*.md",)
    assert cfg.on_label == "review:request"


def test_load_review_config_falls_back_to_legacy_review_budget(tmp_path: Path) -> None:
    (tmp_path / ".ai-ops").mkdir()
    (tmp_path / ".ai-ops" / "harness.toml").write_text(
        '[review_budget]\nmonthly_usd_limit = 1.5\n', encoding="utf-8",
    )
    cfg = review._load_review_config(tmp_path)
    assert cfg.monthly_usd_limit == 1.5
    assert cfg.enabled is True
