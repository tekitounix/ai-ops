# Project Physical Relocation

> Scope: move an existing project from outside `~/ghq/` (e.g. `~/work/<repo>`, `~/Documents/<repo>`) into `~/ghq/<host>/<owner>/<repo>/` while keeping AI session history, IDE state, and build environment functional. **Full migration**: every reference to the old path is severed (no back-symlink, no baked-in cwd in chat history).

## When to use

Use this playbook when `align this project` (the second Quick start prompt) discovers that the working tree is outside `~/ghq/`, or when any other audit flags repo path as a drift signal. It is **not** the right entry point for greenfield work (use the first Quick start prompt) or in-tree refactors (use `docs/realignment.md`).

Pre-conditions:

- All wanted changes are committed and pushed (uncommitted state is harder to roll back if a step fails).
- The target path `~/ghq/<host>/<owner>/<repo>/` does not already exist.
- A full backup of the AI substrate (`~/.claude/projects/<dashed-abs-path>/` etc.) has been taken — Phase 3 rewrites session files in place.

## Operation Model

Relocation is destructive (filesystem move + AI substrate rename + content rewrite) and follows AGENTS.md §Operation Model: each Step is its own Propose → Confirm → Execute. Multi-step inside a single Step (e.g. removing several build caches in Step 1) shares one confirmation when the full list is presented up front.

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

# 4. AI substrate hash + path-mention count
#    Claude Code stores per-project state under ~/.claude/projects/<dashed-abs-path>/
#    where <dashed-abs-path> is the absolute path with `/` replaced by `-`,
#    keeping the leading dash (`/Users/...` → `-Users-...`).
OLD_HASH=$(echo "$OLD" | tr / -)
NEW_HASH=$(echo "$NEW" | tr / -)
ls -la "$HOME/.claude/projects/$OLD_HASH" 2>/dev/null | head -1

# Count how many session files mention $OLD inside their bodies. A `mv` of
# the directory does NOT fix these — Step 3 rewrites them in place.
grep -rl --include="*.jsonl" -F "$OLD" "$HOME/.claude/projects/$OLD_HASH" 2>/dev/null | wc -l
grep -rl -F "$OLD" "$HOME/.codex" "$HOME/.cursor" "$HOME/.copilot" "$HOME/.aider" 2>/dev/null | wc -l

# 5. target path must not exist
ls -la "$NEW" 2>/dev/null | head -1

# 6. AI substrate backup (mandatory before Phase 3 rewrites)
BACKUP_ROOT="$HOME/.ai-ops-relocation-backup/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_ROOT"
[ -d "$HOME/.claude/projects/$OLD_HASH" ] && cp -a "$HOME/.claude/projects/$OLD_HASH" "$BACKUP_ROOT/claude-projects"
echo "AI substrate backup: $BACKUP_ROOT"
```

If `$NEW` already exists, stop and resolve manually before proceeding. Discovery is read-only except for the backup directory under `~/.ai-ops-relocation-backup/`.

## Phase 2 — Plan

The Brief lists the exact source / destination paths and identifies which AI substrate, IDE state, and build cache will be moved, rewritten, reset, or left alone. The Brief states **explicitly that no back-symlink will be left at `$OLD`** (see Step 2). User confirms the Brief before any Step in Phase 3.

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

### Step 2: physical move (NO back-symlink for full migration)

```sh
mkdir -p "$(dirname "$NEW")"

# remove a stale symlink at the target if one exists
[ -L "$NEW" ] && rm "$NEW"

# atomic rename (same filesystem). cross-fs requires copy → verify → delete.
mv "$OLD" "$NEW"
```

**Do NOT create a back-symlink at `$OLD`.** It is an anti-pattern for full migration:

```sh
# ✗ ANTI-PATTERN — do NOT do this:
# ln -s "$NEW" "$OLD"
```

Reasons the back-symlink hurts:

- IDE / shell history resolves `$OLD` and the user keeps working there unaware. The next Claude Code session records `cwd: $OLD` again, undoing Step 3's rewrite.
- "Single source of truth" is lost; two paths point at the same project and only one is canonical.
- Legacy scripts or shell aliases that still reference `$OLD` should be updated explicitly to `$NEW`, not papered over with a symlink.

The narrow exception is a short transition window where IDE workspace migration is the only thing left and the symlink will be removed the moment Phase 4 confirms the IDE points at `$NEW`. State the removal step and timing in the Brief; do not leave a symlink behind by default.

### Step 3: AI substrate (directory rename + content rewrite)

`~/.claude/projects/<dashed-abs-path>/` is keyed on the absolute path **as a directory name**, but each `.jsonl` session file also bakes the path into `cwd`, file-resource URIs, and tool-result fields — typically thousands of mentions per active session. Renaming the directory alone leaves the next session pointed at `$OLD`. Both the directory rename and the content rewrite are required.

```sh
OLD_DIR="$HOME/.claude/projects/$OLD_HASH"
NEW_DIR="$HOME/.claude/projects/$NEW_HASH"

# 3.1 directory rename
if [ -d "$OLD_DIR" ] && [ ! -d "$NEW_DIR" ]; then
    mv "$OLD_DIR" "$NEW_DIR"
elif [ -d "$OLD_DIR" ] && [ -d "$NEW_DIR" ]; then
    echo "Both $OLD_DIR and $NEW_DIR exist — merge manually before continuing." >&2
    exit 1
fi
```

```sh
# 3.2 content rewrite — literal replacement, regex-safe even if $OLD or $NEW
#     contain `.`, `[`, `\`, `&`, etc. Backup was taken in Phase 1.
python3 - "$OLD" "$NEW" "$NEW_DIR" <<'PY'
import glob, sys
old, new, target = sys.argv[1], sys.argv[2], sys.argv[3]
n_files = n_replacements = 0
for path in sorted(glob.glob(f"{target}/**/*.jsonl", recursive=True)):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if old in text:
        n_files += 1
        n_replacements += text.count(old)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, new))
print(f"rewrote {n_replacements} occurrence(s) across {n_files} file(s) in {target}")
PY
```

```sh
# 3.3 other AI tools — Codex / Cursor / Copilot / Aider
#     For each tool whose storage exists, find text files referencing $OLD
#     and rewrite them. Binary stores (e.g. SQLite-backed Cursor state)
#     need a tool-specific procedure; check each tool's docs.
for storage in "$HOME/.codex" "$HOME/.cursor" "$HOME/.copilot" "$HOME/.aider"; do
    [ -d "$storage" ] || continue
    files=$(grep -rlI -F "$OLD" "$storage" 2>/dev/null || true)
    [ -z "$files" ] && continue
    python3 - "$OLD" "$NEW" $files <<'PY'
import sys
old, new = sys.argv[1], sys.argv[2]
for path in sys.argv[3:]:
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if old in text:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, new))
        print(f"rewrote {path}")
PY
done
```

`grep -rlI` skips binary files automatically (the `I` flag). For tools whose state lives in a binary store (SQLite, leveldb, etc.) the rewrite must use that tool's own export/import or in-place schema migration — there is no safe shell-level fallback.

### Step 4: dev environment re-init at `$NEW`

```sh
cd "$NEW"
direnv allow                                     # if .envrc is present
# project-specific re-init — run only the ones the project actually uses:
# python: uv sync   |  node: pnpm install  |  rust: cargo build
# nix:    nix flake check
```

### Step 5: IDE re-point (manual)

Close any workspace pointing at `$OLD` in your IDE and re-open at `$NEW`. IDE workspace state is keyed on the absolute path; rewriting IDE config files in place is risky and usually not worth the effort. Confirm the IDE no longer references `$OLD` before considering Phase 4 verification complete.

## Phase 4 — Verify (structure AND content)

```sh
# 1. git operates from the new path
git -C "$NEW" status
git -C "$NEW" log -1

# 2. project's own check passes
cd "$NEW" && python -m ai_ops check       # or the project's check command

# 3. AI substrate directory exists at the new hash
ls "$HOME/.claude/projects/$NEW_HASH" | head -3

# 4. content-level rewrite is complete — every count below MUST be 0
grep -rlI -F "$OLD" "$HOME/.claude/projects/$NEW_HASH" 2>/dev/null | wc -l
grep -rlI -F "$OLD" "$HOME/.codex" "$HOME/.cursor" "$HOME/.copilot" "$HOME/.aider" 2>/dev/null | wc -l

# 5. no back-symlink at the old path (full migration invariant)
[ -e "$OLD" ] && echo "FAIL: $OLD still exists (symlink or directory) — full migration requires it gone"

# 6. IDE re-point — manual confirmation that no workspace at $OLD is open
```

A non-zero count from check 4 means Step 3.2 / 3.3 missed a file or another AI tool stores binary state; investigate before declaring success. A surviving entity at check 5 means Step 2's anti-pattern slipped back in.

## Rollback

Step 3 mutated the AI substrate in place; rollback restores from the backup taken in Phase 1.

```sh
# directory move
mv "$NEW" "$OLD"
# AI substrate restore (use the Phase 1 backup; do NOT just rename)
rm -rf "$NEW_DIR"
[ -d "$BACKUP_ROOT/claude-projects" ] && cp -a "$BACKUP_ROOT/claude-projects" "$OLD_DIR"
```

Rollback for other AI tools is equivalent: restore from the backup made before Step 3.3. Git itself is path-agnostic; no remote operations are needed for rollback.

## Constraints

- Begin in committed state (Phase 3 Step 1.1). A dirty `mv` can leave the working tree inconsistent.
- Same-filesystem `mv` is atomic; cross-filesystem requires explicit copy → verify → delete.
- Each Step is its own approval. AI data substrate rename + content rewrite (Step 3) is explicitly listed in AGENTS.md §Operation Model.
- A pre-existing symlink at the target path must be removed before `mv` (macOS overwrites the symlink itself, not its target).
- **No back-symlink at `$OLD`** for full migration (Step 2). The narrow transition exception is the only acceptable variant and must come with an explicit removal step in the Brief.
- **Content rewrite is mandatory** when AI session storage is text-based (Step 3.2 / 3.3). Directory rename alone is not full migration.
- **Phase 4 grep must report 0** for every storage location with text-based session data. Non-zero means a missed location.

## See Also

- `AGENTS.md` §Workspace — `~/ghq/` is canonical
- `AGENTS.md` §Operation Model — Propose → Confirm → Execute
- `docs/realignment.md` — how `align this project` reaches this playbook
- `docs/project-addition-and-migration.md` — Tier promotion path moves
