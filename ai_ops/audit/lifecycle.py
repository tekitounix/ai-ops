from __future__ import annotations

from pathlib import Path


REQUIRED_FILES = (
    "README.md",
    "AGENTS.md",
    "docs/ai-first-lifecycle.md",
    "docs/project-addition-and-migration.md",
    "docs/decisions/0007-python-canonical-cli.md",
    "templates/project-brief.md",
    "templates/migration-brief.md",
    "templates/agent-handoff.md",
    "pyproject.toml",
    ".github/workflows/ci.yml",
    "ai_ops/cli.py",
    "ai_ops/lifecycle/project.py",
    "ai_ops/lifecycle/migration.py",
)

CLASSIFICATION_TERMS = ("Fact", "Inference", "Risk", "User decision", "AI recommendation")


def run_lifecycle_audit(root: Path) -> int:
    fail = 0
    passed = 0
    print("==> ai-ops lifecycle audit")
    for rel in REQUIRED_FILES:
        if (root / rel).is_file():
            print(f"  OK: {rel} exists")
            passed += 1
        else:
            print(f"  FAIL: {rel} missing")
            fail += 1

    classification_files = (
        "templates/project-brief.md",
        "templates/migration-brief.md",
        "docs/ai-first-lifecycle.md",
    )
    if all((root / rel).is_file() for rel in classification_files):
        classification_fail_before = fail
        for rel in classification_files:
            text = (root / rel).read_text(encoding="utf-8")
            for term in CLASSIFICATION_TERMS:
                if term not in text:
                    print(f"  FAIL: {rel} missing classification term: {term}")
                    fail += 1
        if fail == classification_fail_before:
            print("  OK: brief classification terms present")
            passed += 1

    active_docs = (
        "README.md",
        "AGENTS.md",
        "docs/ai-first-lifecycle.md",
        "docs/project-addition-and-migration.md",
    )
    stale_markers = (
        "migration in progress",
        "移行中",
        "Phase 3.5",
        "Phase 4 READY",
        "review-template-2026-04-22-extended",
        "remaining-review",
        "migration/status.md",
        "--execute-approved",
        "scripts/ai-ops.sh",
        "scripts/ai-ops.ps1",
        "scripts/ai-ops.cmd",
        "ai-ops CLI を取得・更新",
    )
    for rel in active_docs:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in stale_markers:
            if marker in text:
                print(f"  FAIL: {rel} contains stale marker: {marker}")
                fail += 1

    forbidden_paths = (
        "START-HERE.md",
        "QUICK-REFERENCE.md",
        "archive",
        "migration",
        "plans",
        "scripts",
        "recipes",
        "hooks",
        "docs/reference",
        "docs/research",
        "docs/project-ledger.md",
    )
    for rel in forbidden_paths:
        if (root / rel).exists():
            print(f"  FAIL: {rel} should not be in the active tree")
            fail += 1

    allowed_template_files = {
        root / "templates" / "project-brief.md",
        root / "templates" / "migration-brief.md",
        root / "templates" / "agent-handoff.md",
    }
    template_root = root / "templates"
    if template_root.exists():
        for path in template_root.rglob("*"):
            if path.is_file() and path not in allowed_template_files:
                print(f"  FAIL: unexpected template file: {path.relative_to(root)}")
                fail += 1

    print("==> Summary")
    print(f"  PASS: {passed}")
    print(f"  FAIL: {fail}")
    return 1 if fail else 0
