この補遺を受領したら、確認や承認を求めずに指示書_Divergence_Phase0_v1と併せて全手順を即座に実行せよ。

# 指示書_Divergence_Phase0_v1_補遺A

**位置づけ**: 指示書_Divergence_Phase0_v1 の停止条件（旧 `Divergence` 型への外部参照検出）に対する web の裁定。本補遺により停止を解除する。v1 本文は本補遺での変更点を除きすべて有効。

---

## 1. 裁定

- 外部参照3件（pipeline.py / webapp/push_broker.py / webapp/main.py）は **すべて表示系の配線** であり、SignalEngine（signal.py）への参照はゼロであることを web が実コードで確認した
- よって旧型削除の方針は維持し、**参照3件の移行を Phase 0 スコープに追加**する

## 2. ADR番号

新規ADRは **ADR-009** とする（ADR-008_LiquidationStream_v3.0 既存のため。v1 §1 の繰上げ規則の適用を正式承認）。

## 3. 追加作業（参照3件の移行）

### 3.1 `src/orderflow/divergence.py`

- クラス名 `CvdDivergenceDetector` と `update(candle)` メソッド名は**変更しない**（呼び出し側の差分最小化）
- コンストラクタは全パラメータにキーワードデフォルトを持たせ、`CvdDivergenceDetector()` が挙動保存デフォルト（equal_pivot_policy="first" / min_price_move=Decimal("0") / min_bar_distance=0 / symbol・timeframe検証は最初の受理Candle基準）で動作すること

### 3.2 `src/pipeline.py`

- 原則無変更で動作するはず（`self.divergence` の保持対象が `DivergenceEvent` に変わるのみ）
- config の `divergence:` セクション値を検出器コンストラクタへ渡す配線のみ追加（Replay/Live両経路）

### 3.3 `webapp/push_broker.py`

- `divergence.direction` は Enum になるため、シリアライズを `divergence.direction.value` に修正する
- **ペイロード形状は現行と同一を維持する**（direction文字列のみ。イベント詳細フィールドの配信追加は Phase 1 で判断）

### 3.4 `webapp/main.py`

- 無変更（getattr の受け渡しのみのため）。念のため動作確認に含めること

## 4. 追加テスト

- `CvdDivergenceDetector()`（引数なし）で BULLISH/BEARISH が従来同様に検出されること（3.1 のデフォルト動作保証）
- push_broker のシリアライズ: `DivergenceEvent` を渡した際に direction が `"BULLISH"` / `"BEARISH"` の**文字列**として出力されること、None時は従来通り null であること（既存webappテストの体裁に合わせる。無ければ最小の単体テストを新設）

## 5. 完了条件への追加

- [ ] `grep -rn "Divergence(" と旧型参照` が残存ゼロ（`DivergenceEvent` / `DivergenceDirection` / `DivergenceKind` のみ）
- [ ] signal.py は無変更（v1 の「SignalEngine無変更」条件を維持）
- [ ] ANALYSISメッセージのペイロード形状が移行前後で同一であること

## 6. 既知課題として記録（本Phaseでは修正しない）

`self.divergence` は一度検出されると次の検出まで無期限に保持され、鮮度情報がない。失効ポリシー（例: Nバー経過でNone化）は Phase 1 の保存・品質評価設計と併せて判断する。CompletionLog の報告に既知課題として1行記載すること。
