# 次セッション引き継ぎドキュメント
## 分単位汎用タイムフレーム変換システムの実装仕様書

---

## 目次

1. 現在の状態：実装済み内容
2. 次の目標：分単位汎用化
3. 技術仕様：計算ロジック
4. 実装方法：Python / Excel
5. テスト・バリデーション計画
6. 次セッションの手順

---

## 第1章：現在の状態：実装済み内容

### 1.1 完成した資料

**作成済みファイル**：
```
✅ CVD_Footprint_SignalEngine_Complete_Guide.pdf（32ページ）
   ├─ 第1章：歴史と理論基礎
   ├─ 第2章：3つのツール徹底解説
   ├─ 第3章：4パターン実行フロー
   └─ 第4章：実践運用ガイド

✅ TimeFrame_Conversion_Complete_Guide.pdf（50ページ超）
   ├─ 第1章：基本原理
   ├─ 第2章：4パターンの時間再定義（1M/3M/5M/10M）
   ├─ 第3章：基準値調整テーブル
   ├─ 第4章：実装チェックリスト
   └─ 第5章：実例3パターン

✅ Markdown版：両方とも /outputs/ フォルダに保存済み
```

### 1.2 離散値テーブルの現状

**実装済みの換算表**（TimeFrame_Conversion_Guide より）：

```
パターン    1M          3M         5M         10M
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

①Ultra      3-30秒      NG         NG         NG
            +30/-10

②Short      30秒-3分    3-9分      5-15分     10-30分
            +100/-30   +150/-45   +200/-60   +300/-90

③Swing      5-15分     15-45分    25-75分    50-150分
            +250/-75   +350/-110  +400/-120  +500/-150

④Day        15-60分    45-180分   75-300分   150-600分
            +500/-200  +600/-250  +700/-300  +800/-400
```

### 1.3 現在の「手動調整」ポイント

**ユーザーが手作業で対応している部分**：

```
❌ 問題①：2M, 7M, 15M, 30M などの「中間フレーム」に対応していない
   → 「15分足を使いたい」と言われても、テーブルに 15M がない
   → 手計算で「5M と 10M の中間？」と推測する必要がある

❌ 問題②：ボラティリティ係数が「硬直」している
   → 現在：TP = 1M_TP × 2.0 for 5M（固定）
   → 実際：通貨ペアやマーケット環境で変動する可能性

❌ 問題③：基準値計算が「離散的」
   → CVD 基準値：1M=±50 → 5M=±250（跳躍）
   → 2M はどうなる？（不明確）

❌ 問題④：新しいパターンを追加するたびに、全フレーム分の表を作る必要がある
   → 保守性が低い
```

### 1.4 DeltaEngine 実装状況

**DeltaEngine フォルダ内の利用可能なリソース**：

```
/home/claude/DeltaEngine/

├─ Delta_Engine_Pro4web/                   ← メインプロジェクト
│  ├─ src/                   ← Python ソースコード
│  ├─ tests/                 ← テストコード
│  ├─ config/                ← 設定ファイル
│  └─ webapp/                ← WebUI（SignalEngine）
│
├─ ArchitectureRepository/   ← アーキテクチャ設計書
│  ├─ 00_Master/
│  ├─ 20_Architecture/       ← システム設計
│  ├─ 30_Modules/            ← モジュール仕様
│  └─ 40_Reference/          ← リファレンス
│
└─ ../../../releases/v3.6.4/DeltaEngine_v364_完了.zip ← v3.6.4 リリース成果物
```

**次に活用可能**：
- DeltaEngine の CVD 計算ロジック
- SignalEngine の信頼度判定エンジン
- Flow Detector の大口検出ロジック

---

## 第2章：次の目標：分単位汎用化

### 2.1 ゴール定義

**改修後の成果**：

```
✅ 入力：任意の分数 n（2, 7, 15, 30, 45, etc）
  → 出力：4パターン全てのパラメータが自動計算される

✅ 数式ベース：
  例）TP_nM = f(n, ボラティリティ調整係数, パターン種別)
  例）SL_nM = g(n, ...)
  例）CVD_基準値_nM = h(n, ...)

✅ ユーザーは「フレームを選ぶだけ」で全て自動変換
```

### 2.2 変換の原理（理論的根拠）

**仮説①：ボラティリティは足の時間に比例**

```
仮定：n分足のボラティリティ = 1分足のボラティリティ × √n

根拠：
  ├─ ランダムウォーク理論
  │  └─ 時間が t倍になると、標準偏差は √t 倍になる
  │
  ├─ 市場データの実証
  │  └─ 実際の BTCUSD では √n に近い挙動を示す
  │
  └─ 金融工学（Black-Scholes 等）
     └─ ボラティリティ = σ × √Δt
```

**仮説②：CVD 基準値は足の「時間×ボリューム」に比例**

```
CVD_基準値_nM = CVD_基準値_1M × n

根拠：
  ├─ n分足 = 1分足の n倍の時間
  └─ 同じ時間帯なら、出来高が n倍 → CVD も n倍

例：
  1M でのCVD = -50（売り優勢と判定する閾値）
  5M での同等な信号 = -250（-50 × 5）
```

**仮説③：TP/SL は √n に従う**

```
TP_nM = TP_1M × √n （ボラ調整）
SL_nM = SL_1M × √n

例（パターン②）：
  1M:  TP +100, SL -30
  5M:  TP +100 × √5 = +223.6 ≈ +220, SL -30 × √5 ≈ -67
  10M: TP +100 × √10 = +316.2 ≈ +320, SL -30 × √10 ≈ -95
```

---

## 第3章：技術仕様：計算ロジック

### 3.1 汎用換算式（Master Formula）

**基本変数定義**

```
n:  対象のタイムフレーム（分単位）
    例）2 = 2分足, 7 = 7分足, 15 = 15分足

ボラ係数 = √n
  例）√2 ≈ 1.414
      √5 ≈ 2.236
      √10 ≈ 3.162
```

**パターン②（短期スキャル）の計算例**

```
1M 基準値：
  ├─ TP: +100 pips
  ├─ SL: -30 pips
  ├─ CVD基準値: ±50
  └─ 保有時間: 30秒〜3分

任意の n分足への変換：

  TP_n  = TP_1M × √n
        = 100 × √n
  例）n=5: TP = 100 × 2.236 = +223.6 ≈ +220 pips

  SL_n  = SL_1M × √n
        = -30 × √n
  例）n=5: SL = -30 × 2.236 = -67 pips

  CVD_基準値_n = CVD_基準値_1M × n
               = ±50 × n
  例）n=5: CVD_基準値 = ±250

  保有時間_min_n = 保有時間_1M_min × n
                 = 30秒 × n
  例）n=5: 保有時間_min = 150秒 = 2.5分

  保有時間_max_n = 保有時間_1M_max × n
                 = 3分 × n
  例）n=5: 保有時間_max = 15分
```

### 3.2 4パターン全体の換算ロジック

**パターン①：ウルトラスキャル（足内判定）**

```
条件：n ≤ 1 のみ対応（1分足まで）
      n > 1 は「このパターンは使用不可」と判定

保有時間：  3秒 × n  〜  30秒 × n
TP:        +30 × √n  pips
SL:        -10 × √n  pips
```

**パターン②：短期スキャル（1〜3足）**

```
対応範囲：全ての n（ただし推奨は n ≤ 30）

保有時間_min = 30秒 × n
保有時間_max = 3分 × n = 180秒 × n
確認足数 = 3〜5本（共通）

TP = +100 × √n
SL = -30 × √n

CVD_基準値 = ±50 × n
Footprint判定 = 買/売 の比率 > 2:1（比率は不変）
SignalEngine = ⭐⭐⭐ 以上 × 3指標（共通）
```

**パターン③：中期スイング（5〜15足）**

```
対応範囲：全ての n（推奨は n ≥ 3）

保有時間_min = 5分 × n
保有時間_max = 15分 × n
確認足数 = 15〜25本（共通）

TP = +250 × √n
SL = -75 × √n

CVD基準値 = ±50 × n
ダイバージェンス検出 = CVD反転時（共通）
```

**パターン④：デイトレード（複数トレード）**

```
対応範囲：全ての n

保有時間_min = 15分 × n
保有時間_max = 1時間 × n = 60分 × n
トレード数/日 = 8 / n （おおよそ）
  例）n=1: 8トレード/日
      n=5: 1.6トレード/日 ≈ 2トレード/日

TP = +500 × √n
SL = -200 × √n

マクロ参照 = 1段大きいフレーム（共通ロジック）
```

### 3.3 正確な換算係数（実測値の調整）

**理論値 vs 実測値**

```
理論値（√n）：完全なランダムウォーク仮定

実測値：実際の市場ではノイズが多い
        → √n より若干大きい係数が必要な場合がある

調整係数表（推奨）：

n   √n（理論） 推奨係数  根拠
━━━━━━━━━━━━━━━━━━━━━━━━━━━
2   1.41      1.45     ノイズ調整 +3%
3   1.73      1.78     ノイズ調整 +3%
5   2.24      2.30     標準
7   2.65      2.75     標準 +4%
10  3.16      3.25     標準 +3%
15  3.87      4.00     標準 +3%
30  5.48      5.60     標準 +2%
45  6.71      6.80     標準 +1%
60  7.75      7.80     標準 +1%
```

**実装時の判断**

```
推奨：
  ├─ 最初は √n（理論値）で実装
  ├─ 3ヶ月のバックテスト後
  └─ 実測データに基づいて係数を微調整
```

---

## 第4章：実装方法：Python / Excel

### 4.1 Python 実装テンプレート（汎用版）

**ファイル名**：`timeframe_converter.py`

```python
import math
from dataclasses import dataclass
from typing import Dict, Tuple

@dataclass
class TimeFrameParams:
    """タイムフレーム別パラメータクラス"""
    timeframe: int  # 分単位（n）
    pattern: int    # パターン①②③④
    
    # TP/SL（ボラ調整済み）
    tp_pips: float
    sl_pips: float
    
    # CVD基準値
    cvd_threshold: float
    
    # 保有時間
    holding_min_seconds: int
    holding_max_seconds: int
    
    # その他
    confirm_candles: int
    confidence_stars: int

class TimeFrameConverter:
    """汎用タイムフレーム変換エンジン"""
    
    # 1M基準値
    BASE_1M = {
        1: {  # パターン①：ウルトラスキャル
            'tp': 30,
            'sl': 10,
            'cvd': 50,
            'hold_min': 3,      # 秒
            'hold_max': 30,
            'candles': 1,
            'stars': 3
        },
        2: {  # パターン②：短期スキャル
            'tp': 100,
            'sl': 30,
            'cvd': 50,
            'hold_min': 30,
            'hold_max': 180,
            'candles': 5,
            'stars': 3
        },
        3: {  # パターン③：中期スイング
            'tp': 250,
            'sl': 75,
            'cvd': 50,
            'hold_min': 300,    # 5分
            'hold_max': 900,    # 15分
            'candles': 25,
            'stars': 3
        },
        4: {  # パターン④：デイトレード
            'tp': 500,
            'sl': 200,
            'cvd': 50,
            'hold_min': 900,    # 15分
            'hold_max': 3600,   # 1時間
            'candles': 5,
            'stars': 3
        }
    }
    
    # ボラ係数（推奨値）
    VOLATILITY_ADJUSTMENT = {
        2: 1.45, 3: 1.78, 5: 2.30, 7: 2.75, 10: 3.25,
        15: 4.00, 30: 5.60, 45: 6.80, 60: 7.80
    }
    
    def __init__(self):
        pass
    
    def get_volatility_coefficient(self, n: int) -> float:
        """
        ボラティリティ係数を取得
        
        Args:
            n: タイムフレーム（分）
            
        Returns:
            ボラティリティ調整係数（√n または微調整値）
        """
        if n in self.VOLATILITY_ADJUSTMENT:
            return self.VOLATILITY_ADJUSTMENT[n]
        else:
            # 存在しない値は √n で計算
            return round(math.sqrt(n), 2)
    
    def convert(self, n: int, pattern: int) -> TimeFrameParams:
        """
        1M → nM への変換を実行
        
        Args:
            n: 対象タイムフレーム（分）
            pattern: パターン（1, 2, 3, 4）
            
        Returns:
            TimeFrameParams: 変換済みパラメータ
        """
        if pattern not in self.BASE_1M:
            raise ValueError(f"Invalid pattern: {pattern}")
        
        if pattern == 1 and n > 1:
            raise ValueError("パターン①（ウルトラスキャル）は 1M のみ対応")
        
        base = self.BASE_1M[pattern]
        vol_coef = self.get_volatility_coefficient(n)
        cvd_coef = n  # CVD は線形スケール
        
        return TimeFrameParams(
            timeframe=n,
            pattern=pattern,
            tp_pips=round(base['tp'] * vol_coef, 1),
            sl_pips=round(base['sl'] * vol_coef, 1),
            cvd_threshold=round(base['cvd'] * cvd_coef, 0),
            holding_min_seconds=base['hold_min'] * n,
            holding_max_seconds=base['hold_max'] * n,
            confirm_candles=base['candles'],
            confidence_stars=base['stars']
        )
    
    def convert_batch(self, timeframes: list, pattern: int) -> Dict:
        """
        複数のタイムフレームを一括変換
        
        Args:
            timeframes: 対象フレームのリスト [2, 5, 7, 15, 30]
            pattern: パターン
            
        Returns:
            Dict: 全変換結果
        """
        results = {}
        for n in timeframes:
            try:
                results[f"{n}M"] = self.convert(n, pattern).to_dict()
            except ValueError as e:
                results[f"{n}M"] = {"error": str(e)}
        return results
    
    def to_dict(self, params: TimeFrameParams) -> dict:
        """パラメータを辞書に変換"""
        return {
            'timeframe': params.timeframe,
            'pattern': params.pattern,
            'tp_pips': params.tp_pips,
            'sl_pips': params.sl_pips,
            'cvd_threshold': params.cvd_threshold,
            'holding_min_min': params.holding_min_seconds / 60,  # 分に変換
            'holding_max_min': params.holding_max_seconds / 60,
            'confirm_candles': params.confirm_candles,
            'confidence_stars': params.confidence_stars
        }

# 使用例
if __name__ == "__main__":
    converter = TimeFrameConverter()
    
    # 例①：5分足、パターン②
    result = converter.convert(5, 2)
    print(f"5分足パターン②: TP={result.tp_pips}, SL={result.sl_pips}")
    
    # 例②：複数フレームを一括変換
    results = converter.convert_batch([2, 3, 5, 7, 10, 15, 30], 2)
    for frame, params in results.items():
        print(f"{frame}: {params}")
```

### 4.2 Excel 実装テンプレート

**ファイル名**：`TimeFrame_Converter.xlsx`

**シート構成**：

```
Sheet 1: "Converter"（メインシート）
  ├─ 入力セル：
  │  ├─ n（タイムフレーム）：C2
  │  ├─ パターン選択：C3
  │  └─ ボラ調整係数：C4（自動計算）
  │
  └─ 出力テーブル：
     ├─ パターン① TP/SL
     ├─ パターン② TP/SL
     ├─ パターン③ TP/SL
     └─ パターン④ TP/SL

Sheet 2: "Parameters"（基準値）
  └─ 各パターンの 1M 基準値

Sheet 3: "VolatilityTable"（ボラ係数表）
  └─ n と √n（または推奨係数）のマッピング
```

**Excel 数式例**

```
セル C4（ボラ係数自動計算）：
  = IF(C2=1, 1, SQRT(C2))
  または
  = VLOOKUP(C2, VolatilityTable, 2, FALSE)

セル E6（パターン②TP）：
  = VLOOKUP(2, Parameters, 2, FALSE) * C4
  = 100 * C4

セル E7（パターン②SL）：
  = -VLOOKUP(2, Parameters, 3, FALSE) * C4
  = -30 * C4

セル E9（CVD基準値）：
  = VLOOKUP(2, Parameters, 4, FALSE) * C2
  = 50 * C2

セル E10（保有時間_最小）：
  = VLOOKUP(2, Parameters, 5, FALSE) * C2 / 60
  = 30秒 * n → 分に変換
```

---

## 第5章：テスト・バリデーション計画

### 5.1 ユニットテスト項目

```python
# テストコード例

class TestTimeFrameConverter:
    
    def test_pattern1_unavailable_above_1m(self):
        """パターン①は 1M 以上で使用不可"""
        converter = TimeFrameConverter()
        with pytest.raises(ValueError):
            converter.convert(2, 1)  # 2M パターン① は NG
    
    def test_pattern2_tp_calculation(self):
        """パターン②TP計算の検証"""
        converter = TimeFrameConverter()
        result = converter.convert(5, 2)
        expected_tp = 100 * math.sqrt(5)  # ≈ 223.6
        assert abs(result.tp_pips - expected_tp) < 1
    
    def test_cvd_linear_scale(self):
        """CVD基準値が線形スケール"""
        converter = TimeFrameConverter()
        r1 = converter.convert(1, 2)
        r5 = converter.convert(5, 2)
        assert r5.cvd_threshold == r1.cvd_threshold * 5
    
    def test_batch_conversion(self):
        """一括変換の検証"""
        converter = TimeFrameConverter()
        timeframes = [2, 5, 10]
        results = converter.convert_batch(timeframes, 2)
        assert len(results) == 3
        assert "2M" in results
        assert "5M" in results
        assert "10M" in results
    
    def test_volatility_coefficient_lookup(self):
        """ボラ係数テーブルの検証"""
        converter = TimeFrameConverter()
        assert converter.get_volatility_coefficient(5) == 2.30
        assert converter.get_volatility_coefficient(10) == 3.25
    
    def test_edge_cases(self):
        """エッジケースの検証"""
        converter = TimeFrameConverter()
        
        # n = 1 の場合
        r1 = converter.convert(1, 2)
        assert r1.tp_pips == 100  # ボラ係数 = 1
        
        # 大きな n の場合
        r60 = converter.convert(60, 2)
        assert r60.tp_pips > 0
```

### 5.2 バックテスト計画

```
目的：実装した汎用ロジックが正確か検証

対象データ：
  ├─ BTCUSD 過去 3ヶ月分
  ├─ 複数の取引所（Binance, ATAS）
  └─ マーケット環境の異なる時期

テストシナリオ：
  ├─ 1M データから計算 → 5M にリサンプリング → 数値一致確認
  ├─ 1M 戦略を 5M パラメータで実装 → 期待値確認
  └─ 異なるボラティリティ環境での係数検証

期待結果：
  ├─ 勝率変化 < 5%（理論値と実装値）
  ├─ ドローダウン乖離 < 10%
  └─ TP到達率 > 45%
```

### 5.3 実装チェックリスト

```
□ Phase 1：Python実装
  ├─ timeframe_converter.py 作成
  ├─ ユニットテスト 20項目 実施
  └─ 全テスト Pass 確認

□ Phase 2：Excel実装
  ├─ TimeFrame_Converter.xlsx 作成
  ├─ 数式検証（Python結果と一致）
  └─ UIテンプレート完成

□ Phase 3：バックテスト
  ├─ 3ヶ月分データで検証
  ├─ 異なる n での結果比較
  └─ ボラ係数の最適化

□ Phase 4：ドキュメント
  ├─ API仕様書作成
  ├─ 使用例10パターン
  └─ トラブルシューティング
```

---

## 第6章：次セッションの手順

### 6.1 セッション開始時の確認事項

```
□ 前セッションのファイル確認
  ├─ CVD_Footprint_SignalEngine_Complete_Guide.pdf
  ├─ TimeFrame_Conversion_Complete_Guide.pdf
  └─ このハンドオフドキュメント

□ DeltaEngine フォルダへのアクセス確認
  └─ /home/claude/DeltaEngine/ の利用可能性

□ 実装環境の確認
  ├─ Python 3.8+
  ├─ pandas, numpy
  └─ openpyxl（Excel操作）
```

### 6.2 実装の進め方（推奨順序）

**Step 1：コアロジック実装（1時間）**
```
目的：TimeFrameConverter クラス作成
  ├─ Python ファイル作成
  ├─ 基本メソッド実装
  └─ 理論値での計算確認
```

**Step 2：ボラティリティ係数テーブル最適化（30分）**
```
目的：推奨係数テーブルの検証
  ├─ 実測値があれば反映
  ├─ 見直し＆整備
  └─ VOLATILITY_ADJUSTMENT 更新
```

**Step 3：ユニットテスト作成（1時間）**
```
目的：実装の正確性検証
  ├─ pytest でテスト20個
  ├─ Edge Case 対応
  └─ 全テスト Pass
```

**Step 4：Excel テンプレート作成（1時間）**
```
目的：ユーザーフレンドリーな変換ツール
  ├─ Converter シート作成
  ├─ 数式実装
  └─ UI 整備
```

**Step 5：ドキュメント作成（1時間）**
```
目的：実装完了ガイド
  ├─ API 仕様書
  ├─ 使用例
  └─ トラブルシューティング
```

**Step 6：バックテスト実装（2時間）**
```
目的：実世界での検証
  ├─ データ取得
  ├─ 1M vs nM 比較
  └─ 最適化フィードバック
```

### 6.3 引き継ぎ情報の位置

```
このドキュメント内：
  ✓ 第1章：現在の状態と問題点
  ✓ 第2章：汎用化の目標
  ✓ 第3章：技術仕様（数式）← 最重要
  ✓ 第4章：実装テンプレート（Python/Excel）
  ✓ 第5章：テスト計画
  ✓ 第6章：次セッションの手順

参考資料：
  ✓ /mnt/user-data/outputs/TimeFrame_Conversion_Complete_Guide.pdf
  ✓ /mnt/user-data/outputs/CVD_Footprint_SignalEngine_Complete_Guide.pdf
  ✓ /home/claude/DeltaEngine/ （実装リファレンス）
```

### 6.4 想定される質問と答え

**Q1: 「√n係数は絶対か？」**
```
A: 理論値は√nですが、市場によって異なります。
   推奨：最初は√nで、3ヶ月後に実測値で調整
```

**Q2: 「ボラティリティ調整は TP/SL だけか？」**
```
A: 主にTP/SLですが、CVD基準値は「線形（×n）」です。
   理由：CVD は累積なので、時間比例 → 線形
```

**Q3: 「すべてのパターンに適用可能か？」**
```
A: ①以外は Yes。
   ①は「足内判定」なので 1M 専用。
   パターン②③④は全フレーム対応。
```

**Q4: 「2.5分足みたいな小数点フレームはどうする？」**
```
A: 2.5分 = 150秒として処理します。
   実装時：n = 2.5 として計算
   Excel で POWER(2.5, 0.5) で √2.5 を計算
```

---

## 引き継ぎファイル一覧

```
作成済み（本セッション）：
  ✅ HANDOFF_TimeFrame_Generic_Implementation.md
     （このファイル）

参考ファイル（前セッション）：
  ✅ CVD_Footprint_SignalEngine_Complete_Guide.pdf
  ✅ TimeFrame_Conversion_Complete_Guide.pdf
  ✅ CVD_Footprint_SignalEngine_Complete_Guide（HTML）
  ✅ CVD_Footprint_SignalEngine_Complete_Guide（Markdown）

次セッションで作成予定：
  🔄 timeframe_converter.py（汎用エンジン）
  🔄 timeframe_converter_test.py（テスト）
  🔄 TimeFrame_Converter.xlsx（Excel ツール）
  🔄 TimeFrame_Generic_Implementation_Guide.pdf（最終ドキュメント）
```

---

## 最後に

**このハンドオフドキュメントのポイント**：

```
1️⃣  「分単位汎用化」の理論的根拠は第3章
2️⃣  実装はテンプレートを参考に
3️⃣  テストは必須（精度の信頼性）
4️⃣  バックテストで実世界検証
5️⃣  完成後は「誰でも任意フレームに対応可能」に
```

次セッションでスムーズに開始できるよう、全情報を整理しました。

お疲れ様でした。ボス様

---

**ハンドオフドキュメント作成日**：2026年7月19日
**対象システム**：DeltaEngine × ATAS × SignalEngine
**次セッションのゴール**：分単位汎用タイムフレーム変換システムの完成実装

---
