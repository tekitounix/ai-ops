# ADR 0007: Python canonical CLI

> Status: Accepted
> Date: 2026-04-27

## Context

ai-ops の正規実装は OS-specific な shell semantics に依存してはならない。Bash / PowerShell / CMD を adapter として並べる構成は command surface を統一できても、Windows 上で Git Bash や WSL を要求する点で本質的なポータビリティを欠く。

## Decision

`ai-ops` の canonical 実装は Python CLI とする。Shell / PowerShell / CMD の launcher は target design に含めない。user-facing command と Nix apps は Python CLI を直接指す。

実装構成:

```text
ai_ops/
  __main__.py
  cli.py
  config.py
  models.py
  paths.py
  process.py
  agents/
    base.py           # Agent protocol
    prompt_only.py    # 内蔵 fallback
    subprocess.py     # 外部 AI CLI 呼び出し
  lifecycle/
    project.py
    migration.py
    prompts.py
  audit/
    lifecycle.py
    nix.py
    security.py
  checks/
    runner.py         # ai-ops check entrypoint
```

User-facing command surface:

```sh
ai-ops new <name> --purpose "<one-line-purpose>"
ai-ops migrate <path>
ai-ops audit {lifecycle,nix,security}
ai-ops check
```

`new` / `migrate` の共通オプション:

- `--agent <name>` — 設定済み default agent を上書き
- `--agent prompt-only` — AI CLI を呼ばずに prompt と brief draft だけ出力
- `--dry-run` — agent を呼ばずに最終 prompt と brief draft を表示
- `--output <path>` — brief draft / migration prompt をファイルに書き出し
- `--interactive` — 必要項目を対話で入力

## Agent configuration

Default agent は config で決め、コードにハードコードしない。

優先順位:

1. CLI flag: `--agent <name>`
2. repo-local `ai-ops.toml`
3. user-local `$XDG_CONFIG_HOME/ai-ops/config.toml` (Windows: `%APPDATA%\ai-ops\config.toml`)
4. built-in default: `prompt-only`

最小設定:

```toml
[agent]
default = "prompt-only"

[agents.claude]
command = ["claude", "-p", "--no-session-persistence", "--tools", ""]

[agents.codex]
command = ["codex", "exec", "-m", "gpt-5.2", "-c", 'model_reasoning_effort="high"', "--sandbox", "read-only", "-"]
```

agent adapter は prompt を stdin で渡し、stdout を relay するだけ。CLI 自身が project を機械的に作成・移行することはない (理想形は project-specific であるため)。

## Consequences

Positive:

- cross-platform 挙動を Python 一本で実装。Windows でも Git Bash / WSL を要求しない。
- AI invocation を config で切り替え・テストできる。
- `prompt-only` で AI CLI 未インストール環境でも lifecycle を回せる。
- Nix は再現性 wrapper として残るが、primary runtime ではない。

Negative:

- Python packaging、subprocess の挙動、TOML パースが harness の表面に乗る。

## Verification

```sh
python -m ai_ops --help
python -m ai_ops new --help
python -m ai_ops migrate --help
python -m ai_ops check
python -m ai_ops audit lifecycle
python -m pytest
nix flake check
```

CI matrix:

- Python: Ubuntu / macOS / Windows
- Nix: Ubuntu / macOS

## Related

- ADR 0002: portability first
- ADR 0005: Nix optional reproducibility layer
- ADR 0006: AI-first project lifecycle
- `docs/ai-first-lifecycle.md`
