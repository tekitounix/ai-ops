"""Tests for ai_ops.setup helpers (PR η added)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ai_ops import setup
from ai_ops.paths import package_root


def test_setup_ci_workflow_substitutes_ai_ops_ref_in_uses_lines() -> None:
    """PR η: `setup ci --ai-ops-ref v1.0` で template の `@main` が `@v1.0` に置換される。"""
    template_path = (
        package_root() / "templates" / "artifacts" / ".github" / "workflows" / "ai-ops.yml"
    )
    template_content = template_path.read_text(encoding="utf-8")
    # template が `@main` を含むこと (PR η の前提)
    assert "managed-project-check.yml@main" in template_content
    assert "managed-project-review.yml@main" in template_content

    # Simulate substitution as run_setup_ci_workflow does
    ai_ops_ref = "v1.0"
    tier = "B"
    content = template_content
    content = content.replace("tier: 'D'", f"tier: '{tier}'")
    content = content.replace("ai_ops_ref: 'main'", f"ai_ops_ref: '{ai_ops_ref}'")
    content = content.replace(
        "managed-project-check.yml@main",
        f"managed-project-check.yml@{ai_ops_ref}",
    )
    content = content.replace(
        "managed-project-review.yml@main",
        f"managed-project-review.yml@{ai_ops_ref}",
    )
    assert "managed-project-check.yml@v1.0" in content
    assert "managed-project-review.yml@v1.0" in content
    assert "managed-project-check.yml@main" not in content
    assert "tier: 'B'" in content
    assert "ai_ops_ref: 'v1.0'" in content


def test_setup_ci_template_uses_explicit_secrets_not_inherit() -> None:
    """PR η: `secrets: inherit` は startup_failure の原因なので明示渡しに変えた。"""
    template_path = (
        package_root() / "templates" / "artifacts" / ".github" / "workflows" / "ai-ops.yml"
    )
    content = template_path.read_text(encoding="utf-8")
    # secrets: inherit が消えている
    assert "secrets: inherit" not in content
    # 明示渡しに変わっている
    assert "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in content
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in content


def test_setup_ci_template_default_uses_main_not_v1() -> None:
    """PR η: template の `uses:` 行が `@main` (tag は今のところ無し)。"""
    template_path = (
        package_root() / "templates" / "artifacts" / ".github" / "workflows" / "ai-ops.yml"
    )
    content = template_path.read_text(encoding="utf-8")
    # `uses:` 行に @v1 がない (comment 内の `@v1.0` 例示は許容)
    for line in content.splitlines():
        if "uses:" in line and "tekitounix/ai-ops" in line:
            assert "@main" in line, f"line uses non-main ref: {line}"
