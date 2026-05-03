# プロジェクトの物理 relocation

> マスター運用ガイド: [`operation.md`](operation.md)。これは relocate sub-flow の deep-dive (特殊: セッション履歴を保ちながらの物理パス移行)。
>
> スコープ: `~/ghq/` 外 (例: `~/work/<repo>`、`~/Documents/<repo>`) の既存プロジェクトを `~/ghq/<host>/<owner>/<repo>/` 配下へ移し、AI セッション履歴、IDE ワークスペース状態、ビルド環境を機能させ続ける。**完全移行**: 旧 path への参照をすべて切る (back-symlink 無し、チャット履歴に焼き付いた cwd 無し、孤立した IDE ストレージ無し)。
>
> 状態: 3-way split (`HASH_OLD` symlink fragment + `HASH_NEW_V1` ドット保持 sanitize + `HASH_NEW_V2` ドット置換 sanitize) に対する end-to-end 復旧を検証済み — Claude セッション merge、VS Code チャット状態 rsync、Phase 4 の grep-zero 基準すべて合格。In-session 経路 (`AI_OPS_MIGRATION_IN_PROGRESS=1`) は dry-run のみで運用検証済み。実運用の signal が出たらここに記録すること。

この playbook は 3 シナリオを扱う。

| シナリオ | 入口 signal |
|---|---|
| **Clean migration** | プロジェクトが `~/ghq/` 外、AI substrate は単一の canonical hash、過去の partial 移動なし |
| **Recovery** | ファイルシステム移動は完了したが、AI substrate が分裂 / 部分書換 / 孤立 (下記 [Recovery](#recovery-partial-migration) 参照) |
| **Preventive setup** | 新規プロジェクトを最初から `~/ghq/...` 配下に置く。Phase 4 相当の invariant のみ適用 |

## 使うべきとき

`align this project` (Quick start プロンプト 2 番目) が「作業ツリーが `~/ghq/` 外」を発見したとき、または他の監査が repo path を drift signal としてフラグ付けしたときに使う。greenfield 作業 (Quick start 1 番目) や in-tree refactor (`docs/realignment.md`) には使わない。

事前条件:

- 残したい変更はすべて commit と push 済み。
- 目的地 `~/ghq/<host>/<owner>/<repo>/` がまだ存在しない。
- AI substrate のフルバックアップを取得済み — Phase 3 はセッションファイルを in-place で書き換える。
- **移行エージェントの cwd が、symlink 経由ではなく意図する canonical path に解決されること。** $OLD で active なセッション内から `mv` を走らせる場合は事前に [In-session migration](#in-session-migration-self-protection) を読む。

## AI ツール substrate リファレンス

各 AI ツールは絶対 path をプロジェクトごとのストレージにマップする。マッピング規則と、ツールが `cwd` を symlink 経由で解決するか (`realpath`) が、relocation に対する substrate の堅牢性を決める。ツールリリースで規則が変わるので、毎回の移行時に表頭をチェックし、新版が出たら更新する。

| ツール | ストレージ root (macOS) | Path → key 変換 | symlink 解決? | in-place 書換可? |
|---|---|---|---|---|
| Claude Code (≥ 2.1.x) | `~/.claude/projects/` | `tr './' '-'` (`/` も `.` も `-` へ) | しない (起動時の `cwd` を記録) | はい — `*.jsonl` はテキスト |
| Claude Code (< 2.1.x) | `~/.claude/projects/` | `tr / -` (`/` のみ。`.` は保持) | しない | はい — `*.jsonl` はテキスト |
| Codex CLI | `~/.codex/` | session/config ファイル単位。ほぼテキスト | する (cwd の realpath を記録) | はい — テキストファイル |
| Cursor | `~/Library/Application Support/Cursor/User/workspaceStorage/<md5>/` | `file://` ワークスペースフォルダ URI の md5 | しない | **混在** — JSON はい、sqlite はツール独自の export/import が必要 |
| VS Code (+ Copilot Chat) | `~/Library/Application Support/Code/User/workspaceStorage/<md5>/` | `file://` ワークスペースフォルダ URI の md5 | しない | 混在 — `chatSessions/`、`chatEditingSessions/`、`GitHub.copilot-chat/` は JSON、`state.vscdb` (sqlite) はバイナリ |
| Copilot (CLI) | `~/.copilot/` | session ごとのテキストファイル | バージョン依存 | はい |
| Aider | `~/.aider.*` と repo ごとの `.aider.chat.history.md` | チャットログ内の絶対 path | しない | はい — markdown |

Linux は `~/Library/Application Support/` の代わりに `~/.config/`、Windows (WSL) は Linux と同じ。**毎回の移行で、この表から該当する全ストレージ root を列挙し、Phase 1 でチェックする。**

## 運用モデル

Relocation は破壊的 (filesystem move + AI substrate rename + content rewrite + IDE workspace storage migration) で、AGENTS.md §Operation Model に従う。各 Step は独自の Propose → Confirm → Execute。Step 内の複数操作は、最初に全リストを提示すれば 1 確認を共有できる。

```text
Phase 1 Discovery -> Phase 2 Plan -> Phase 3 Execute (step ごと) -> Phase 4 Verify
```

partial 移行からの復旧は同じ 4 フェーズだが、Step 2 を straight `mv` ではなく [Recovery](#recovery-partial-migration) の merge 戦略に置き換える。

## In-session migration: self-protection

移行を駆動する AI エージェント自身が `$OLD` 内のプロジェクト内で動いている場合、エージェント自身の cwd、フックスクリプト、AI substrate が移動の途中で無効化される可能性がある。

**default**: プロジェクト内に **無い** cwd を持つ新しいターミナルを開いてもらい、そこから移行を再起動するよう使用者に依頼する。これが最も安全な経路で、下記の懸念のほとんどは消える。

In-session migration が避けられない場合は、次のオーケストレーション付き transition に従う。

1. Phase 1 のバックアップを最初に取る (移行エージェント自身のセッションを含む全 AI substrate)。
2. 破壊的操作の前に symlink を解決する。
   ```sh
   ACTUAL_CWD=$(realpath .)
   echo "agent realpath cwd: $ACTUAL_CWD"
   [ "$ACTUAL_CWD" = "$OLD" ] || echo "WARN: cwd resolves to $ACTUAL_CWD, not $OLD"
   ```
3. プロジェクトが `$OLD` keyed の path を読むフックスクリプトを持つ場合、`AI_OPS_MIGRATION_IN_PROGRESS=1` を設定し、変数が立っている間それらのフックを short-circuit させる。ai-ops 自身はフックを持たない。これはプロジェクトレベルの慣習。
4. Step 1 → 5 を通常通り実行する。Step 2 の `mv` 後にエージェントの cwd は stale path になるので、即座に `cd "$NEW"` する。
5. Phase 4 で cwd、hook、substrate continuity を検証してから (下記 check 7 参照) `AI_OPS_MIGRATION_IN_PROGRESS` を解除する。

`align this project` エージェントは default で「ターミナルを切り替えるよう使用者に依頼」を選ぶ。in-session 移行を試みるのは最後の手段。

## Phase 1 — Discovery (read-only)

各結果を記録する。Brief は移動前にこれらを示す。

```sh
OLD=<old-path>                        # 例: $HOME/work/<repo>
NEW=$HOME/ghq/<host>/<owner>/<repo>

# 1. uncommitted state
git -C "$OLD" status --short

# 2. tracked file count (move scope)
git -C "$OLD" ls-files | wc -l

# 3. build / cache footprint (Step 1 candidates)
du -sh "$OLD"/{build,.xmake,.cache,target,dist,node_modules,.venv,__pycache__} 2>/dev/null

# 4. realpath / symlink check — split-hash リスクが drift になる前に浮上させる
[ -L "$OLD" ] && echo "WARN: $OLD is a symlink → its target is the canonical path"
ACTUAL_OLD=$(realpath "$OLD")
[ "$ACTUAL_OLD" = "$OLD" ] || echo "INFO: working-tree canonical path is $ACTUAL_OLD"
```

```sh
# 5. Claude Code substrate hash 候補 (v2 / v1 sanitize drift をカバー)
#    v2 (≥ 2.1.x): `/` と `.` の両方が `-` に置換される
#    v1 (< 2.1.x): `/` のみ置換、`.` はそのまま
HASH_V2=$(echo "$OLD" | tr './' '-')
HASH_V1=$(echo "$OLD" | tr / -)
NEW_HASH=$(echo "$NEW"  | tr './' '-')

for h in "$HASH_V2" "$HASH_V1"; do
    [ "$h" = "$HASH_V2" ] || [ "$h" = "$HASH_V1" ] || continue
    [ -d "$HOME/.claude/projects/$h" ] && \
        echo "claude substrate hit: $HOME/.claude/projects/$h"
done

# 6. 全テキストベース AI substrate 横断のコンテンツ path 出現数
grep -rlI -F "$OLD" "$HOME/.claude/projects" 2>/dev/null | wc -l
grep -rlI -F "$OLD" "$HOME/.codex" "$HOME/.copilot" "$HOME/.aider" 2>/dev/null | wc -l
```

```sh
# 7. IDE workspace storage hash (フォルダ URI の md5)。md5 を計算し直すのではなく
#    workspace.json を grep する — IDE が記録した URI そのままを反映している。
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

# 8. 目的地が存在してはならない
ls -la "$NEW" 2>/dev/null | head -1

# 9. 必須バックアップ (AI substrate + IDE workspace storage)
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

`$NEW` がすでに存在する場合は止めて手動で解決する。Claude hash 候補が複数ヒット (v1 と v2 両方にディレクトリがある) する場合、プロジェクトは split 状態 — Phase 3 に進む前に [Recovery](#recovery-partial-migration) へ。

## Phase 2 — Plan

Brief は正確な source / destination パスをリストし、どの AI substrate、IDE workspace storage、ビルドキャッシュが移動・書換・リセット・据え置きされるかを特定する。Brief は **`$OLD` に back-symlink を残さないことを明示する** (Step 2 参照)。Phase 3 のいずれの Step も使用者の Brief 確認後にしか実行しない。

## Phase 3 — Execute (step ごとの確認)

### Step 1: snapshot + cache cleanup

```sh
git -C "$OLD" add -A
git -C "$OLD" commit -m "WIP: pre-relocation snapshot" || true
git -C "$OLD" push

rm -rf "$OLD"/{build,.xmake,.cache,target,dist,node_modules,.venv,__pycache__}
```

コンパイルデータベース (`compile_commands.json`) や絶対 path を焼き付ける他のツールは `$NEW` のソースから再生成される。削除しておけば `$OLD` への stale 参照が残らない。

### Step 2: 物理移動 (完全移行では back-symlink を作らない)

```sh
mkdir -p "$(dirname "$NEW")"
[ -L "$NEW" ] && rm "$NEW"
mv "$OLD" "$NEW"
```

**`$OLD` に back-symlink を作ってはならない。** 完全移行ではアンチパターン:

```sh
# ✗ ANTI-PATTERN — 絶対にやらない:
# ln -s "$NEW" "$OLD"
```

back-symlink が害になる理由:

- IDE / シェル履歴は `$OLD` を解決し、使用者は気付かずそこで作業を続ける。次の Claude Code セッションは `cwd: $OLD` を再記録し、Step 3 の書換が undone になる。
- `cwd` を realpath 解決しない AI ツール (Claude Code、VS Code) は symlink path に別 substrate を再生成 → split-hash drift。
- 「single source of truth」が失われる。同じプロジェクトを 2 つの path が指し、片方しか canonical でない。
- `$OLD` を参照する legacy スクリプトやシェル alias は、symlink で誤魔化さず明示的に `$NEW` へ更新する。

唯一の例外は、IDE workspace migration だけが残った短い transition window で、Phase 4 が IDE が `$NEW` を指していることを確認した瞬間に symlink を削除する場合。Brief に削除手順とタイミングを明記すること。default では symlink を残さない。

### Step 3: AI substrate (rename + content rewrite。v1/v2 hash merge 含む)

`~/.claude/projects/<hash>/` は絶対 path をキーとし、各 `.jsonl` も path を `cwd`、ファイルリソース URI、ツール結果フィールドに焼き付けている — active セッション 1 件あたり数千の言及が普通。ディレクトリ rename だけでは次のセッションが `$OLD` を指したままになる。rename と content rewrite (内容書き換え) の両方が必須。v1 と v2 の hash ディレクトリが両方存在する場合、新 hash に merge する。

```sh
NEW_DIR="$HOME/.claude/projects/$NEW_HASH"

# 3.1 旧 hash ディレクトリ群を新 hash ディレクトリに rename / merge する。
#
# INVARIANT: `cp -an "$src"/*` は *全* エントリをコピーする (`*.jsonl` だけではない)。
# session UUID 名のサブディレクトリ、`memory/`、`tool-results/`、その他の
# トップレベルエントリは jsonls と一緒に移動しなければならない。
# 安易な `*.jsonl` フィルタはこれらを silently 落とし、次のセッションが
# 会話メモリと tool-result キャッシュを失う。
mkdir -p "$NEW_DIR"
for h in "$HASH_V2" "$HASH_V1"; do
    src="$HOME/.claude/projects/$h"
    [ -d "$src" ] && [ "$src" != "$NEW_DIR" ] || continue
    cp -an "$src"/* "$NEW_DIR/" 2>/dev/null || true
    # 旧 hash dir はロールバック用に保持。Phase 4 後に使用者が削除する。
done
```

```sh
# 3.2 content rewrite — リテラル置換。`$OLD` や `$NEW` に `.`、`[`、`\`、`&` 等が
#     含まれていても regex-safe。Phase 1 でバックアップ取得済み。
#
# INVARIANT: `**/*.<ext>` を recursive=True で使えば session ごとのサブディレクトリも
# scan する。`*.<ext>` (no `**`) は `<NEW_DIR>/<uuid>/` 配下を silently 見落とす。
# 拡張子は Claude Code が現在永続化する全テキスト形式をカバー: `.jsonl`
# (sessions、大半)、`.md` (`memory/MEMORY.md` と session 内ノート)、`.json`
# (メタデータ sidecar)、`.txt` (`tool-results/*.txt`)。バイナリ形式 (例: `.pdf`) は
# 対象外。ツールがバイナリ状態の永続化を始めたら、その layout を
# substrate リファレンス表に載せ、ツール固有の rewrite 手順を追加する。
python3 - "$OLD" "$NEW" "$NEW_DIR" <<'PY'
import glob, sys
old, new, target = sys.argv[1], sys.argv[2], sys.argv[3]
patterns = ("*.jsonl", "*.md", "*.json", "*.txt")
paths: set[str] = set()
for ext in patterns:
    paths.update(glob.glob(f"{target}/**/{ext}", recursive=True))
n_files = n_replacements = 0
for path in sorted(paths):
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
# 3.3 他のテキストベース AI substrate
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

`grep -rlI` はバイナリファイルを skip する (`I` フラグ)。状態がバイナリストア (sqlite、leveldb 等) にあるツールは独自の export/import が必要 — VS Code の `state.vscdb` と Cursor の sqlite ストアについては Step 5b 参照。

### Step 4: dev 環境を `$NEW` で再初期化

```sh
cd "$NEW"
direnv allow                                     # .envrc がある場合
# プロジェクト固有の再初期化 — プロジェクトが実際に使うものだけ:
# python: uv sync   |  node: pnpm install  |  rust: cargo build
# nix:    nix flake check
```

### Step 5a: IDE workspace storage — 特定

```sh
case "$(uname -s)" in
    Darwin) IDE_BASE="$HOME/Library/Application Support" ;;
    *)      IDE_BASE="$HOME/.config" ;;
esac

# IDE を先に閉じる — `state.vscdb` への書込競合はファイルを破損させる。
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

使う予定の IDE で `NEW_WS` が空なら、IDE を `$NEW` で 1 度開けばフォルダが作られる。その後 Step 5a を再実行する。

### Step 5b: IDE workspace storage — チャット / 拡張状態のコピー

各 IDE について、JSON ベースのエージェント状態を OLD ワークスペースストレージから NEW へコピーする。**`state.vscdb` (sqlite) は上書きしない** — OLD のものをバックアップとして残し、NEW のものはクリーン状態から続行させ、テキスト重複は Step 3.3 に任せる。

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

Phase 4 で IDE 上にチャット履歴が見えることを確認したら、上記の OLD ワークスペースストレージディレクトリを削除してよい — ただし使用者の明示承認を得てから。

## Phase 4 — Verify (構造 AND コンテンツ)

```sh
# 1. git は新しい path から動く
git -C "$NEW" status
git -C "$NEW" log -1

# 2. プロジェクト自身の check が通る
cd "$NEW" && python -m ai_ops check

# 3. AI substrate ディレクトリが新 hash に存在
ls "$HOME/.claude/projects/$NEW_HASH" | head -3

# 4. content-level rewrite が完了 — 下のカウントは全部 0 でなければならない
grep -rlI -F "$OLD" "$HOME/.claude/projects" 2>/dev/null | wc -l
grep -rlI -F "$OLD" "$HOME/.codex" "$HOME/.copilot" "$HOME/.aider" 2>/dev/null | wc -l

# 5. split-hash ディレクトリが存在しない — 新 hash ディレクトリだけがデータを持ち、
#    旧 hash dir は Step 3.1 の merge 後に消えているか空のはず。
for h in "$HASH_V2" "$HASH_V1"; do
    [ "$h" = "$NEW_HASH" ] && continue
    src="$HOME/.claude/projects/$h"
    if [ -d "$src" ]; then
        count=$(find "$src" -type f | wc -l | tr -d ' ')
        [ "$count" = "0" ] || echo "FAIL: $src still has $count file(s); merge missed?"
    fi
done

# 6. IDE workspace storage が NEW を指し、chatSessions が見える
for ide in Code Cursor; do
    base="$IDE_BASE/$ide/User/workspaceStorage"
    [ -d "$base" ] || continue
    NEW_WS=$(grep -lF "\"file://$NEW\"" "$base"/*/workspace.json 2>/dev/null | head -1)
    [ -n "$NEW_WS" ] || { echo "INFO: $ide has no workspace at $NEW yet"; continue; }
    NEW_DIR=$(dirname "$NEW_WS")
    [ -d "$NEW_DIR/chatSessions" ] && echo "$ide chat sessions: $(ls "$NEW_DIR/chatSessions" | wc -l)"
done

# 7. ファイルシステム上に $OLD の残骸が無い (完全移行 invariant)
[ -e "$OLD" ] && echo "FAIL: $OLD still exists (symlink or directory)"

# 8. in-session: agent cwd が $NEW に解決される
cd "$NEW" && [ "$(realpath .)" = "$NEW" ] || echo "FAIL: cwd does not realpath to $NEW"
```

check 4 のカウントが非ゼロなら Step 3.2 / 3.3 がファイルを見落としているか、別の AI ツールがバイナリ状態を保存している。成功宣言の前に調査する。check 7 で残骸があれば Step 2 のアンチパターンが入り込んだ。check 5 の失敗は Step 3.1 がマージしなかった v1 / v2 sanitize hash の split を示す。

## Recovery (partial migration)

Phase 1 Discovery がプロジェクトの partial 移行状態を示したらこの section を使う。典型的な signal:

- ファイルシステム移動完了 (`$NEW` 存在) だが `$OLD` も残っている (symlink またはディレクトリ断片)。
- Claude hash ディレクトリが複数ヒット (`$HASH_V1` と `$HASH_V2` が両方占有、または `$NEW_HASH` が `$HASH_V2` と並存)。
- ディレクトリ rename はしたのに `grep -rlI -F "$OLD"` のカウントが任意の AI substrate で非ゼロ。
- 同じ session UUID ファイルが複数の hash ディレクトリに現れる。
- 同じ IDE で OLD と NEW の hash の両方に IDE workspace storage が存在。

Recovery は同じ 4 フェーズだが、Step 2 の straight `mv` を **merge** に置き換える。

1. **Phase 1 Discovery (recovery mode)**: Phase 1 を全部走らせ、multi-hash ヒットと content count を recovery branch 配下にキャプチャする。`~/.ai-ops-relocation-backup/recovery-$(date +%Y%m%d-%H%M%S)/` に新規バックアップを取る — recovery の mutation は clean migration と異なるので、バックアップは別ものでなければならない。

2. **Phase 2 Plan**: Brief は見つかった全 hash ディレクトリ、`$OLD` 内の全断片、session UUID ごとの merge map を明示列挙する。各エントリを `keep` / `merge` / `discard` のいずれかにマーク。

3. **Step 1 (Recovery)**: `$OLD` 断片があればクリーンアップ。`$OLD` が back-symlink なら削除 (`mv` 不要。`$NEW` が既にデータを持つ)。

4. **Step 2 (Recovery — move ではなく merge)**: 複数の hash ディレクトリで見つかった session UUID ごとに、canonical コピーを選び (最大サイズか最新 mtime が妥当な default)、`$NEW_HASH/<uuid>.jsonl` に置き、兄弟を `<uuid>-fragment-<source-hash-trimmed>.jsonl` にリネーム。`<source-hash-trimmed>` は `${source_hash#-}` — Claude が前置する `-` を剥がし、ファイル名は `<uuid>-fragment-Users-foo-...jsonl` になるようにする (`<uuid>-fragment--Users-foo-...jsonl` のリテラル double-dash は可読性とハイフン分割のツールを傷める)。ユニークなファイルは `$NEW_HASH/` に直接コピーする。

5. **Step 3 (Recovery)**: メイン flow の Step 3.2 / 3.3 を merge 後の `$NEW_DIR` と全テキストベース AI substrate に対して走らせる。バイナリストア (sqlite、leveldb) は据え置き。OLD コピーがロールバック artifact、NEW コピーは fresh から続行。

6. **Step 4 / 5**: メイン flow と同一 — dev 環境再初期化、生き残った OLD ワークスペースストレージから NEW へ IDE チャット状態をコピー。

7. **Phase 4 (Recovery)**: 8 つの検証すべて走らせる。同じ pass 基準: `grep -rlI -F "$OLD"` は 0、split hash dirs はデータを持たない、`$OLD` は path / symlink として存在しない。加えて `*-fragment-*.jsonl` が対応する canonical 兄弟なしに残っていないことを確認。

8. **Cleanup (使用者承認)**: Phase 4 が pass し、使用者が `*-fragment-*.jsonl` セットをレビューしてはじめて、旧 hash ディレクトリを削除する。Recovery は使用者の sign-off なしには破壊的削除を行わない — オリジナル substrate がロールバック手段。

## Rollback

Step 3 は AI substrate を in-place で書き換えた。ロールバックは Phase 1 のバックアップから復元する。

```sh
# directory move
mv "$NEW" "$OLD"
# AI substrate restore (Phase 1 のバックアップから。リネームではない)
rm -rf "$HOME/.claude/projects/$NEW_HASH"
[ -d "$BACKUP_ROOT/claude-projects" ] && cp -a "$BACKUP_ROOT/claude-projects" "$HOME/.claude/projects"
# IDE workspace storage restore: バックアップ済みの各 <hash> ディレクトリを巻き戻す
for backup in "$BACKUP_ROOT"/Code-* "$BACKUP_ROOT"/Cursor-*; do
    [ -d "$backup" ] || continue
    name=$(basename "$backup")           # 例: Code-02b51147...
    ide=${name%%-*}                      # Code | Cursor
    hash=${name#*-}                      # 02b51147...
    rm -rf "$IDE_BASE/$ide/User/workspaceStorage/$hash"
    cp -a "$backup" "$IDE_BASE/$ide/User/workspaceStorage/$hash"
done
```

他の AI ツールのロールバックも同等。Step 3.3 の前に取ったバックアップから復元する。Git 自身は path-agnostic なので、ロールバックにリモート操作は不要。

## 制約

- commit 済み状態で開始する。dirty な `mv` は作業ツリーを inconsistent にしうる。
- 同一ファイルシステム間の `mv` は atomic。ファイルシステム跨ぎは明示的な copy → verify → delete が必要。
- 各 Step は独自の承認。AI data substrate rename + content rewrite (Step 3) と IDE workspace storage migration (Step 5) は AGENTS.md §Operation Model に明示列挙されている。
- 目的地 path に既存の symlink がある場合、`mv` 前に削除する (macOS は symlink 自身を上書きし、その target ではない)。
- 完全移行では **`$OLD` に back-symlink なし** (Step 2)。狭い transition 例外のみ許容。Brief に明示的な削除 step が伴わなければならない。
- AI セッションストレージがテキストベースなら **content rewrite は必須** (Step 3.2 / 3.3)。ディレクトリ rename だけでは完全移行ではない。
- テキストベースのセッションデータを持つ全ストレージ位置に対して **Phase 4 grep は 0 を報告しなければならない**。非ゼロは見逃した位置あり。
- **Hash 候補は v1 + v2 sanitize ルール (および将来の variant) を列挙する**。単一ルールの Discovery は split-hash drift を silently 見落とす。
- **In-session migration はターミナル再起動を優先する**。inline transition のオーケストレーションは、ターミナル再起動が不可能な場合のみ。
- **Recovery の破壊的クリーンアップは fragment ごとに使用者承認が必要**。オリジナル substrate がロールバック artifact。

## 関連

- `AGENTS.md` §Workspace — `~/ghq/` が canonical
- `AGENTS.md` §Operation Model — Propose → Confirm → Execute
- `docs/realignment.md` — `align this project` がこの playbook に到達するルート
- `docs/project-addition-and-migration.md` — Tier 昇格 path 移動
