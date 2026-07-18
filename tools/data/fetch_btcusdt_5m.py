"""
BTCUSDT (無期限先物) 5分足 過去2週間分を取得し、CSVに出力するスクリプト

取得項目:
- Open Time (時刻)
- Open / High / Low / Close (始値・高値・安値・終値)
- Volume (出来高: BTC建て)
- Number of Trades (約定回数 = ティック数の代替指標)

事前準備:
    pip install requests pandas

実行方法:
    python fetch_btcusdt_5m.py

出力:
    btcusdt_5m_2weeks.csv (このスクリプトと同じフォルダに生成されます)
"""

import time
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

# ===== 設定 =====
SYMBOL = "BTCUSDT"
INTERVAL = "5m"
DAYS = 14
LIMIT = 1500  # Binance API 1回あたりの上限本数
BASE_URL = "https://fapi.binance.com/fapi/v1/klines"
OUTPUT_FILE = "btcusdt_5m_2weeks.csv"


def fetch_klines(symbol, interval, start_time_ms, end_time_ms, limit=1500):
    """指定期間のkline(ローソク足)データを取得する"""
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": limit,
    }
    resp = requests.get(BASE_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def main():
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=DAYS)

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    all_rows = []
    cursor = start_ms

    # 5分足 × 1500本 = 約5.2日分 なので、2週間分は複数回に分けて取得
    print(f"{symbol_label(SYMBOL)} の {INTERVAL} 足を {DAYS}日分取得します...")

    while cursor < end_ms:
        data = fetch_klines(SYMBOL, INTERVAL, cursor, end_ms, LIMIT)
        if not data:
            break

        all_rows.extend(data)

        last_open_time = data[-1][0]
        # 次のリクエストは最後の足の次から
        cursor = last_open_time + 1

        print(f"  取得済み: {len(all_rows)}本 (最新時刻: {ms_to_str(last_open_time)})")

        # レート制限対策の待機
        time.sleep(0.3)

        if len(data) < LIMIT:
            # これ以上データがない = 最新まで到達
            break

    if not all_rows:
        print("データが取得できませんでした。")
        return

    # Binance klines のカラム定義
    columns = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base_volume", "taker_buy_quote_volume", "ignore",
    ]

    df = pd.DataFrame(all_rows, columns=columns)

    # 必要な列だけ抽出・型変換
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

    numeric_cols = ["open", "high", "low", "close", "volume", "number_of_trades"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col])

    # 重複除去(念のため)・時系列ソート
    df = df.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)

    # 出力する列を整理
    out_df = df[["open_time", "open", "high", "low", "close", "volume", "number_of_trades", "close_time"]]
    out_df.columns = ["時刻(UTC)", "始値", "高値", "安値", "終値", "出来高(Volume)", "約定回数(Trades)", "終了時刻(UTC)"]

    out_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    print(f"\n完了しました。合計 {len(out_df)} 本のデータを {OUTPUT_FILE} に出力しました。")
    print(f"期間: {out_df['時刻(UTC)'].iloc[0]} 〜 {out_df['時刻(UTC)'].iloc[-1]}")


def ms_to_str(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def symbol_label(symbol):
    return symbol


if __name__ == "__main__":
    main()
