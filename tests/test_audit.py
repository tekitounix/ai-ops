from pathlib import Path

from ai_ops.audit.nix import run_nix_audit
from ai_ops.audit.security import run_security_audit


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
    (tmp_path / "config.txt").write_text("AKIA0123456789ABCDEF\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_detects_private_key_header(tmp_path: Path) -> None:
    (tmp_path / "key.txt").write_text(
        "-----BEGIN RSA PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    assert run_security_audit(tmp_path) == 1


def test_security_audit_skips_test_fixtures_under_tests_dir(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "fixture.txt").write_text("AKIA0123456789ABCDEF\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 0


def test_security_audit_still_flags_secret_named_files_under_tests_dir(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / ".env").write_text("placeholder\n", encoding="utf-8")
    assert run_security_audit(tmp_path) == 1


def test_security_audit_skips_binary_files_without_crashing(tmp_path: Path) -> None:
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02\xff\xfe")
    assert run_security_audit(tmp_path) == 0
