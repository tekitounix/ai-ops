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

# LLM 価格表 (USD per million tokens、2026-05 時点)。
# 新モデル追加時はここに追記。未知モデルは cost 表示 skip。
PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    # OpenAI
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.0},
}


def _estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """model と token 数から USD コストを推定。未知 model は None。"""
    rates = PRICING_USD_PER_MTOK.get(model)
    if rates is None:
        return None
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


def _format_cost_footer(
    model: str, input_tokens: int, output_tokens: int
) -> str:
    """PR Comment 末尾と stdout に出すコスト情報行。"""
    cost = _estimate_cost_usd(model, input_tokens, output_tokens)
    cost_str = f"${cost:.4f}" if cost is not None else "n/a (unknown model)"
    return (
        f"---\nai-ops AI Review · model={model} "
        f"· input={input_tokens:,} tok · output={output_tokens:,} tok "
        f"· estimated_cost={cost_str}"
    )


# ---------- monthly cost cap + cache (PR ε, CR3) ----------


def _cost_cache_path(month: str | None = None) -> Path:
    """`~/.cache/ai-ops/review-cost-YYYY-MM.json` の path を返す。"""
    from datetime import datetime, timezone
    if month is None:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
    return Path.home() / ".cache" / "ai-ops" / f"review-cost-{month}.json"


def _read_monthly_total_usd(month: str | None = None) -> float:
    """月次累計 USD を返す (キャッシュが無ければ 0)。"""
    path = _cost_cache_path(month)
    if not path.is_file():
        return 0.0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0.0
    entries = data.get("entries", [])
    return sum(float(e.get("cost_usd", 0.0)) for e in entries)


def _append_cost_entry(
    repo: str, pr: int, model: str,
    input_tokens: int, output_tokens: int, cost_usd: float | None,
) -> None:
    """月次キャッシュに 1 entry 追記する (best-effort)。"""
    from datetime import datetime, timezone
    path = _cost_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"entries": []}
    except (OSError, json.JSONDecodeError):
        data = {"entries": []}
    data.setdefault("entries", []).append({
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": repo,
        "pr": pr,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd if cost_usd is not None else 0.0,
    })
    try:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _read_monthly_budget_usd(cwd: Path) -> float | None:
    """`harness.toml::[review_budget].monthly_usd_limit` または env var から読む。

    優先: env var `AI_OPS_REVIEW_BUDGET_USD_MONTH` > harness.toml > None。
    None は cap 無し (default 挙動)。
    """
    env_val = os.environ.get("AI_OPS_REVIEW_BUDGET_USD_MONTH")
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    manifest = cwd / ".ai-ops" / "harness.toml"
    if not manifest.is_file():
        return None
    try:
        text = manifest.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    import re as _re
    match = _re.search(
        r"\[review_budget\][^\[]*?monthly_usd_limit\s*=\s*([\d.]+)",
        text, flags=_re.DOTALL,
    )
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def run_review_cost(month: str | None = None) -> int:
    """月次レビューコストを表で出力する (PR ε)。

    `--month YYYY-MM` で指定可。default は当月。
    """
    from datetime import datetime, timezone
    if month is None:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
    path = _cost_cache_path(month)
    print(f"==> ai-ops review cost summary ({month})")
    print(f"  cache: {path}")
    if not path.is_file():
        print("  (no entries yet)")
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  ERROR: cache unreadable ({exc})", file=sys.stderr)
        return 1
    entries = data.get("entries", [])
    if not entries:
        print("  (no entries)")
        return 0
    # repo + model 単位で集計
    by_repo: dict[str, dict[str, float | int]] = {}
    for e in entries:
        repo = e.get("repo", "?")
        agg = by_repo.setdefault(repo, {"count": 0, "input": 0, "output": 0, "cost": 0.0})
        agg["count"] = int(agg["count"]) + 1
        agg["input"] = int(agg["input"]) + int(e.get("input_tokens", 0))
        agg["output"] = int(agg["output"]) + int(e.get("output_tokens", 0))
        agg["cost"] = float(agg["cost"]) + float(e.get("cost_usd", 0.0))
    total_cost = sum(float(v["cost"]) for v in by_repo.values())
    total_count = sum(int(v["count"]) for v in by_repo.values())
    print(f"  reviews: {total_count}, total estimated cost: ${total_cost:.4f}")
    print()
    print(f"  {'repo':<35} {'count':>6} {'input tok':>12} {'output tok':>12} {'cost USD':>10}")
    for repo in sorted(by_repo.keys()):
        v = by_repo[repo]
        print(
            f"  {repo[:34]:<35} {int(v['count']):>6} {int(v['input']):>12,} "
            f"{int(v['output']):>12,} ${float(v['cost']):>9.4f}"
        )
    return 0


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


def _call_anthropic(
    model: str, system: str, user: str, api_key: str
) -> tuple[str | None, int, int]:
    """Anthropic API を呼び、(text, input_tokens, output_tokens) を返す。"""
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
        return None, 0, 0
    text: str | None = None
    for block in data.get("content") or []:
        if block.get("type") == "text":
            text = block.get("text")
            break
    usage = data.get("usage") or {}
    return text, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))


def _call_openai(
    model: str, system: str, user: str, api_key: str
) -> tuple[str | None, int, int]:
    """OpenAI API を呼び、(text, input_tokens, output_tokens) を返す。"""
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
        return None, 0, 0
    choices = data.get("choices") or []
    text: str | None = None
    if choices:
        text = (choices[0].get("message") or {}).get("content")
    usage = data.get("usage") or {}
    return (
        text,
        int(usage.get("prompt_tokens", 0)),
        int(usage.get("completion_tokens", 0)),
    )


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
    cwd: Path | None = None,
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
    # PR ε: monthly budget cap. 累計 USD が `monthly_usd_limit` を超えていたら
    # neutral skip。default は cap 無し (既存挙動を壊さない)。
    budget = _read_monthly_budget_usd(cwd or Path.cwd())
    if budget is not None:
        spent = _read_monthly_total_usd()
        if spent >= budget:
            return ReviewResult(
                state="neutral",
                summary=f"ai-ops review skipped (budget exceeded: ${spent:.4f} ≥ ${budget:.4f})",
                body=(
                    f"`ai-ops review-pr` skipped this PR because the monthly review "
                    f"budget is reached: spent ${spent:.4f} of ${budget:.4f} cap "
                    f"(set via `[review_budget].monthly_usd_limit` in `.ai-ops/harness.toml` "
                    f"or `AI_OPS_REVIEW_BUDGET_USD_MONTH` env var)."
                ),
            )
    user_prompt = _format_user_prompt(ctx)
    raw: str | None
    input_tokens = output_tokens = 0
    if chosen == "anthropic":
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        raw, input_tokens, output_tokens = _call_anthropic(
            model, REVIEW_SYSTEM_PROMPT, user_prompt, anthropic_key or "",
        )
    else:
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        raw, input_tokens, output_tokens = _call_openai(
            model, REVIEW_SYSTEM_PROMPT, user_prompt, openai_key or "",
        )
    if not raw:
        return ReviewResult(
            state="neutral",
            summary="ai-ops review skipped (LLM call failed)",
            body="LLM call returned no content. See workflow logs for details.",
        )
    result = _parse_llm_response(raw)
    # Comment 末尾に cost footer を貼る (使用量 + 推定 USD)
    footer = _format_cost_footer(model, input_tokens, output_tokens)
    # PR ε: 月次キャッシュに記録 (CR3 の closure)
    cost = _estimate_cost_usd(model, input_tokens, output_tokens)
    _append_cost_entry(ctx.repo, ctx.number, model, input_tokens, output_tokens, cost)
    return ReviewResult(
        state=result.state,
        summary=result.summary,
        body=f"{result.body}\n\n{footer}",
    )


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
    result = review_with_llm(ctx, provider=provider, cwd=work_dir)
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
