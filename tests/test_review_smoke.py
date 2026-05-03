"""実 LLM API を叩く smoke test (PR γ)。

`@pytest.mark.smoke` で skip default。`ANTHROPIC_API_KEY` または `OPENAI_API_KEY`
が設定されていれば実 API を 1 ping して、SDK 仕様変更を本番 PR より先に検知する。

CI では:
- default の `python -m ai_ops check` には含まれない (smoke marker のため)
- 別 job で `pytest -m smoke` を `if: secrets.ANTHROPIC_API_KEY != ''` で gate
- ローカルでは `pytest tests/test_review_smoke.py -m smoke` で手動実行可

API コストは 1 件 < $0.001 程度 (max_tokens=64 + 短い prompt)。
"""
from __future__ import annotations

import os

import pytest

from ai_ops import review


@pytest.mark.smoke
def test_anthropic_api_returns_parseable_text() -> None:
    """Anthropic Messages API が text + usage を返す (SDK 契約)。"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    text, in_tok, out_tok = review._call_anthropic(
        os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        'Reply with the literal JSON: {"ok": true}',
        "ping",
        api_key,
    )
    assert text is not None and len(text) > 0, "no text returned"
    assert in_tok > 0, "input_tokens missing in usage"
    assert out_tok > 0, "output_tokens missing in usage"


@pytest.mark.smoke
def test_openai_api_returns_parseable_text() -> None:
    """OpenAI Chat Completions API が text + usage を返す (SDK 契約)。"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")
    text, in_tok, out_tok = review._call_openai(
        os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        'Reply with the literal JSON: {"ok": true}',
        "ping",
        api_key,
    )
    assert text is not None and len(text) > 0, "no text returned"
    assert in_tok > 0, "prompt_tokens missing in usage"
    assert out_tok > 0, "completion_tokens missing in usage"
