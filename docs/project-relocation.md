# Project Physical Relocation

> Scope: move an existing project from outside `~/ghq/` (e.g. `~/work/<repo>`, `~/Documents/<repo>`) into `~/ghq/<host>/<owner>/<repo>/` while keeping AI session history, IDE workspace state, and build environment functional. **Full migration**: every reference to the old path is severed (no back-symlink, no baked-in cwd in chat history, no orphaned IDE storage).

This playbook covers three scenarios:

| Scenario | Entry signal |
|---|---|
| **Clean migration** | Project is outside `~/ghq/`, AI substrate lives at one canonical hash, no prior partial moves |
| **Recovery** | Filesystem move already happened, but AI substrate is split / partially rewritten / orphaned (see [Recovery](#recovery-partial-migration)) |
| **Preventive setup** | New project being placed under `~/ghq/...` from the start; only Phase 4-style invariants apply |

## When to use

Use this playbook when `align this project` (the second Quick start prompt) discovers that the working tree is outside `~/ghq/`, or when any other audit flags repo path as a drift signal. It is **not** the right entry point for greenfield work (use the first Quick start prompt) or in-tree refactors (use `docs/realignment.md`).

Pre-conditions:

- All wanted changes are committed and pushed.
- The target path `~/ghq/<host>/<owner>/<repo>/` does not already exist.
- A full backup of the AI substrate has been taken — Phase 3 rewrites session files in place.
- **The migration agent's cwd resolves to the canonical path you intend, not via a symlink.** See [In-session migration](#in-session-migration-self-protection) before running `mv` from inside an active session at `$OLD`.

## AI tool substrate reference

Each AI tool maps an absolute path to a per-project storage location. The mapping rule and whether the tool resolves `cwd` through symlinks (`realpath`) determine how robust the substrate is to relocation. Tool releases change these rules — check the table at the top of every migration and update as new versions ship.

| Tool | Storage root (macOS) | Path → key transform | Resolves symlinks? | Rewriteable in-place? |
|---|---|---|---|---|
| Claude Code (≥ 2.1.x) | `~/.claude/projects/` | `tr './' '-'` (both `/` and `.` → `-`) | No (records `cwd` as invoked) | Yes — `*.jsonl` is text |
| Claude Code (< 2.1.x) | `~/.claude/projects/` | `tr / -` (only `/` → `-`, `.` kept) | No | Yes — `*.jsonl` is text |
| Codex CLI | `~/.codex/` | per session/config files; mostly text | Yes (records realpath of cwd) | Yes — text files |
| Cursor | `~/Library/Application Support/Cursor/User/workspaceStorage/<md5>/` | md5 of `file://` workspace folder URI | No | **Mixed** — JSON yes, sqlite needs the tool's own export/import |
| VS Code (+ Copilot Chat) | `~/Library/Application Support/Code/User/workspaceStorage/<md5>/` | md5 of `file://` workspace folder URI | No | Mixed — `chatSessions/`, `chatEditingSessions/`, `GitHub.copilot-chat/` are JSON; `state.vscdb` (sqlite) is binary |
| Copilot (CLI) | `~/.copilot/` | per session text files | Varies by version | Yes |
| Aider | `~/.aider.*` and per-repo `.aider.chat.history.md` | absolute paths in chat log | No | Yes — markdown |

Linux substitutes `~/.config/` for `~/Library/Application Support/`; Windows (WSL) follows the Linux layout. **Each migration must enumerate every applicable storage root from this table and check it in Phase 1.**

## Operation Model

Relocation is destructive (filesystem move + AI substrate rename + content rewrite + IDE workspace storage migration) and follows AGENTS.md §Operation Model: each Step is its own Propose → Confirm → Execute. Multi-step inside a single Step shares one confirmation when the full list is presented up front.

```text
Phase 1 Discovery -> Phase 2 Plan -> Phase 3 Execute (per step) -> Phase 4 Verify
```

Recovery from a partial migration follows the same four phases but uses the [Recovery](#recovery-partial-migration) merge strategy instead of straight `mv` in Step 2.

## In-session migration: self-protection

If the AI agent driving the migration is itself running inside the project at `$OLD`, the agent's own cwd, hook scripts, and AI substrate can be invalidated mid-move.

**Default**: ask the user to open a fresh terminal whose cwd is **not** inside the project, then re-invoke the migration from that terminal. This is the safest path; almost every other concern below disappears.

If in-session migration is unavoidable, follow this orchestrated transition:

1. Phase 1 backup is taken first (all AI substrate, including the migration agent's own session if applicable).
2. Resolve symlinks before doing anything destructive:
   ```sh
   ACTUAL_CWD=$(realpath .)
   echo "agent realpath cwd: $ACTUAL_CWD"
   [ "$ACTUAL_CWD" = "$OLD" ] || echo "WARN: cwd resolves to $ACTUAL_CWD, not $OLD"
   ```
3. If the project ships hook scripts that read `$OLD`-keyed paths, set `AI_OPS_MIGRATION_IN_PROGRESS=1` and have those hooks short-circuit while the variable is set. ai-ops itself ships no hooks; this is a project-level convention.
4. Run Steps 1 → 5 normally. After Step 2's `mv` the agent's cwd becomes a stale path; switch with `cd "$NEW"` immediately.
5. Phase 4 verifies cwd, hooks, and substrate continuity (see check 7 below) before clearing `AI_OPS_MIGRATION_IN_PROGRESS`.

`align this project` agents should default to "ask the user to switch terminals" rather than attempting in-session migration.

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

# 4. realpath / symlink check — surfaces split-hash risk before it becomes drift
[ -L "$OLD" ] && echo "WARN: $OLD is a symlink → its target is the canonical path"
ACTUAL_OLD=$(realpath "$OLD")
[ "$ACTUAL_OLD" = "$OLD" ] || echo "INFO: working-tree canonical path is $ACTUAL_OLD"
```

```sh
# 5. Claude Code substrate hash candidates (cover the v2 / v1 sanitize drift).
#    v2 (≥ 2.1.x): both `/` and `.` are replaced with `-`
#    v1 (< 2.1.x): only `/` is replaced; `.` stays
HASH_V2=$(echo "$OLD" | tr './' '-')
HASH_V1=$(echo "$OLD" | tr / -)
NEW_HASH=$(echo "$NEW"  | tr './' '-')

for h in "$HASH_V2" "$HASH_V1"; do
    [ "$h" = "$HASH_V2" ] || [ "$h" = "$HASH_V1" ] || continue
    [ -d "$HOME/.claude/projects/$h" ] && \
        echo "claude substrate hit: $HOME/.claude/projects/$h"
done

# 6. content path-mention counts across every text-based AI substrate
grep -rlI -F "$OLD" "$HOME/.claude/projects" 2>/dev/null | wc -l
grep -rlI -F "$OLD" "$HOME/.codex" "$HOME/.copilot" "$HOME/.aider" 2>/dev/null | wc -l
```

```sh
# 7. IDE workspace storage hashes (md5 of the folder URI). Search the
#    workspace.json files instead of trying to recompute md5 — they record
#    the URI exactly as the IDE stored it.
case "$(uname -s)" in
    Darwin) IDE_BASE="$HOME/Library/Application Support" ;;
    *)      IDE_BASE="$HOME/.config" ;;
esac
for ide in Code Cursor; do
    base="$IDE_BASE/$ide/User/workspaceStorage"
    [ -d "$base" ] || continue
    grep -lF "\"file://$OLD\"" "$base"/*/workspace.json 2>/dev/null | while read -r ws; do
        echo "$ide workspace storage: $(dirname "$ws")"
    done
done

# 8. target path must not exist
ls -la "$NEW" 2>/dev/null | head -1

# 9. mandatory backup (AI substrate + IDE workspace storage)
BACKUP_ROOT="$HOME/.ai-ops-relocation-backup/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_ROOT"
cp -a "$HOME/.claude/projects" "$BACKUP_ROOT/claude-projects" 2>/dev/null || true
for ide in Code Cursor; do
    base="$IDE_BASE/$ide/User/workspaceStorage"
    [ -d "$base" ] && grep -lF "\"file://$OLD\"" "$base"/*/workspace.json 2>/dev/null | while read -r ws; do
        cp -a "$(dirname "$ws")" "$BACKUP_ROOT/$ide-$(basename "$(dirname "$ws")")" 2>/dev/null
    done
done
echo "AI / IDE substrate backup: $BACKUP_ROOT"
```

If `$NEW` already exists, stop and resolve manually. If multiple Claude hash candidates hit (v1 and v2 both have a directory), the project is in a split state — go to [Recovery](#recovery-partial-migration) before running Phase 3.

## Phase 2 — Plan

The Brief lists the exact source / destination paths and identifies which AI substrate, IDE workspace storage, and build cache will be moved, rewritten, reset, or left alone. The Brief states **explicitly that no back-symlink will be left at `$OLD`** (see Step 2). User confirms the Brief before any Step in Phase 3.

## Phase 3 — Execute (per-step confirmation)

### Step 1: snapshot + cache cleanup

```sh
git -C "$OLD" add -A
git -C "$OLD" commit -m "WIP: pre-relocation snapshot" || true
git -C "$OLD" push

rm -rf "$OLD"/{build,.xmake,.cache,target,dist,node_modules,.venv,__pycache__}
```

Compile databases (`compile_commands.json`) and other tools that bake absolute paths regenerate from sources at `$NEW`; deleting them avoids stale references to `$OLD`.

### Step 2: physical move (NO back-symlink for full migration)

```sh
mkdir -p "$(dirname "$NEW")"
[ -L "$NEW" ] && rm "$NEW"
mv "$OLD" "$NEW"
```

**Do NOT create a back-symlink at `$OLD`.** It is an anti-pattern for full migration:

```sh
# ✗ ANTI-PATTERN — do NOT do this:
# ln -s "$NEW" "$OLD"
```

Reasons the back-symlink hurts:

- IDE / shell history resolves `$OLD` and the user keeps working there unaware. The next Claude Code session records `cwd: $OLD` again, undoing Step 3's rewrite.
- AI tools that do not realpath-resolve `cwd` (Claude Code, VS Code) will re-create a separate substrate at the symlinked path → split-hash drift.
- "Single source of truth" is lost; two paths point at the same project and only one is canonical.
- Legacy scripts or shell aliases that still reference `$OLD` should be updated explicitly to `$NEW`, not papered over with a symlink.

The narrow exception is a short transition window where IDE workspace migration is the only thing left and the symlink will be removed the moment Phase 4 confirms the IDE points at `$NEW`. State the removal step and timing in the Brief; do not leave a symlink behind by default.

### Step 3: AI substrate (rename + content rewrite, including v1/v2 hash merge)

`~/.claude/projects/<hash>/` is keyed on the absolute path; each `.jsonl` also bakes the path into `cwd`, file-resource URIs, and tool-result fields — typically thousands of mentions per active session. Renaming the directory alone leaves the next session pointed at `$OLD`. Both rename and content rewrite are required; if v1 and v2 hash directories both exist, they must merge into the new hash.

```sh
NEW_DIR="$HOME/.claude/projects/$NEW_HASH"

# 3.1 rename / merge old hash directories into the new-hash directory
mkdir -p "$NEW_DIR"
for h in "$HASH_V2" "$HASH_V1"; do
    src="$HOME/.claude/projects/$h"
    [ -d "$src" ] && [ "$src" != "$NEW_DIR" ] || continue
    cp -an "$src"/* "$NEW_DIR/" 2>/dev/null || true
    # Old-hash dir is preserved for rollback; user removes it after Phase 4.
done
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
# 3.3 other text-based AI substrate
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

`grep -rlI` skips binary files (the `I` flag). Tools whose state lives in a binary store (sqlite, leveldb, etc.) need their own export/import — see Step 5b for VS Code's `state.vscdb` and Cursor's sqlite stores.

### Step 4: dev environment re-init at `$NEW`

```sh
cd "$NEW"
direnv allow                                     # if .envrc is present
# project-specific re-init — only what the project actually uses:
# python: uv sync   |  node: pnpm install  |  rust: cargo build
# nix:    nix flake check
```

### Step 5a: IDE workspace storage — identify

```sh
case "$(uname -s)" in
    Darwin) IDE_BASE="$HOME/Library/Application Support" ;;
    *)      IDE_BASE="$HOME/.config" ;;
esac

# Close the IDE first — write contention against `state.vscdb` corrupts the file.
echo "Close VS Code / Cursor before continuing. Press enter when done."
read -r _

for ide in Code Cursor; do
    base="$IDE_BASE/$ide/User/workspaceStorage"
    [ -d "$base" ] || continue
    OLD_WS=$(grep -lF "\"file://$OLD\"" "$base"/*/workspace.json 2>/dev/null | head -1)
    NEW_WS=$(grep -lF "\"file://$NEW\"" "$base"/*/workspace.json 2>/dev/null | head -1)
    echo "$ide: OLD=$OLD_WS  NEW=$NEW_WS"
done
```

If `NEW_WS` is empty for an IDE you intend to use, opening the IDE once at `$NEW` creates the folder. Re-run Step 5a after that.

### Step 5b: IDE workspace storage — copy chat / extension state

For each IDE, copy the JSON-based agent state from the OLD workspace storage to the NEW one. **Do not overwrite `state.vscdb` (sqlite)** — keep OLD's as the backup, let NEW's continue from a clean state, and rely on Step 3.3 for any text duplicates.

```sh
for ide in Code Cursor; do
    base="$IDE_BASE/$ide/User/workspaceStorage"
    OLD_WS=$(grep -lF "\"file://$OLD\"" "$base"/*/workspace.json 2>/dev/null | head -1)
    NEW_WS=$(grep -lF "\"file://$NEW\"" "$base"/*/workspace.json 2>/dev/null | head -1)
    [ -n "$OLD_WS" ] && [ -n "$NEW_WS" ] || continue
    OLD_DIR=$(dirname "$OLD_WS")
    NEW_DIR=$(dirname "$NEW_WS")
    for sub in chatSessions chatEditingSessions GitHub.copilot-chat; do
        [ -d "$OLD_DIR/$sub" ] || continue
        rsync -a "$OLD_DIR/$sub/" "$NEW_DIR/$sub/"
        echo "$ide: copied $sub from $OLD_DIR to $NEW_DIR"
    done
done
```

After Phase 4 verifies the chat history is visible in the IDE, you may delete the OLD workspace storage directories listed above — but only with explicit user approval.

## Phase 4 — Verify (structure AND content)

```sh
# 1. git operates from the new path
git -C "$NEW" status
git -C "$NEW" log -1

# 2. project's own check passes
cd "$NEW" && python -m ai_ops check

# 3. AI substrate directory exists at the new hash
ls "$HOME/.claude/projects/$NEW_HASH" | head -3

# 4. content-level rewrite is complete — every count below MUST be 0
grep -rlI -F "$OLD" "$HOME/.claude/projects" 2>/dev/null | wc -l
grep -rlI -F "$OLD" "$HOME/.codex" "$HOME/.copilot" "$HOME/.aider" 2>/dev/null | wc -l

# 5. no split-hash directories — only the new-hash directory should remain
#    populated; old-hash dirs are either gone or empty after Step 3.1 merge.
for h in "$HASH_V2" "$HASH_V1"; do
    [ "$h" = "$NEW_HASH" ] && continue
    src="$HOME/.claude/projects/$h"
    if [ -d "$src" ]; then
        count=$(find "$src" -type f | wc -l | tr -d ' ')
        [ "$count" = "0" ] || echo "FAIL: $src still has $count file(s); merge missed?"
    fi
done

# 6. IDE workspace storage points at NEW and chatSessions are visible
for ide in Code Cursor; do
    base="$IDE_BASE/$ide/User/workspaceStorage"
    [ -d "$base" ] || continue
    NEW_WS=$(grep -lF "\"file://$NEW\"" "$base"/*/workspace.json 2>/dev/null | head -1)
    [ -n "$NEW_WS" ] || { echo "INFO: $ide has no workspace at $NEW yet"; continue; }
    NEW_DIR=$(dirname "$NEW_WS")
    [ -d "$NEW_DIR/chatSessions" ] && echo "$ide chat sessions: $(ls "$NEW_DIR/chatSessions" | wc -l)"
done

# 7. no remnants of $OLD on the filesystem (full-migration invariant)
[ -e "$OLD" ] && echo "FAIL: $OLD still exists (symlink or directory)"

# 8. in-session: agent cwd resolves to $NEW
cd "$NEW" && [ "$(realpath .)" = "$NEW" ] || echo "FAIL: cwd does not realpath to $NEW"
```

A non-zero count from check 4 means Step 3.2 / 3.3 missed a file or another AI tool stores binary state; investigate before declaring success. A surviving entity at check 7 means Step 2's anti-pattern slipped back in. Failures at check 5 indicate a split between the v1 and v2 sanitize hashes that Step 3.1 did not merge.

## Recovery (partial migration)

Use this section when Phase 1 Discovery shows a project already in a partially-migrated state — typical signals:

- Filesystem move completed (`$NEW` exists) but `$OLD` is still present (symlink or dir fragment).
- Multiple Claude hash directories hit (`$HASH_V1` and `$HASH_V2` both populated, or `$NEW_HASH` exists alongside `$HASH_V2`).
- `grep -rlI -F "$OLD"` count is non-zero in any AI substrate even though the directory rename happened.
- Same session UUID file appears in more than one hash directory.
- IDE workspace storage exists at both OLD and NEW hashes for the same IDE.

Recovery uses the same four phases but replaces Step 2's straight `mv` with a **merge**:

1. **Phase 1 Discovery (recovery mode)**: re-run Phase 1 in full so multi-hash hits and content counts are captured under the recovery branch. Take a fresh backup under `~/.ai-ops-relocation-backup/recovery-$(date +%Y%m%d-%H%M%S)/` — recovery's mutations are different from a clean migration's, so the backup must be distinct.

2. **Phase 2 Plan**: the Brief explicitly enumerates every hash directory found, every fragment in `$OLD`, and the merge map per session UUID. Mark each entry as `keep`, `merge`, or `discard`.

3. **Step 1 (Recovery)**: clean up `$OLD` fragment if present. If `$OLD` is a back-symlink, remove it (no `mv` needed; `$NEW` already holds the data).

4. **Step 2 (Recovery — merge instead of move)**: for each session UUID found in more than one hash directory, choose the canonical copy (largest size or newest mtime is a sane default), keep it under `$NEW_HASH/<uuid>.jsonl`, and rename siblings to `<uuid>-fragment-<source-hash>.jsonl` so the user can audit them later. Unique files copy directly into `$NEW_HASH/`.

5. **Step 3 (Recovery)**: run Step 3.2 / 3.3 of the main flow against the merged `$NEW_DIR` and every text-based AI substrate. Binary stores (sqlite, leveldb) are left as-is; the OLD copy becomes the rollback artifact, the NEW copy continues fresh.

6. **Step 4 / 5**: identical to the main flow — re-init dev environment, copy IDE chat state from any surviving OLD workspace storage to NEW.

7. **Phase 4 (Recovery)**: run all eight verifications. The same pass criteria apply: `grep -rlI -F "$OLD"` must be 0, no split hash dirs may carry data, `$OLD` must not exist as a path or symlink. Additionally confirm no `*-fragment-*.jsonl` survived without a corresponding canonical sibling.

8. **Cleanup (with user approval)**: only after Phase 4 passes and the user reviews the `*-fragment-*.jsonl` set, delete the old hash directories. Recovery never deletes anything destructively without the user signing off — original substrate is the rollback.

## Rollback

Step 3 mutated AI substrate in place; rollback restores from the Phase 1 backup.

```sh
# directory move
mv "$NEW" "$OLD"
# AI substrate restore (use the Phase 1 backup; do NOT just rename)
rm -rf "$HOME/.claude/projects/$NEW_HASH"
[ -d "$BACKUP_ROOT/claude-projects" ] && cp -a "$BACKUP_ROOT/claude-projects" "$HOME/.claude/projects"
# IDE workspace storage restore: revert each backed-up <hash> directory
for backup in "$BACKUP_ROOT"/Code-* "$BACKUP_ROOT"/Cursor-*; do
    [ -d "$backup" ] || continue
    name=$(basename "$backup")           # e.g. Code-02b51147...
    ide=${name%%-*}                      # Code | Cursor
    hash=${name#*-}                      # 02b51147...
    rm -rf "$IDE_BASE/$ide/User/workspaceStorage/$hash"
    cp -a "$backup" "$IDE_BASE/$ide/User/workspaceStorage/$hash"
done
```

Rollback for other AI tools is equivalent: restore from the backup made before Step 3.3. Git itself is path-agnostic; no remote operations are needed for rollback.

## Constraints

- Begin in committed state. A dirty `mv` can leave the working tree inconsistent.
- Same-filesystem `mv` is atomic; cross-filesystem requires explicit copy → verify → delete.
- Each Step is its own approval. AI data substrate rename + content rewrite (Step 3) and IDE workspace storage migration (Step 5) are explicitly listed in AGENTS.md §Operation Model.
- A pre-existing symlink at the target path must be removed before `mv` (macOS overwrites the symlink itself, not its target).
- **No back-symlink at `$OLD`** for full migration (Step 2). The narrow transition exception is the only acceptable variant and must come with an explicit removal step in the Brief.
- **Content rewrite is mandatory** when AI session storage is text-based (Step 3.2 / 3.3). Directory rename alone is not full migration.
- **Phase 4 grep must report 0** for every storage location with text-based session data. Non-zero means a missed location.
- **Hash candidates must enumerate v1 + v2 sanitize rules** (and any future variants). A single-rule Discovery silently misses split-hash drift.
- **In-session migration prefers terminal restart**; only orchestrate inline transition when terminal restart is impossible.
- **Recovery's destructive cleanup requires user approval per fragment.** Original substrate is the rollback artifact.

## See Also

- `AGENTS.md` §Workspace — `~/ghq/` is canonical
- `AGENTS.md` §Operation Model — Propose → Confirm → Execute
- `docs/realignment.md` — how `align this project` reaches this playbook
- `docs/project-addition-and-migration.md` — Tier promotion path moves
