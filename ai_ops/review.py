"""PR の AI レビュー (ADR 0012)。

`ai-ops review-pr` は管理対象プロジェクトの PR を ai-ops 固有の規約 (AGENTS.md /
ADR / harness.toml / 関連 plan) と突き合わせて言語的にレビューする。GitHub
Copilot Code Review が汎用品質を見るのと役割分担し、こちらは ai-ops repo に
コミットされた契約への適合を判定する。

入力:
    --pr <N>       PR 番号
    --repo OWNER/NAME (省略時は cwd の origin)
    --dry-run      Comment / status check の投稿を抑制
    --provider {anthropic,openai,auto}
                   default: auto (環境変数 ANTHROPIC_API_KEY > OPENAI_API_KEY)

出力:
    PR Comment (Markdown、`gh pr comment` 経由)
    Status check `ai-ops AI Review` (`success` / `failure` / `neutral`、
    `gh api repos/.../statuses/<sha>` 経由)

API キーが両方無い場合は `neutral` を投稿して exit 0 (skip)。これにより
secrets 未設定の repo でも CI を壊さない。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

STATUS_CONTEXT = "ai-ops AI Review"
DEFAULT_TIMEOUT = 60


# ---------- 外部呼び出しのためのプリミティブ (テストは monkeypatch で差し替え) ----------


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _gh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=DEFAULT_TIMEOUT,
    )


# ---------- データクラス ----------


@dataclass
class PRContext:
    """LLM に渡す PR の文脈一式。"""

    repo: str  # owner/name
    number: int
    head_sha: str
    base_ref: str
    title: str
    body: str
    author: str
    diff: str
    agents_md: str
    adrs: dict[str, str]  # path → content
    harness_toml: str | None
    plan_md: str | None  # 該当 plan があれば


@dataclass
class ReviewResult:
    """LLM レビュー結果。"""

    state: Literal["success", "failure", "neutral"]
    summary: str  # status check description (1 行、140 字以内)
    body: str  # PR Comment 本文 (Markdown)


# ---------- PR 文脈の収集 ----------


def _resolve_repo(cwd: Path) -> str | None:
    """cwd の origin から owner/name を解決する。"""
    result = _gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"])
    if result.returncode == 0:
        name = result.stdout.strip()
        return name or None
    return None


def _fetch_pr(repo: str, pr: int) -> dict | None:
    result = _gh([
        "pr", "view", str(pr),
        "--repo", repo,
        "--json", "number,headRefOid,baseRefName,title,body,author",
    ])
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _fetch_pr_diff(repo: str, pr: int) -> str:
    result = _gh(["pr", "diff", str(pr), "--repo", repo])
    return result.stdout if result.returncode == 0 else ""


def _fetch_file_at_ref(repo: str, ref: str, path: str) -> str | None:
    """リモートの指定 ref からファイル内容を取得する (`gh api` 経由)。"""
    result = _gh([
        "api",
        f"repos/{repo}/contents/{path}",
        "-q", ".content",
        "-f", f"ref={ref}",
    ])
    if result.returncode != 0:
        return None
    encoded = result.stdout.strip()
    if not encoded:
        return None
    import base64
    try:
        return base64.b64decode(encoded).decode("utf-8", errors="replace")
    except Exception:
        return None


def _list_adrs_at_ref(repo: str, ref: str) -> list[str]:
    """`docs/decisions/` 直下の `.md` ファイル名を列挙する。"""
    result = _gh([
        "api",
        f"repos/{repo}/contents/docs/decisions",
        "-q", "[.[] | select(.type==\"file\") | .name]",
        "-f", f"ref={ref}",
    ])
    if result.returncode != 0:
        return []
    try:
        names = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return [n for n in names if isinstance(n, str) and n.endswith(".md")]


def _detect_plan_path(diff: str) -> str | None:
    """diff から `docs/plans/<slug>/plan.md` の path を検出する。

    複数あれば最初のものを返す (PR 内で複数 plan を触るのは稀)。
    """
    import re
    match = re.search(r"docs/plans/([^/]+)/plan\.md", diff)
    if not match:
        return None
    return f"docs/plans/{match.group(1)}/plan.md"


def gather_context(repo: str, pr: int) -> PRContext | None:
    meta = _fetch_pr(repo, pr)
    if meta is None:
        return None
    head_sha = meta.get("headRefOid", "")
    base_ref = meta.get("baseRefName", "main")
    diff = _fetch_pr_diff(repo, pr)
    agents = _fetch_file_at_ref(repo, base_ref, "AGENTS.md") or ""
    harness = _fetch_file_at_ref(repo, base_ref, ".ai-ops/harness.toml")
    adrs: dict[str, str] = {}
    for name in _list_adrs_at_ref(repo, base_ref):
        content = _fetch_file_at_ref(repo, base_ref, f"docs/decisions/{name}")
        if content is not None:
            adrs[f"docs/decisions/{name}"] = content
    plan_md: str | None = None
    plan_path = _detect_plan_path(diff)
    if plan_path:
        # PR head から plan を取る (PR が plan を作成 / 更新する場合)。
        plan_md = _fetch_file_at_ref(repo, head_sha, plan_path)
    author_obj = meta.get("author") or {}
    return PRContext(
        repo=repo,
        number=int(meta.get("number", pr)),
        head_sha=head_sha,
        base_ref=base_ref,
        title=str(meta.get("title", "")),
        body=str(meta.get("body", "") or ""),
        author=str(author_obj.get("login", "")),
        diff=diff,
        agents_md=agents,
        adrs=adrs,
        harness_toml=harness,
        plan_md=plan_md,
    )


# ---------- LLM 呼び出し (Anthropic / OpenAI) ----------


REVIEW_SYSTEM_PROMPT = """You are an ai-ops review agent. ai-ops is a cross-project AI operations
toolkit; the PR you are reviewing belongs to a project that has adopted ai-ops as its operating
contract.

Your job: judge whether the PR diff respects the project's committed contract — AGENTS.md, ADRs,
.ai-ops/harness.toml, and (if the PR touches one) the corresponding execution plan. You are NOT
reviewing general code quality; that's GitHub Copilot Code Review's job. Focus on contract
compliance.

Specifically check:
- Branch naming follows `<type>/<slug>` (feat / fix / chore / docs / refactor) when applicable.
- If the PR includes a plan.md, its `Branch` / `Worktree` / `Plan path` fields match the actual
  branch name, and the Outcomes & Retrospective section is filled (not still TBD) when Progress is
  complete.
- propagate-* PRs (head branch starts with `ai-ops/`) only modify the declared scope: anchor PRs
  touch only `.ai-ops/harness.toml`'s `ai_ops_sha`; init PRs only commit a new `.ai-ops/harness.toml`;
  files PRs only refresh hash records.
- Tier consistency: if the project declares `workflow_tier`, the PR practice (long-lived branch,
  direct push, etc.) is consistent with the tier.
- ADR 0010 §Lifecycle 4 (post-merge sequence) is not pre-violated by the PR (e.g. archive commits
  go through the right path for the tier).
- Workflow / harness changes are reflected in the appropriate ADR or plan.

Return a JSON object with three keys:
- "state": one of "success", "failure", "neutral".
  - "success" = PR respects the contract (minor stylistic notes are still success).
  - "failure" = PR violates the contract in a way that blocks merge.
  - "neutral" = PR is out of scope for contract review (e.g. dependency bump only, doc typo).
- "summary": one-line description (under 140 chars) for the GitHub status check.
- "body": multi-line Markdown for the PR Comment. Cite specific files / lines / ADR sections.
  Be concise; no chitchat.

When in doubt, prefer "success" over "failure". Only mark "failure" when you are confident the
PR violates a clear contract clause; cite the clause in `body`.
"""


def _call_anthropic(model: str, system: str, user: str, api_key: str) -> str | None:
    import urllib.request
    payload = {
        "model": model,
        "max_tokens": 2048,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"anthropic call failed: {exc}", file=sys.stderr)
        return None
    blocks = data.get("content") or []
    for block in blocks:
        if block.get("type") == "text":
            return block.get("text")
    return None


def _call_openai(model: str, system: str, user: str, api_key: str) -> str | None:
    import urllib.request
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"openai call failed: {exc}", file=sys.stderr)
        return None
    choices = data.get("choices") or []
    if not choices:
        return None
    return (choices[0].get("message") or {}).get("content")


def _format_user_prompt(ctx: PRContext) -> str:
    parts: list[str] = []
    parts.append(f"# PR #{ctx.number} on {ctx.repo}")
    parts.append(f"Title: {ctx.title}")
    parts.append(f"Author: {ctx.author}")
    parts.append(f"Base ref: {ctx.base_ref}  Head SHA: {ctx.head_sha}")
    parts.append("")
    parts.append("## PR body")
    parts.append(ctx.body or "(empty)")
    parts.append("")
    parts.append("## AGENTS.md (base ref)")
    parts.append(ctx.agents_md[:8000] or "(missing)")
    parts.append("")
    if ctx.harness_toml is not None:
        parts.append("## .ai-ops/harness.toml (base ref)")
        parts.append(ctx.harness_toml[:2000])
        parts.append("")
    if ctx.adrs:
        parts.append("## ADRs (base ref, file: content)")
        for path, content in sorted(ctx.adrs.items()):
            parts.append(f"### {path}")
            parts.append(content[:4000])
            parts.append("")
    if ctx.plan_md is not None:
        parts.append("## Plan (head ref)")
        parts.append(ctx.plan_md[:8000])
        parts.append("")
    parts.append("## Diff")
    parts.append(ctx.diff[:30000])
    return "\n".join(parts)


def review_with_llm(
    ctx: PRContext,
    provider: Literal["anthropic", "openai", "auto"] = "auto",
) -> ReviewResult:
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    chosen: Literal["anthropic", "openai"] | None
    if provider == "anthropic" and anthropic_key:
        chosen = "anthropic"
    elif provider == "openai" and openai_key:
        chosen = "openai"
    elif provider == "auto":
        chosen = "anthropic" if anthropic_key else ("openai" if openai_key else None)
    else:
        chosen = None
    if chosen is None:
        return ReviewResult(
            state="neutral",
            summary="ai-ops review skipped (no LLM API key)",
            body=(
                "`ai-ops review-pr` skipped: neither `ANTHROPIC_API_KEY` nor "
                "`OPENAI_API_KEY` is set. Configure either secret to enable AI review."
            ),
        )
    user_prompt = _format_user_prompt(ctx)
    raw: str | None
    if chosen == "anthropic":
        raw = _call_anthropic(
            os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            REVIEW_SYSTEM_PROMPT,
            user_prompt,
            anthropic_key or "",
        )
    else:
        raw = _call_openai(
            os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            REVIEW_SYSTEM_PROMPT,
            user_prompt,
            openai_key or "",
        )
    if not raw:
        return ReviewResult(
            state="neutral",
            summary="ai-ops review skipped (LLM call failed)",
            body="LLM call returned no content. See workflow logs for details.",
        )
    return _parse_llm_response(raw)


def _parse_llm_response(raw: str) -> ReviewResult:
    """LLM 応答 (JSON 想定) を ReviewResult にパースする。失敗時は neutral。"""
    text = raw.strip()
    # Anthropic は素の JSON ではなく markdown code fence で返す場合がある
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.startswith("```")]
        text = "\n".join(lines)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return ReviewResult(
            state="neutral",
            summary="ai-ops review: LLM response not parseable",
            body=f"Raw response:\n\n```\n{raw[:2000]}\n```",
        )
    state_val = str(obj.get("state", "neutral"))
    if state_val not in ("success", "failure", "neutral"):
        state_val = "neutral"
    return ReviewResult(
        state=state_val,  # type: ignore[arg-type]
        summary=str(obj.get("summary", ""))[:140] or "ai-ops AI review complete",
        body=str(obj.get("body", "")) or "(no detailed feedback)",
    )


# ---------- 出力 (Comment + status check) ----------


def post_pr_comment(repo: str, pr: int, body: str) -> bool:
    """PR に Comment を投稿する。"""
    # gh pr comment は body をファイルから読む方が安定 (`--body-file`)
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(body)
        path = fh.name
    try:
        result = _gh([
            "pr", "comment", str(pr),
            "--repo", repo,
            "--body-file", path,
        ])
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    return result.returncode == 0


def post_status_check(
    repo: str,
    sha: str,
    state: Literal["success", "failure", "neutral", "pending", "error"],
    description: str,
) -> bool:
    """Commit status を投稿する (`gh api repos/.../statuses/<sha>`)。

    GitHub の statuses API は `state=neutral` を直接受け付けないので、
    neutral は `success` で代替し description にスキップ理由を入れる。
    """
    api_state = state if state in ("success", "failure", "pending", "error") else "success"
    result = _gh([
        "api",
        f"repos/{repo}/statuses/{sha}",
        "-X", "POST",
        "-f", f"state={api_state}",
        "-f", f"context={STATUS_CONTEXT}",
        "-f", f"description={description[:140]}",
    ])
    return result.returncode == 0


# ---------- エントリポイント ----------


def run_review_pr(
    pr: int,
    repo: str | None = None,
    dry_run: bool = False,
    provider: Literal["anthropic", "openai", "auto"] = "auto",
    cwd: Path | None = None,
) -> int:
    if not _gh_available():
        print("`gh` is required (Tier 1). Install with `ai-ops bootstrap`.", file=sys.stderr)
        return 2
    work_dir = cwd or Path.cwd()
    target_repo = repo or _resolve_repo(work_dir)
    if not target_repo:
        print(
            "Could not resolve repo. Pass --repo OWNER/NAME or run inside a repo with origin set.",
            file=sys.stderr,
        )
        return 2
    print(f"==> ai-ops review-pr: {target_repo}#{pr}")
    ctx = gather_context(target_repo, pr)
    if ctx is None:
        print(f"Failed to fetch PR {target_repo}#{pr}", file=sys.stderr)
        return 1
    print(f"  context gathered: AGENTS.md={len(ctx.agents_md)} bytes, "
          f"ADRs={len(ctx.adrs)}, plan={'yes' if ctx.plan_md else 'no'}, "
          f"diff={len(ctx.diff)} bytes")
    result = review_with_llm(ctx, provider=provider)
    print(f"  result: state={result.state}  summary={result.summary}")
    if dry_run:
        print("  --dry-run: skipping Comment / status check post")
        print("---- Comment body ----")
        print(result.body)
        print("---- end ----")
        return 0
    comment_ok = post_pr_comment(target_repo, pr, result.body)
    status_ok = post_status_check(target_repo, ctx.head_sha, result.state, result.summary)
    if not comment_ok:
        print("  WARN: failed to post PR comment", file=sys.stderr)
    if not status_ok:
        print("  WARN: failed to post status check", file=sys.stderr)
    # `failure` の状態は status check で merge を止める。CLI の exit は status post の
    # 成否を反映する (両方 OK なら 0)。
    return 0 if (comment_ok and status_ok) else 1
