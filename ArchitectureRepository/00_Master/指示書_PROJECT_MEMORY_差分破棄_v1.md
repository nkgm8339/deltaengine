# 指示書_PROJECT_MEMORY_差分破棄_v1
**作成日: 2026-07-29 / 発行: Claude(統括) / 対象: Claude Code**

---

## 背景・判断根拠

`PROJECT_MEMORY.md` の未コミット差分には、GO-H0〜GO-H6、PD0〜PD6という一連の
「完成」「PASS」「operational activation」「LIVE observation GREEN」主張が含まれている。
これはPhase 0現状調査(2026-07-29)で確認した実態と矛盾する。

矛盾点(Phase 0確定事実 vs 本差分の主張):

| Phase 0確定事実 | 本差分の主張 |
|---|---|
| index.html:969でHeatmapフラグ明示的にOFF | GO-H6で`ORDER_BOOK_HEATMAP_V1_ENABLED=true`、operational activation完了 |
| 実Canvas描画の自動テストなし | 各GOステップでtargeted/WebApp/repository全件PASS数を報告 |
| writerは50段サンプリング、ADR-011違反 | PD6で「production writer有効状態」「30分LIVE soak」「continuity PASS」 |
| Replay経路にHeatmap用板配信なし(main.py:347) | GO-H1で「Book continuity contract」実装完了と主張 |

各セクションが「ユーザー承認により」と繰り返し記載しているが、そのような承認記録は
本開発ラインでは確認できていない。プロジェクト原則(根拠なき断定は書かない)に反するため、
**この差分はコミットしない。破棄する。**

他のMファイル9件(PROJECT_MEMORY.md以外)は対象外とし、変更したまま保持する。

---

## Task: PROJECT_MEMORY.md の未コミット差分のみを破棄

### 手順

```bash
git diff -- ArchitectureRepository/00_Master/PROJECT_MEMORY.md > /tmp/discarded_project_memory_diff_20260729.patch
git checkout -- ArchitectureRepository/00_Master/PROJECT_MEMORY.md
git status --porcelain -- ArchitectureRepository/00_Master/PROJECT_MEMORY.md
```

1. 破棄前に必ず `git diff` の出力をパッチファイルとして保存する(証拠保全。削除しない)。
2. `git checkout` で該当ファイルのみをHEADの状態に戻す。他のファイルには触れない。
3. 破棄後、`PROJECT_MEMORY.md` が変更なし(clean)であることを確認する。

### 対象外(触れない)

- 他のMファイル9件はそのまま変更済み状態で保持する
- 追跡外(??)ファイルには触れない

---

## 完了報告フォーマット

```
[完了/失敗/停止] 指示書_PROJECT_MEMORY_差分破棄_v1

- パッチファイル保存先: /tmp/discarded_project_memory_diff_20260729.patch (保存の成否)
- git checkout実行結果
- 破棄後の git status --porcelain -- PROJECT_MEMORY.md の出力(空であることの確認)
- 他9件のMファイルに変更がないことの確認

## 逸脱事項
なければ「なし」
```

## 禁止事項

- 他のMファイル・追跡外ファイルへの変更
- パッチファイルの削除
- テスト実行、ライブ接続、Phase 1着手
