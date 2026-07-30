"""Build the Phase 2-0-b evidence report from read-only source artifacts."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[4]
DATA_DIR = (
    REPO_ROOT
    / "Delta_Engine_Pro4web"
    / "data_05M"
    / "depth_history_raw"
    / "symbol=BTCUSDT"
)
REPORT_PATH = (
    REPO_ROOT
    / "ArchitectureRepository"
    / "00_Master"
    / "HEATMAP"
    / "Phase_2-0-b_記録物現物提出報告.md"
)
VERIFY_PATH = SCRIPT_PATH.with_name("verify_depth_history.py")
ORDERBOOK_PATH = (
    REPO_ROOT / "Delta_Engine_Pro4web" / "src" / "orderflow" / "orderbook.py"
)
TESTS_PATH = REPO_ROOT / "Delta_Engine_Pro4web" / "tests"


VERIFY_OUTPUT = r"""PHASE_2_0_B_DEPTH_HISTORY_VERIFICATION
DATA_DIR: C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web\data_05M\depth_history_raw\symbol=BTCUSDT
SEGMENT_COUNT: 2
SEGMENT: raw_depth.20260729T110911.036557Z.jsonl bytes=7774951 lines=11975
SEGMENT: raw_depth.20260729T113705.315567Z.jsonl bytes=1444501 lines=2226
JSON_ERROR_COUNT: 0
DEPTH_UPDATE_COUNT: 5097
DEPTH_UPDATE_ADJACENT_PAIR_COUNT: 5096
DEPTH_UPDATE_CHAIN_MISMATCH_COUNT: 1
DEPTH_UPDATE_CHAIN_MISMATCH: previous=raw_depth.20260729T110911.036557Z.jsonl:11975 previous_u=11161471812523 next=raw_depth.20260729T113705.315567Z.jsonl:2 next_pu=11161591222580 snapshot_between=true
SNAPSHOT_COUNT: 2
SNAPSHOT_CONNECTION: snapshot=raw_depth.20260729T110911.036557Z.jsonl:1 snapshot_u=11161433367685 capture_reason='INITIAL_BOOK_SYNC' next_depth_update=raw_depth.20260729T110911.036557Z.jsonl:2 next_U=11161433377860 next_u=11161433384728 target=11161433367686 result=FAIL
SNAPSHOT_CONNECTION: snapshot=raw_depth.20260729T113705.315567Z.jsonl:1 snapshot_u=11161591208786 capture_reason='INITIAL_BOOK_SYNC' next_depth_update=raw_depth.20260729T113705.315567Z.jsonl:2 next_U=11161591223109 next_u=11161591239445 target=11161591208787 result=FAIL
SEGMENT_BOUNDARY_COUNT: 1
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T110911.036557Z.jsonl next_segment=raw_depth.20260729T113705.315567Z.jsonl previous_depth_update=raw_depth.20260729T110911.036557Z.jsonl:11975 previous_u=11161471812523 next_depth_update=raw_depth.20260729T113705.315567Z.jsonl:2 next_pu=11161591222580 snapshot_before_next_update=true result=FAIL
FLOAT_NUMBER_LINE_COUNT: 0
RESULT: COMPLETE"""


PYTEST_TAIL = """tests/webapp/test_push_broker.py::test_price_cvd_delta_oi_combination_guide_is_clickable_observation_reference
tests/webapp/test_push_broker.py::test_live_observation_and_fixed_chart_detail_keep_final_readability_contract
tests/webapp/test_push_broker.py::test_flow_response_state_guide_explains_all_colors_without_changing_chart
tests/webapp/test_tape_update.py::test_batcher_preserves_acceptance_order_sequence_and_message_cap
tests/webapp/test_tape_update.py::test_overflow_drops_oldest_and_exposes_real_sequence_gap
tests/webapp/test_tape_update.py::test_slow_sender_never_blocks_publish_and_overflow_remains_accounted
tests/webapp/test_tape_update.py::test_send_failure_becomes_explicit_drop_on_next_batch
tests/webapp/test_tape_update.py::test_invalid_tap_input_is_rejected_without_consuming_sequence
tests/webapp/test_tape_update.py::test_new_batcher_creates_new_stream_and_restarts_sequence_at_one
tests/webapp/test_tape_update.py::test_replay_batch_uses_last_trade_market_time_not_wall_clock
tests/webapp/test_tape_update.py::test_push_broker_serializes_tape_and_does_not_replay_batch_on_reconnect
tests/webapp/test_tape_update.py::test_time_sales_history_is_oldest_first_exact_and_before_is_exclusive
tests/webapp/test_version.py::test_parse_version_latest_entry_wins
tests/webapp/test_version.py::test_parse_version_no_heading_returns_none
tests/webapp/test_version.py::test_resolve_version_from_file
tests/webapp/test_version.py::test_resolve_version_missing_file_falls_back
tests/webapp/test_version.py::test_resolve_version_first_hit_wins
tests/webapp/test_version.py::test_api_version_endpoint

696 tests collected in 87.18s (0:01:27)

ExitCode        : 0
OutputLineCount : 698"""


def fenced(language: str, body: str) -> str:
    return f"```{language}\n{body}\n```"


def load_rows(segments: list[Path]) -> tuple[dict[str, list[str]], list[dict]]:
    raw_by_segment: dict[str, list[str]] = {}
    records: list[dict] = []
    for segment in segments:
        lines = segment.read_text(encoding="utf-8").splitlines()
        raw_by_segment[segment.name] = lines
        for line_number, line in enumerate(lines, start=1):
            payload = json.loads(line)
            payload["_report_segment"] = segment.name
            payload["_report_line"] = line_number
            records.append(payload)
    return raw_by_segment, records


def test_structure() -> tuple[int, int, int, list[tuple[str, int]]]:
    files = sorted(TESTS_PATH.rglob("test_*.py"))
    groups: Counter[str] = Counter()
    root_count = 0
    for path in files:
        relative = path.relative_to(TESTS_PATH)
        if len(relative.parts) == 1:
            root_count += 1
            groups["(tests root)"] += 1
        else:
            groups[relative.parts[0]] += 1
    return len(files), root_count, len(files) - root_count, sorted(groups.items())


def command_log() -> str:
    return r"""
本節の「結果」は、全文掲載を明示したコマンド以外は、当該コマンドの終了コードと
本報告の対応節を示す。失敗した補助コマンド2件も隠さず記録する。

1. 初期Git状態・トップ階層・`depth_history_raw`のGit管理対象内検索

   ```powershell
   $root = (Get-Location).Path
   $gitTop = git rev-parse --show-toplevel 2>&1
   $gitStatus = git status --short 2>&1
   $topEntries = Get-ChildItem -Force | Select-Object Mode, Name, Length
   [pscustomobject]@{ WorkingDirectory = $root; GitTopLevel = ($gitTop -join "`n"); GitStatusShort = ($gitStatus -join "`n") } | Format-List
   $topEntries | Format-Table -AutoSize
   rg --files | rg '(^|[\\/])depth_history_raw([\\/]|$)'
   ```

   結果: 終了コード1。`git rev-parse`は
   `C:/Users/user/Desktop/DeltaEngine05M`。既存の変更・未追跡物が多数存在した。
   最後の`rg`はGit管理対象外データを検索できず0件だったため複合コマンド全体が1。

2. `data_05M`候補パス確認

   ```powershell
   [System.IO.Directory]::Exists(<root>/data_05M)
   [System.IO.Directory]::Exists(<root>/Delta_Engine_Pro4web/data_05M)
   [System.IO.Directory]::Exists(<root>/project/data_05M)
   ```

   結果: 終了コード0。中央の候補だけが存在し、対象symbolディレクトリも存在。

3. 対象ファイル一覧

   ```powershell
   Get-ChildItem -LiteralPath <symbol-directory> -File |
     Sort-Object Name | Select-Object Name, Length, LastWriteTime
   ```

   結果: 終了コード0。JSONL 2件、manifest 2件。詳細は§3.1。

4. StreamReaderによる行数計数とmanifest全文読取

   ```powershell
   $reader = [System.IO.File]::OpenText($segment.FullName)
   while ($null -ne $reader.ReadLine()) { $lineCount++ }
   [System.IO.File]::ReadAllText($manifest.FullName, [System.Text.Encoding]::UTF8)
   ```

   結果: 終了コード0。詳細は§3.1、§3.2。

5. サンプル行のスキーマ要約（1回目）

   ```powershell
   [pscustomobject]@{ U = $row.U; u = $row.u }
   ```

   結果: 終了コード1。PowerShellはハッシュキーの大文字小文字を区別せず、
   `U`と`u`を重複キーと判定した。データ読取前のParserError。

6. サンプル行のスキーマ要約（2回目）

   ```powershell
   $indices = @(0, 1, 2, $lines.Length - 2, $lines.Length - 1)
   ```

   結果: プロセス終了コード0だがPowerShell `InvalidOperation`。
   配列リテラル内の減算解釈が原因。データ変更なし。この補助処理は再試行せず、
   保存済みPython検証器へ切り替えた。

7. Phase 1報告内の関連語検索

   ```powershell
   rg -n --no-heading "depth_history_raw|depthSnapshot|_capture_reason|OrderBookStateManager|raw_depth" <P1 reports>
   ```

   結果: 終了コード0。P1-2/P1-2b/P1-3の関連箇所を確認。判定は本指示書の
   現物走査結果を正とした。

8. 許可出力先の重複確認

   ```powershell
   [System.IO.File]::Exists(<verify-script>)
   [System.IO.File]::Exists(<report>)
   ```

   結果: 終了コード0。作成前はいずれもFalse。

9. 検証スクリプト実行

   ```powershell
   python ArchitectureRepository/00_Master/HEATMAP/tools_p20b/verify_depth_history.py Delta_Engine_Pro4web/data_05M/depth_history_raw/symbol=BTCUSDT
   ```

   結果: 終了コード0。標準出力全文は§4.4。

10. `OrderBookStateManager`候補検索

    ```powershell
    rg -n --no-heading "class OrderBookStateManager|def [A-Za-z_]*(snapshot|diff)|gap|last_update_id|lastUpdateId" Delta_Engine_Pro4web/src Delta_Engine_Pro4web/tests |
      rg "OrderBookStateManager|orderbook|order_book|book_state|snapshot|gap"
    ```

    結果: 終了コード0。定義は`src/orderflow/orderbook.py:97`。詳細は§5.1。

11. `orderbook.py` 90〜280行の行番号付き読取

    ```powershell
    $lines = [System.IO.File]::ReadAllLines(<orderbook.py>, [System.Text.Encoding]::UTF8)
    for ($lineNumber = 90; $lineNumber -le 280; $lineNumber++) {
      '{0,4}: {1}' -f $lineNumber, $lines[$lineNumber - 1]
    }
    ```

    結果: 終了コード0。署名・gap挙動は§5.1。

12. `.git`全階層、root/submodule/内側候補確認

    ```powershell
    Get-ChildItem -LiteralPath <root> -Force -Recurse -Filter '.git'
    git rev-parse --show-toplevel
    git submodule status
    git -C Delta_Engine_Pro4web rev-parse --show-toplevel
    git -C Delta_Engine_Pro4web rev-parse --git-dir
    ```

    結果: 終了コード0。詳細は§5.2。

13. `git cat-file`等のオブジェクト確認（1回目）

    ```powershell
    foreach ($hash in $hashes) { [pscustomobject]@{...} } | Format-Table
    ```

    結果: 終了コード1。PowerShellの`foreach`文直後のpipeがParserError。
    Gitコマンド実行前の失敗。

14. `git cat-file`、Heatmap range、祖先確認（修正版）

    ```powershell
    foreach ($hash in $hashes) { git cat-file -t $hash }
    git log --oneline --reverse 'f94822a^..e358a0f'
    git merge-base --is-ancestor f94822a e358a0f
    ```

    結果: 終了コード0。対象7 hashはすべて`commit`。Heatmap 5 commitと
    endpointの祖先関係は§5.2。

15. PROJECT_MEMORY記載commitのHeatmap/HEAD祖先確認

    ```powershell
    git rev-parse HEAD
    git show -s --format='%h %s' <hash>
    git merge-base --is-ancestor <hash> f94822a
    git merge-base --is-ancestor <hash> HEAD
    ```

    結果: 終了コード0（個別祖先判定はexit 1を結果値として取得）。
    5 commitともHeatmap開始・HEADの祖先ではない。詳細は§5.2。

16. テストファイル構成計数

    ```powershell
    Get-ChildItem -LiteralPath Delta_Engine_Pro4web/tests -File -Recurse -Filter 'test_*.py'
    ```

    結果: 終了コード0。100ファイル。内訳は§5.3。

17. pytest収集のみ

    ```powershell
    $collectOutput = python -m pytest --collect-only -q 2>&1
    $collectOutput | Select-Object -Last 20
    ```

    作業ディレクトリ:
    `C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web`

    結果: 終了コード0、出力698行、`696 tests collected in 87.18s`。
    末尾全文は§5.3。テスト本体は実行していない。

18. testsの既存worktree差分確認

    ```powershell
    git diff --numstat -- Delta_Engine_Pro4web/tests
    git diff --unified=0 -- Delta_Engine_Pro4web/tests | rg '^\+def test_'
    ```

    結果: 終了コード0。`test_book_update.py`に既存の+117/-0行、
    追加test定義3件。改行警告あり。変更は行っていない。

19. PROJECT_MEMORY記載commitのref包含・Heatmapとのmerge-base確認

    ```powershell
    git for-each-ref --format='%(refname)' --contains <hash>
    git merge-base <hash> f94822a
    ```

    結果: 終了コード0（個別merge-baseはexit 1を結果値として取得）。
    5件とも`refs/remotes/proposed-origin/master`に包含されるが、
    `f94822a`とのmerge-baseは存在しない。詳細は§5.2。

20. 現物貼付量と境界行長の確認

    ```powershell
    [System.IO.File]::ReadAllLines(<segment>, [System.Text.Encoding]::UTF8)
    ```

    結果: 終了コード0。先頭5行43,212文字、末尾5行5,539文字。
    最大行は42,140文字。境界後1行目は42,134文字。

21. 報告書生成

    ```powershell
    python ArchitectureRepository/00_Master/HEATMAP/tools_p20b/build_phase_2_0_b_report.py
    ```

    結果: 終了コード0。本ファイルを許可先へ生成。

22. 報告書・現物転記・manifest hash・変更範囲の最終確認

    ```powershell
    [System.IO.File]::ReadAllText(<report>, [System.Text.Encoding]::UTF8)
    [System.IO.File]::ReadAllLines(<segments>, [System.Text.Encoding]::UTF8)
    Get-FileHash -LiteralPath <segment> -Algorithm SHA256
    git status --short -- ArchitectureRepository/00_Master/HEATMAP
    ```

    結果: 終了コード0。報告書123,809 byte／617行、必須marker欠落0、
    raw sample欠落0、manifest本文欠落0。2セグメントとも実ファイルSHA-256が
    manifest記載値と一致。既存HEATMAP成果物は未追跡のまま保持し、本作業の新規物は
    `Phase_2-0-b_記録物現物提出報告.md`と`tools_p20b/`配下2スクリプト。
""".strip()


def main() -> int:
    segments = sorted(DATA_DIR.glob("*.jsonl"))
    if not segments:
        raise SystemExit(f"No segments found: {DATA_DIR}")
    raw_by_segment, records = load_rows(segments)
    manifests = sorted(DATA_DIR.glob("*.manifest.json"))
    first_segment = segments[0]
    first_lines = raw_by_segment[first_segment.name]

    snapshots = [row for row in records if row.get("e") == "depthSnapshot"]
    updates = [row for row in records if row.get("e") == "depthUpdate"]
    event_counts = Counter(str(row.get("e")) for row in records)
    segment_update_counts = Counter(
        row["_report_segment"] for row in updates
    )

    test_file_count, test_root_count, test_sub_count, test_groups = (
        test_structure()
    )
    now = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds")

    parts: list[str] = []
    parts.append("# [完了] Phase 2-0-b 記録物現物提出")
    parts.append("")
    parts.append(f"- 報告作成時刻: `{now}`")
    parts.append(
        "- 報告書保存先: "
        "`ArchitectureRepository/00_Master/HEATMAP/"
        "Phase_2-0-b_記録物現物提出報告.md`"
    )
    parts.append(
        "- 検証スクリプト: "
        "`ArchitectureRepository/00_Master/HEATMAP/tools_p20b/"
        "verify_depth_history.py`"
    )
    parts.append(
        "- 報告書生成補助: "
        "`ArchitectureRepository/00_Master/HEATMAP/tools_p20b/"
        "build_phase_2_0_b_report.py`"
    )
    parts.append("- 調査対象: 既存記録データのみ。ライブ接続なし。")
    parts.append(
        "- 変更範囲: 上記スクリプト2件と本報告書のみ。"
        "記録データ・リポジトリ本体は未変更。"
    )
    parts.append("")

    parts.append("## §3 タスクA: 記録物の現物提出")
    parts.append("")
    parts.append("### §3.1 セグメントファイル一覧")
    parts.append("")
    parts.append(
        "実パスは"
        "`Delta_Engine_Pro4web/data_05M/depth_history_raw/"
        "symbol=BTCUSDT/`。"
    )
    parts.append("")
    parts.append("| ファイル名 | byte数 | 行数 |")
    parts.append("|---|---:|---:|")
    for segment in segments:
        parts.append(
            f"| `{segment.name}` | {segment.stat().st_size:,} | "
            f"{len(raw_by_segment[segment.name]):,} |"
        )
    parts.append("")
    parts.append(
        f"全セグメント合計: {sum(p.stat().st_size for p in segments):,} byte / "
        f"{sum(len(raw_by_segment[p.name]) for p in segments):,}行。"
    )
    parts.append(
        "イベント内訳: "
        + "、".join(
            f"`{name}` {count:,}行"
            for name, count in sorted(event_counts.items())
        )
        + "。"
    )
    parts.append(
        "depthUpdate内訳: "
        + "、".join(
            f"`{name}` {segment_update_counts[name]:,}行"
            for name in sorted(segment_update_counts)
        )
        + "。"
    )
    parts.append("")

    parts.append("### §3.2 manifest全文")
    parts.append("")
    for manifest in manifests:
        parts.append(f"#### `{manifest.name}`")
        parts.append("")
        parts.append(
            fenced(
                "json",
                manifest.read_text(encoding="utf-8").rstrip("\r\n"),
            )
        )
        parts.append("")

    parts.append("### §3.3 最初のセグメントの先頭5行・末尾5行")
    parts.append("")
    parts.append(f"対象: `{first_segment.name}`")
    parts.append("")
    parts.append("#### 先頭5行（現物）")
    parts.append("")
    parts.append(fenced("jsonl", "\n".join(first_lines[:5])))
    parts.append("")
    parts.append("#### 末尾5行（現物）")
    parts.append("")
    parts.append(fenced("jsonl", "\n".join(first_lines[-5:])))
    parts.append("")

    parts.append("### §3.4 depthSnapshot総数・出現位置")
    parts.append("")
    parts.append(f"総数: **{len(snapshots)}行**")
    parts.append("")
    parts.append("| セグメント:行番号 | `_capture_reason` | `u` |")
    parts.append("|---|---|---:|")
    for snapshot in snapshots:
        parts.append(
            f"| `{snapshot['_report_segment']}:{snapshot['_report_line']}` | "
            f"`{snapshot.get('_capture_reason')}` | {snapshot.get('u')} |"
        )
    parts.append("")

    parts.append("### §3.5 複数セグメント境界の前後各2行")
    parts.append("")
    for previous, following in zip(segments, segments[1:]):
        previous_lines = raw_by_segment[previous.name]
        following_lines = raw_by_segment[following.name]
        parts.append(f"#### `{previous.name}` → `{following.name}`")
        parts.append("")
        parts.append(
            "前側は"
            f"`{previous.name}:{len(previous_lines) - 1}`〜"
            f"`{previous.name}:{len(previous_lines)}`、後側は"
            f"`{following.name}:1`〜`{following.name}:2`。"
        )
        parts.append("")
        parts.append(fenced("jsonl", "\n".join(previous_lines[-2:])))
        parts.append("")
        parts.append(fenced("jsonl", "\n".join(following_lines[:2])))
        parts.append("")
    parts.append(
        "注: 両manifestの`closed_reason`は`close`で、開始時刻間に約20分48秒の"
        "空きがある。したがって現物上は「自動rotationが連続した境界」ではなく、"
        "2回の独立capture境界と判断する。ただし複数セグメント境界として現物を提出した。"
    )
    parts.append("")

    parts.append("### §3.6 float型混入チェック")
    parts.append("")
    parts.append(
        "**0行**。全14,201行を`json.loads`し、dict/listを再帰走査して"
        "Python `float`が1つでも含まれる行を数えた。"
        "ID・時刻等の整数型は対象外で、価格・数量の文字列保持を確認する検査である。"
        "JSON parse errorも0件。"
    )
    parts.append("")

    parts.append("## §4 タスクB: 連続性の機械検証")
    parts.append("")
    parts.append("### §4.1 depthUpdate連続性")
    parts.append("")
    parts.append(
        "- depthUpdate: 5,097行、隣接ペア: 5,096組。"
    )
    parts.append(
        "- `pu(後) == u(前)`不成立: **1組**。"
    )
    parts.append(
        "- 不成立箇所: "
        "`raw_depth.20260729T110911.036557Z.jsonl:11975` "
        "`u=11161471812523` → "
        "`raw_depth.20260729T113705.315567Z.jsonl:2` "
        "`pu=11161591222580`。"
    )
    parts.append(
        "- この1組はセグメント跨ぎで、間に次セグメント1行目の"
        "`depthSnapshot`が存在する。セグメント内5,095組は全件成立。"
    )
    parts.append("")

    parts.append("### §4.2 snapshot接続")
    parts.append("")
    parts.append("| snapshot | snapshot `u` | 直後のdepthUpdate | `U` | `u` | `u_snapshot+1` | 判定 |")
    parts.append("|---|---:|---|---:|---:|---:|---|")
    parts.append(
        "| `raw_depth.20260729T110911.036557Z.jsonl:1` | "
        "11161433367685 | `同:2` | 11161433377860 | 11161433384728 | "
        "11161433367686 | **FAIL** |"
    )
    parts.append(
        "| `raw_depth.20260729T113705.315567Z.jsonl:1` | "
        "11161591208786 | `同:2` | 11161591223109 | 11161591239445 | "
        "11161591208787 | **FAIL** |"
    )
    parts.append("")
    parts.append(
        "2件とも`U <= u_snapshot + 1 <= u`を満たさない。いずれも"
        "`U > u_snapshot + 1`。修正・再記録は行っていない。"
    )
    parts.append("")

    parts.append("### §4.3 セグメント跨ぎ")
    parts.append("")
    parts.append(
        "境界1件のdepthUpdate同士の`pu`チェーンは**FAIL**。"
        "ただし後セグメントは1行目に`INITIAL_BOOK_SYNC` snapshotを持つ独立captureであり、"
        "連続rotationではない。生の比較結果はFAILのまま報告する。"
    )
    parts.append("")

    parts.append("### §4.4 検証スクリプト・実行コマンド・出力全文")
    parts.append("")
    parts.append(
        "スクリプト: "
        "`ArchitectureRepository/00_Master/HEATMAP/tools_p20b/"
        "verify_depth_history.py`"
    )
    parts.append("")
    parts.append(fenced(
        "powershell",
        "python ArchitectureRepository/00_Master/HEATMAP/tools_p20b/"
        "verify_depth_history.py "
        "Delta_Engine_Pro4web/data_05M/depth_history_raw/symbol=BTCUSDT",
    ))
    parts.append("")
    parts.append("出力全文:")
    parts.append("")
    parts.append(fenced("text", VERIFY_OUTPUT))
    parts.append("")

    parts.append("## §5 タスクC: 既存資産とリポジトリ構造")
    parts.append("")
    parts.append("### §5.1 OrderBookStateManagerの現物確認")
    parts.append("")
    parts.append(
        "- 定義ファイル: "
        "`Delta_Engine_Pro4web/src/orderflow/orderbook.py`"
    )
    parts.append("- クラス定義: 同ファイル **97行目**。")
    parts.append(
        "- snapshot/diff共通の公開適用入口: "
        "`def apply(self, update: OrderBookUpdate) -> ApplyResult:` "
        "（129行目）。136〜139行で`SNAPSHOT`を`_apply_snapshot`、"
        "`DIFF`を`_apply_diff`へdispatchする。"
    )
    parts.append(
        "- 初期snapshot同期モードの公開メソッド: "
        "`def apply_initial_sync(self, snapshot_update_id: int) -> None:` "
        "（142行目）。"
    )
    parts.append(
        "- snapshot適用本体はprivate "
        "`def _apply_snapshot(self, update: OrderBookUpdate) -> ApplyResult:` "
        "（196行目）。既存板を空にしてlevelを入れ直し、"
        "`_last_update_id=update.final_update_id`、初期化済みにする"
        "（197〜211行）。"
    )
    parts.append(
        "- diff適用本体はprivate "
        "`def _apply_diff(self, update: OrderBookUpdate) -> ApplyResult:` "
        "（213行目）。"
    )
    parts.append(
        "- `def snapshot(self) -> Optional[OrderBookSnapshot]:`（176行目）は"
        "現在状態の読出しであり、snapshot適用APIではない。"
    )
    parts.append("")
    parts.append("gap検出時の挙動:")
    parts.append("")
    parts.append(
        "- 244〜252行: `pu`があれば`pu != _last_update_id`、なければ"
        "`U != _last_update_id + 1`でgap判定。"
    )
    parts.append(
        "- 253〜268行: gap時はbid/askを空にし、`_last_update_id=None`、"
        "`_sync_id=None`、`_initialized=False`、`gaps_detected += 1`。"
        "当該diffは適用せず`ApplyResult(..., gap_detected=True)`を返す。"
    )
    parts.append(
        "- 233〜242行: `apply_initial_sync`後の最初のnon-stale diffは"
        "Binance Futuresの接続timingを理由に**lenient**に受理し、"
        "厳密な`U <= snapshot+1 <= u`を再検査しない。今回のsnapshot接続FAILと"
        "再構築設計上の重要な差である。"
    )
    parts.append("")
    parts.append("主要コード（現物抜粋）:")
    parts.append("")
    orderbook_lines = ORDERBOOK_PATH.read_text(encoding="utf-8").splitlines()
    snippets = []
    for start, end in ((97, 103), (127, 151), (196, 276)):
        snippets.extend(
            f"{number:4}: {orderbook_lines[number - 1]}"
            for number in range(start, end + 1)
        )
        snippets.append("")
    parts.append(fenced("python", "\n".join(snippets).rstrip()))
    parts.append("")

    parts.append("### §5.2 リポジトリ構造・commit所属")
    parts.append("")
    parts.append(
        "- active rootでの`git rev-parse --show-toplevel`: "
        "`C:/Users/user/Desktop/DeltaEngine05M`。"
    )
    parts.append(
        "- `git -C Delta_Engine_Pro4web rev-parse --show-toplevel`も同じroot、"
        "`--git-dir`もrootの`.git`。現在の`Delta_Engine_Pro4web`はnested repoではない。"
    )
    parts.append("- `git submodule status`: 出力なし。submoduleなし。")
    parts.append(
        "- `.git`は再帰走査で7ディレクトリ。activeはrootの1個。残り6個は"
        "`archive/external-backups`または`DeltaEngine_BACKUP_20260719`配下の"
        "保存済みnested repositoryで、active source treeのGit境界ではない。"
    )
    parts.append("")
    parts.append("`.git`現物一覧:")
    parts.append("")
    git_dirs = [
        ".git",
        "archive/external-backups/DeltaEngine_broken_20260718/.git",
        "archive/external-backups/DeltaEngine_mixed_20260718/.git",
        "DeltaEngine_BACKUP_20260719/.git",
        "DeltaEngine_BACKUP_20260719/archive/external-backups/"
        "DeltaEngine_broken_20260718/.git",
        "DeltaEngine_BACKUP_20260719/archive/external-backups/"
        "DeltaEngine_mixed_20260718/.git",
        "DeltaEngine_BACKUP_20260719/Delta_Engine_Pro4web/.git",
    ]
    parts.extend(f"- `{path}`" for path in git_dirs)
    parts.append("")
    parts.append(
        "Heatmap line（`f94822a^..e358a0f`）は次の同一連結履歴:"
    )
    parts.append("")
    parts.append(fenced(
        "text",
        """f94822a feat(depth-history): ADR-011 raw depth recorder (P1-1)
a7f107d fix(depth-history): correct rotation test threshold (P1-1修正1)
28d656c feat(depth-history): wire raw recorder into acquisition tap (P1-1-b)
091b202 fix(depth-history): restore compose disabled-comment for pd4 contract (P1-1c)
e358a0f fix(depth-history): RecorderTee.close no-op to prevent shutdown AttributeError (P1-2b)""",
    ))
    parts.append("")
    parts.append(
        "`git merge-base --is-ancestor f94822a e358a0f`はexit 0。"
        "調査時HEADは`e358a0f1696ad3065ce37fce1a75f62b43f46ab8`。"
    )
    parts.append("")
    parts.append("| commit | `git cat-file -t` | Heatmap開始の祖先 | HEADの祖先 | 包含ref | Heatmapとのmerge-base |")
    parts.append("|---|---|---|---|---|---|")
    memory_commits = [
        ("a8a7439", "fix: reject invalid zero-value trades"),
        ("c9b804f", "feat: stabilize chart selection and fixed details"),
        ("44270cf", "refactor(webapp): streamline observation dashboard"),
        ("adbcf1e", "feat(webapp): mark recent flow events on candles"),
        ("9c4539d", "feat(webapp): add OI context and observation controls"),
    ]
    for commit_hash, subject in memory_commits:
        parts.append(
            f"| `{commit_hash}` {subject} | `commit` | No | No | "
            "`refs/remotes/proposed-origin/master` | なし（exit 1） |"
        )
    parts.append("")
    parts.append(
        "結論: PROJECT_MEMORY記載commitはactive `.git`のobject databaseには存在するが、"
        "Heatmap lineとは共通祖先のない別履歴であり、同一の連結commit履歴には属さない。"
        "「内側リポジトリ」は現在のactive `Delta_Engine_Pro4web`のGit境界を意味しない。"
    )
    parts.append("")

    parts.append("### §5.3 テストディレクトリ構成・収集数")
    parts.append("")
    parts.append(
        f"- `Delta_Engine_Pro4web/tests`: `test_*.py` **{test_file_count}ファイル**。"
    )
    parts.append(
        f"- tests直下: {test_root_count}、サブディレクトリ: {test_sub_count}。"
    )
    parts.append("- `pytest.ini` / `pyproject.toml` / `setup.cfg` / `tox.ini`は当該root直下に0件。")
    parts.append("")
    parts.append("| tests配下 | testファイル数 |")
    parts.append("|---|---:|")
    for group, count in test_groups:
        parts.append(f"| `{group}` | {count} |")
    parts.append("")
    parts.append(
        "収集コマンド（テスト実行なし）:"
    )
    parts.append("")
    parts.append(fenced("powershell", "python -m pytest --collect-only -q"))
    parts.append("")
    parts.append("末尾出力:")
    parts.append("")
    parts.append(fenced("text", PYTEST_TAIL))
    parts.append("")
    parts.append(
        "- PROJECT_MEMORYの`370 passed`から現在の`696 collected`までは"
        "名目上+326。ただしpassedとcollectedは同一指標ではない。"
    )
    parts.append(
        "- 指示書記載のHeatmap line現状`694 passed`に対し、今回の現物収集は"
        "`696 collected`（名目+2）。"
    )
    parts.append(
        "- 収集時worktreeにはユーザー所有の未コミット"
        "`tests/webapp/test_book_update.py` +117/-0行があり、追加`test_`定義3件を確認。"
        "このため694との差をcommit済みHeatmap lineの増減と断定しない。"
    )
    parts.append("")

    parts.append("## §6 実行した全コマンドと結果")
    parts.append("")
    parts.append(command_log())
    parts.append("")

    parts.append("## §7 発見した想定外事項")
    parts.append("")
    parts.append(
        "1. 指示書の相対対象`data_05M/...`はrepository root直下ではなく、"
        "`Delta_Engine_Pro4web/data_05M/...`に存在した。"
    )
    parts.append(
        "2. 2ファイルはmanifest上いずれも`closed_reason=close`で、"
        "自動rotation連続境界ではなく2回の独立captureである。"
    )
    parts.append(
        "3. 各captureのsnapshot直後diffは厳密なBinance snapshot接続条件を"
        "2件とも満たさない。"
    )
    parts.append(
        "4. depthUpdateのセグメント内`pu`チェーンは全件成立するが、"
        "独立capture間の生比較1件は不成立。次capture先頭にはsnapshotがある。"
    )
    parts.append(
        "5. 現行`OrderBookStateManager`の初期同期処理は厳密接続条件ではなく"
        "最初のnon-stale diffをlenientに受理する。"
    )
    parts.append(
        "6. PROJECT_MEMORY記載commitとHeatmap lineは同一object databaseにあるが、"
        "共通祖先のない別履歴。"
    )
    parts.append(
        "7. 指示書の`694 passed`に対し、現在worktreeの収集結果は"
        "`696 collected`。既存未コミットtest変更がある。"
    )
    parts.append("")
    parts.append(
        "上記事項への修正、再記録、ライブ接続、テスト実行は行っていない。"
    )
    parts.append("")

    parts.append("## §8 報告書保存先")
    parts.append("")
    parts.append(
        "`C:\\Users\\user\\Desktop\\DeltaEngine05M\\ArchitectureRepository\\"
        "00_Master\\HEATMAP\\Phase_2-0-b_記録物現物提出報告.md`"
    )
    parts.append("")

    REPORT_PATH.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    print(f"REPORT_PATH: {REPORT_PATH}")
    print(f"REPORT_BYTES: {REPORT_PATH.stat().st_size}")
    print(
        "REPORT_LINES: "
        f"{len(REPORT_PATH.read_text(encoding='utf-8').splitlines())}"
    )
    print("RESULT: COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
