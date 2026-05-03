# ADR INDEX

各 ADR を 1 行 summary で navigate するための index。詳細は各リンクを参照。

| # | タイトル | 1 行 summary |
|---|---|---|
| [0001](0001-agents-md-as-primary.md) | AGENTS.md を AI ルールの source of truth にする | AI 向け契約は `AGENTS.md` 1 ファイルに集約し、他のドキュメントは pointer に徹する |
| [0002](0002-portability-first.md) | ポータビリティ優先 | OS / shell に依存せず、必要ツールは `bootstrap` で使用者承認の上で install する |
| [0003](0003-deletion-policy.md) | 削除は Git 履歴と復旧可能性を優先する | tracked file は `git rm` 経由で削除、`rm -rf` や archive 移動を避ける |
| [0004](0004-secrets-management.md) | 秘匿情報を AI 文脈に入れない | secret 値は読まず、ファイル名 / pattern だけで Risk として扱う |
| [0005](0005-nix-optional-reproducibility-layer.md) | Nix as default reproducibility layer | Stage A/B/C rubric で AI が adoption level を機械判定 (default-required) |
| [0006](0006-ai-first-project-lifecycle.md) | AI-first project lifecycle | Intake → Discovery → Brief → Confirm → Execute → Verify → Adopt の正本フロー |
| [0007](0007-python-canonical-cli.md) | Python canonical CLI | shell スクリプトを廃止し、`ai-ops` Python CLI を唯一の正本実装にする |
| [0008](0008-plan-persistence.md) | Execution plan persistence | 非自明な作業は `docs/plans/<slug>/plan.md` に永続化、必須 section schema を canonical 化 |
| [0009](0009-git-workflow-tiers.md) | Git workflow tiers for managed projects | 各管理対象プロジェクトに Tier A/B/C/D を宣言させ、tier 別運用規範を audit が検出 |
| [0010](0010-worktree-workflow.md) | Worktree-based parallel work and plan binding | 1 plan : 1 branch : 1 worktree、sibling 配置、3〜5 worktree/repo 上限 |
| [0011](0011-github-native-operation.md) | GitHub-native ecosystem operation | Issues + sub-issues + Projects v2 + Rulesets + reusable workflows で運用基盤を構築 |
| [0012](0012-pr-ai-review.md) | PR 自動レビュー (二層構成 + AI エージェント主体ワークフロー) | Copilot Code Review + `ai-ops review-pr` の二層、AI エージェントが規定ワークフローを自律実行 |
