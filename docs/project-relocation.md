# Project Physical Relocation

> Scope: move an existing project from outside `~/ghq/` (e.g. `~/work/<repo>`, `~/Documents/<repo>`) into `~/ghq/<host>/<owner>/<repo>/` while keeping AI session history, IDE state, and build environment functional.

## When to use

Use this playbook when `align this project` (the second Quick start prompt) discovers that the working tree is outside `~/ghq/`, or when any other audit flags repo path as a drift signal. It is **not** the right entry point for greenfield work (use the first Quick start prompt) or in-tree refactors (use `docs/realignment.md`).

Pre-conditions:

- All wanted changes are committed and pushed (uncommitted state is harder to roll back if a step fails).
- The target path `~/ghq/<host>/<owner>/<repo>/` does not already exist.

## Operation Model

Relocation is destructive (filesystem move + AI substrate rename) and follows AGENTS.md Operation Model: each Step is its own Propose → Confirm → Execute. Multi-step inside a single Step (e.g. removing several build caches in Step 1) shares one confirmation when the full list is presented up front.

```text
Phase 1 Discovery -> Phase 2 Plan -> Phase 3 Execute (per step) -> Phase 4 Verify
```

## Phase 1 — Discovery (read-only)

Record each result. The Brief shows them before any move.

```sh
OLD=<old-path>                        # e.g. $HOME/work/<repo>
NEW=$HOME/ghq/<host>/<owner>/<repo>

# 1. uncommitted state
git -C "$OLD" status --short

# 2. tracked file count (move scope)
git -C "$OLD" ls-files | wc -l

# 3. build / cache footprint (Step 1 candidates)
du -sh "$OLD"/{build,.xmake,.cache,target,dist,node_modules,.venv,__pycache__} 2>/dev/null

# 4. AI substrate hash
#    Claude Code stores per-project state under ~/.claude/projects/<dashed-abs-path>/
#    where <dashed-abs-path> is the absolute path with `/` replaced by `-`,
#    keeping the leading dash (`/Users/...` → `-Users-...`).
OLD_HASH=$(echo "$OLD" | tr / -)
NEW_HASH=$(echo "$NEW" | tr / -)
ls -la "$HOME/.claude/projects/$OLD_HASH" 2>/dev/null | head -1

# 5. target path must not exist
ls -la "$NEW" 2>/dev/null | head -1
```

If `$NEW` already exists, stop and resolve manually before proceeding.

## Phase 2 — Plan

The Brief lists the exact source / destination paths and identifies which AI substrate, IDE state, and build cache will be moved, reset, or left alone. User confirms the Brief before any Step in Phase 3.

## Phase 3 — Execute (per-step confirmation)

### Step 1: snapshot + cache cleanup

```sh
# 1.1 commit and push pending changes
git -C "$OLD" add -A
git -C "$OLD" commit -m "WIP: pre-relocation snapshot" || true
git -C "$OLD" push

# 1.2 drop path-encoded build artifacts (regenerate at $NEW)
rm -rf "$OLD"/{build,.xmake,.cache,target,dist,node_modules,.venv,__pycache__}
```

Compile databases (`compile_commands.json`) and other tools that bake absolute paths can regenerate from sources at `$NEW`; deleting them avoids stale references to `$OLD`.

### Step 2: physical move

```sh
mkdir -p "$(dirname "$NEW")"

# remove a stale symlink at the target if one exists
[ -L "$NEW" ] && rm "$NEW"

# atomic rename (same filesystem). cross-fs requires copy → verify → delete.
mv "$OLD" "$NEW"

# optional back-symlink so legacy shell history / IDE pointers still resolve
ln -s "$NEW" "$OLD"
```

### Step 3: AI substrate

`~/.claude/projects/<dashed-abs-path>/` is keyed on the absolute path. Without a rename, the next Claude Code session at `$NEW` starts with no history.

```sh
OLD_DIR="$HOME/.claude/projects/$OLD_HASH"
NEW_DIR="$HOME/.claude/projects/$NEW_HASH"

if [ -d "$OLD_DIR" ] && [ ! -d "$NEW_DIR" ]; then
    mv "$OLD_DIR" "$NEW_DIR"
elif [ -d "$OLD_DIR" ] && [ -d "$NEW_DIR" ]; then
    echo "Both $OLD_DIR and $NEW_DIR exist — merge manually."
fi
```

Codex / Cursor / Aider use different storage layouts; check each tool's docs before applying the same pattern. If a tool stores absolute paths inside its session files (rather than encoding them in the directory name), an in-place rename is sufficient but content rewrites may be needed.

### Step 4: dev environment re-init at `$NEW`

```sh
cd "$NEW"
direnv allow                                     # if .envrc is present
# project-specific re-init — run only the ones the project actually uses:
# python: uv sync   |  node: pnpm install  |  rust: cargo build
# nix:    nix flake check
```

### Step 5: IDE re-point (manual)

Most IDEs key workspace state on the absolute path. The cleanest path is to close the workspace at `$OLD` and re-open at `$NEW`. Rewriting IDE config files in place is risky and usually not worth the effort.

## Phase 4 — Verify

```sh
# git operates from the new path
git -C "$NEW" status
git -C "$NEW" log -1

# project's own check passes
cd "$NEW" && python -m ai_ops check       # or the project's check command

# AI history transferred
ls "$HOME/.claude/projects/$NEW_HASH" | head -3
```

If all four pass, the back-symlink at `$OLD` can be removed when ready (it is only there for legacy compatibility).

## Rollback

Within the same session, before adding further commits at `$NEW`:

```sh
[ -L "$OLD" ] && rm "$OLD"
mv "$NEW" "$OLD"
mv "$NEW_DIR" "$OLD_DIR"
```

After pushing more commits at `$NEW`, rollback is still the same `mv` (Git is path-agnostic) plus the AI substrate rename.

## Constraints

- Begin in committed state (Phase 3 Step 1.1). A dirty `mv` can leave the working tree inconsistent.
- Same-filesystem `mv` is atomic; cross-filesystem requires explicit copy → verify → delete.
- Each Step is its own approval. AI data substrate rename (Step 3) is explicitly listed in AGENTS.md §Operation Model.
- A pre-existing symlink at the target path must be removed before `mv` (macOS overwrites the symlink itself, not its target).

## See Also

- `AGENTS.md` §Workspace — `~/ghq/` is canonical
- `AGENTS.md` §Operation Model — Propose → Confirm → Execute
- `docs/realignment.md` — how `align this project` reaches this playbook
- `docs/project-addition-and-migration.md` — Tier promotion path moves
