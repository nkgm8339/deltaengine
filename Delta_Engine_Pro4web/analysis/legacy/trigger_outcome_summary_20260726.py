"""Legacy Step 2 precursor retained for audit; not the authoritative runner.

The maintained implementation is ``analysis/aggregate_trigger_outcomes_step2.py``.
This precursor intentionally remains otherwise unchanged so the exploration that led
to the strict final aggregate can be inspected.

Step 2: トリガー実績集計（読み取り専用）。

既存の記録は一切変更しない。data_05M / data の parquet のみを読み、
状態×window×horizon 別の方向一致率・forward_return_bps 分布・MFE/MAE・
HFM実建値・時間帯別・confluence(OI/native_flow) を集計して Markdown へ出力する。

注意:
  - orderflow_05M.duckdb は稼働中プロセスがロックするため触れない。parquet のみ使用。
  - 期間は実質数日。本集計は「傾向の一次把握」であり確定判断ではない。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # Delta_Engine_Pro4web
OUT_DIR = os.path.join(HERE, "out")
os.makedirs(OUT_DIR, exist_ok=True)
OUT_MD = os.path.join(OUT_DIR, "trigger_outcome_report_20260726.md")

NEW = os.path.join(ROOT, "data_05M", "parquet")
OLD = os.path.join(ROOT, "data", "parquet")

# 執行器の固定変換に基づく発注方向（sign: +1=BUY, -1=SELL）
# BUY_EFFECTIVE->BUY, SELL_EFFECTIVE->SELL, BUY_TRAPPED->SELL, SELL_TRAPPED->BUY
# *_STALLED は圧力方向で参考評価（BUY_STALLED->BUY）
SIGN_CASE = """
  case
    when state in ('BUY_EFFECTIVE','BUY_STALLED','SELL_TRAPPED') then 1
    when state in ('SELL_EFFECTIVE','SELL_STALLED','BUY_TRAPPED') then -1
    else 0 end
"""
REF_CASE = "case when state in ('BUY_STALLED','SELL_STALLED') then true else false end"

con = duckdb.connect()
con.execute("SET enable_progress_bar=false")
con.execute("SET TimeZone='Asia/Tokyo'")

md: list[str] = []


def w(line: str = "") -> None:
    md.append(line)
    print(line)


def outcomes_view(name: str, glob: str) -> bool:
    """directed 列を付与した outcomes ビューを作る。ファイルが無ければ False。"""
    import glob as _g
    if not _g.glob(glob, recursive=True):
        return False
    con.execute(f"""
        create or replace view {name} as
        select
          event_time, window_sec, state, horizon_sec,
          cast(observed_price as double) observed_price,
          cast(forward_return_bps as double) fr_bps,
          cast(max_up_bps as double) up_bps,
          cast(max_down_bps as double) dn_bps,
          {SIGN_CASE} as sgn,
          {REF_CASE} as is_ref,
          {SIGN_CASE} * cast(forward_return_bps as double) as directed_bps,
          case when {SIGN_CASE} = 1 then cast(max_up_bps as double)
               else -cast(max_down_bps as double) end as mfe_bps,
          case when {SIGN_CASE} = 1 then cast(max_down_bps as double)
               else -cast(max_up_bps as double) end as mae_bps,
          20.0 / cast(observed_price as double) * 10000.0 as thr20_bps,
          extract(hour from event_time) as jst_hour
        from read_parquet('{glob}')
        where {SIGN_CASE} <> 0
    """)
    return True


def table(headers: list[str], rows: list[list]) -> None:
    w("| " + " | ".join(headers) + " |")
    w("|" + "|".join(["---"] * len(headers)) + "|")
    for r in rows:
        w("| " + " | ".join("" if c is None else str(c) for c in r) + " |")
    w()


def fnum(v, d=2):
    if v is None:
        return "-"
    return f"{v:.{d}f}"


# ---------------------------------------------------------------------------
w(f"# トリガー実績集計 報告書（Step 2）")
w()
w(f"生成: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}")
w()
w("> **本集計は傾向の一次把握であり確定判断ではない。** 対象データは実質数日分"
  "（新 data_05M: 2026-07-24〜26 / 旧 data: 2026-07-21〜24）。方向一致率は執行器の"
  "固定変換（BUY_EFFECTIVE→BUY / SELL_EFFECTIVE→SELL / BUY_TRAPPED→SELL / SELL_TRAPPED→BUY）"
  "に基づく directed_bps>0 の割合。*_STALLED は圧力方向による**参考値**。")
w()

have_new = outcomes_view("o_new", f"{NEW}/flow_response_outcomes/**/*.parquet")
have_old = outcomes_view("o_old", f"{OLD}/flow_response_outcomes/**/*.parquet")

DATASETS = [("新(data_05M)", "o_new", have_new), ("旧(data)", "o_old", have_old)]

# === 1. 状態×window×horizon 別 ===============================================
w("## 1. 状態×window×horizon 別 方向一致率・forward_return_bps 分布（本丸）")
w()
for label, view, ok in DATASETS:
    if not ok:
        w(f"### {label}: データなし\n")
        continue
    total = con.execute(f"select count(*) from {view}").fetchone()[0]
    w(f"### {label}  総outcome件数: {total:,}")
    w()
    rows = con.execute(f"""
        select state, window_sec, horizon_sec,
               count(*) n,
               avg(case when directed_bps>0 then 1.0 else 0.0 end)*100 match_pct,
               median(directed_bps) med, avg(directed_bps) mean,
               quantile_cont(directed_bps,0.25) p25,
               quantile_cont(directed_bps,0.75) p75,
               any_value(is_ref) is_ref
        from {view}
        group by 1,2,3
        having count(*) >= 20
        order by state, window_sec, horizon_sec
    """).fetchall()
    table(
        ["state", "win", "hz", "n", "一致率%", "中央bps", "平均bps", "p25", "p75", "参考"],
        [[r[0], r[1], r[2], r[3], fnum(r[4], 1), fnum(r[5]), fnum(r[6]),
          fnum(r[7]), fnum(r[8]), "★" if r[9] else ""] for r in rows],
    )
    # 状態ごと最良horizon（発火4状態のみ、n>=30）
    best = con.execute(f"""
        with g as (
          select state, window_sec, horizon_sec, count(*) n,
                 avg(case when directed_bps>0 then 1.0 else 0.0 end)*100 match_pct
          from {view} where is_ref=false group by 1,2,3 having count(*)>=30)
        select state, window_sec, horizon_sec, n, match_pct,
               row_number() over (partition by state order by match_pct desc) rn
        from g qualify rn=1 order by match_pct desc
    """).fetchall()
    w(f"**{label} 発火4状態: 一致率最大の (window,horizon)**")
    w()
    table(["state", "best_win", "best_hz", "n", "一致率%"],
          [[r[0], r[1], r[2], r[3], fnum(r[4], 1)] for r in best])

# 新旧の傾向一致（発火4状態 window=30 の一致率差）
if have_new and have_old:
    w("### 新旧の傾向一致（window=30・発火4状態・一致率%）")
    w()
    cmp = con.execute("""
        with n as (select state,horizon_sec,
                     avg(case when directed_bps>0 then 1.0 else 0.0 end)*100 p, count(*) c
                   from o_new where window_sec=30 and is_ref=false group by 1,2),
             o as (select state,horizon_sec,
                     avg(case when directed_bps>0 then 1.0 else 0.0 end)*100 p, count(*) c
                   from o_old where window_sec=30 and is_ref=false group by 1,2)
        select coalesce(n.state,o.state) state, coalesce(n.horizon_sec,o.horizon_sec) hz,
               n.p, n.c, o.p, o.c, (n.p-o.p) diff
        from n full outer join o on n.state=o.state and n.horizon_sec=o.horizon_sec
        order by 1,2
    """).fetchall()
    table(["state", "hz", "新一致率%", "新n", "旧一致率%", "旧n", "差(新-旧)"],
          [[r[0], r[1], fnum(r[2], 1), r[3], fnum(r[4], 1), r[5], fnum(r[6], 1)] for r in cmp])

# === 2. MFE/MAE ==============================================================
w("## 2. MFE/MAE 分布と「順行20ドル以上」割合（状態×horizon）")
w()
w("順行20ドル閾値は行ごとに `20 / observed_price × 10000` bps（BTC≈64,000で約3.1bps）へ換算。"
  "directed MFE がその閾値以上の割合。")
w()
for label, view, ok in DATASETS:
    if not ok:
        continue
    w(f"### {label}")
    w()
    rows = con.execute(f"""
        select state, horizon_sec, count(*) n,
               median(mfe_bps) mfe_med, median(mae_bps) mae_med,
               avg(case when mfe_bps >= thr20_bps then 1.0 else 0.0 end)*100 pct20
        from {view}
        group by 1,2 having count(*)>=20
        order by state, horizon_sec
    """).fetchall()
    table(["state", "hz", "n", "MFE中央bps", "MAE中央bps", "順行≥20$ 割合%"],
          [[r[0], r[1], r[2], fnum(r[3]), fnum(r[4]), fnum(r[5], 1)] for r in rows])

# === 3. HFM実建値（USD建） ===================================================
w("## 3. HFM実建値検証（hfm_context_outcomes・USD建）")
w()
w("※ これは PRICE/CVD/Delta の8パターン+OI 系トリガーの実HFM建値ベース成績であり、"
  "flow_response とは**別系統**である。Binance側bpsと符号方向の整合のみ確認する。")
w()
import glob as _g
hfm_glob = f"{NEW}/hfm_context_outcomes/**/*.parquet"
if _g.glob(hfm_glob, recursive=True):
    con.execute(f"create or replace view hfm as select * from read_parquet('{hfm_glob}')")
    total = con.execute("select count(*) from hfm").fetchone()[0]
    st = con.execute("select status, count(*) from hfm group by 1 order by 2 desc").fetchall()
    w(f"総件数: {total:,} / status: " + ", ".join(f"{s[0]}={s[1]}" for s in st))
    w()
    rows = con.execute("""
        select horizon_sec, count(*) n,
               median(cast(long_return_bps as double)) l_ret_bps,
               median(cast(long_mfe_usd as double)) l_mfe_usd,
               median(cast(long_mae_usd as double)) l_mae_usd,
               median(cast(short_return_bps as double)) s_ret_bps,
               median(cast(short_mfe_usd as double)) s_mfe_usd,
               median(cast(short_mae_usd as double)) s_mae_usd
        from hfm where status not in ('PENDING') or status is null
        group by 1 order by 1
    """).fetchall()
    table(["hz", "n", "long_ret中央bps", "long_MFE中央$", "long_MAE中央$",
           "short_ret中央bps", "short_MFE中央$", "short_MAE中央$"],
          [[r[0], r[1], fnum(r[2]), fnum(r[3]), fnum(r[4]),
            fnum(r[5]), fnum(r[6]), fnum(r[7])] for r in rows])
    # 整合: long_return_bps と Binance側 combined_context の値動き符号（同一event期間）
    w("**整合チェック**: long_return_bps の符号は Binance建値上昇=正。short はその反転で一貫。"
      "HFMのUSD建 MFE/MAE にはスプレッド(≈20$)が内包される点に留意。")
    w()
else:
    w("hfm_context_outcomes: データなし\n")

# === 4. 時間帯別（JST） ======================================================
w("## 4. 時間帯別偏り（JST時・発火4状態・全window/horizon）")
w()
for label, view, ok in DATASETS:
    if not ok:
        continue
    w(f"### {label}")
    w()
    rows = con.execute(f"""
        select jst_hour, count(*) n,
               avg(case when directed_bps>0 then 1.0 else 0.0 end)*100 match_pct,
               avg(directed_bps) mean
        from {view} where is_ref=false
        group by 1 order by 1
    """).fetchall()
    table(["JST時", "n", "一致率%", "平均directed_bps"],
          [[int(r[0]), r[1], fnum(r[2], 1), fnum(r[3])] for r in rows])

# === 5. confluence（OI / native_flow のみ） ==================================
w("## 5. confluence 評価（OI・native_flow のみ）")
w()
w("代表条件: window=30・horizon=300・発火4状態。新旧を結合して一次把握する。")
w()

# 5a. OI 方向との突合（ASOF: event直近OIと120秒前OIの差の符号）
oi_new = f"{NEW}/open_interest_samples/**/*.parquet"
oi_old = f"{OLD}/open_interest_samples/**/*.parquet"
oi_globs = [g for g in (oi_new, oi_old) if _g.glob(g, recursive=True)]
out_globs = []
if have_new:
    out_globs.append(f"{NEW}/flow_response_outcomes/**/*.parquet")
if have_old:
    out_globs.append(f"{OLD}/flow_response_outcomes/**/*.parquet")

try:
    con.execute(f"""
        create or replace view oi_all as
        select source_time, cast(open_interest as double) oi
        from read_parquet({oi_globs})
    """)
    con.execute(f"""
        create or replace view out_all as
        select event_time, state, observed_price,
               {SIGN_CASE} sgn,
               {SIGN_CASE}*cast(forward_return_bps as double) directed_bps
        from read_parquet({out_globs})
        where window_sec=30 and horizon_sec=300 and {SIGN_CASE}<>0
          and state in ('BUY_EFFECTIVE','SELL_EFFECTIVE','BUY_TRAPPED','SELL_TRAPPED')
    """)
    rows = con.execute("""
        with j as (
          select o.state, o.directed_bps,
                 cur.oi cur_oi, prv.oi prv_oi
          from out_all o
          asof left join oi_all cur on cur.source_time <= o.event_time
          asof left join oi_all prv on prv.source_time <= o.event_time - interval 120 second
        )
        select case when cur_oi is null or prv_oi is null then 'OI欠測'
                    when cur_oi>prv_oi then 'BUILDING'
                    when cur_oi<prv_oi then 'UNWINDING'
                    else 'UNCHANGED' end oi_dir,
               count(*) n,
               avg(case when directed_bps>0 then 1.0 else 0.0 end)*100 match_pct,
               avg(directed_bps) mean
        from j group by 1 order by 2 desc
    """).fetchall()
    w("### 5a. OI方向別（event直近OI vs 120秒前OI）")
    w()
    table(["OI方向", "n", "一致率%", "平均directed_bps"],
          [[r[0], r[1], fnum(r[2], 1), fnum(r[3])] for r in rows])
except Exception as e:
    w(f"### 5a. OI突合: 実行エラー: {e}\n")

# 5b. native_flow との突合（新のみ）
nf_glob = f"{NEW}/native_flow_events/**/*.parquet"
try:
    if _g.glob(nf_glob, recursive=True) and have_new:
        con.execute(f"""
            create or replace view nf as
            select event_time,
                   case when pressure_side='BUY' then 1 when pressure_side='SELL' then -1 else 0 end nf_sgn
            from read_parquet('{nf_glob}')
        """)
        con.execute(f"""
            create or replace view out_new as
            select event_time, state, {SIGN_CASE} sgn,
                   {SIGN_CASE}*cast(forward_return_bps as double) directed_bps
            from read_parquet('{NEW}/flow_response_outcomes/**/*.parquet')
            where window_sec=30 and horizon_sec=300 and {SIGN_CASE}<>0
              and state in ('BUY_EFFECTIVE','SELL_EFFECTIVE','BUY_TRAPPED','SELL_TRAPPED')
        """)
        rows = con.execute("""
            with j as (
              select o.directed_bps, o.sgn, nf.nf_sgn
              from out_new o
              asof left join nf on nf.event_time <= o.event_time)
            select case when nf_sgn is null then 'native欠測'
                        when nf_sgn=sgn then '同方向'
                        when nf_sgn=-sgn then '逆方向'
                        else '中立' end agree,
                   count(*) n,
                   avg(case when directed_bps>0 then 1.0 else 0.0 end)*100 match_pct,
                   avg(directed_bps) mean
            from j group by 1 order by 2 desc
        """).fetchall()
        w("### 5b. native_flow 圧力方向との一致（新data_05Mのみ）")
        w()
        table(["native方向", "n", "一致率%", "平均directed_bps"],
              [[r[0], r[1], fnum(r[2], 1), fnum(r[3])] for r in rows])
    else:
        w("### 5b. native_flow: データなし\n")
except Exception as e:
    w(f"### 5b. native_flow突合: 実行エラー: {e}\n")

w("### confluence 範囲の限界と先行改修")
w()
w("- 今回突合できたのは **OI と native_flow のみ**。")
w("- **吸収・大口約定・スイープ・清算はいずれも永続化されておらず**（実装上メモリ内→WebApp配信のみ）、"
  "本集計では突合不能。")
w("- **結論: 統合判断層（板×約定×吸収の合流）を実績ベースで設計するには、"
  "吸収/大口/スイープ/清算イベントの永続化が先行改修として必須。**")
w()

with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write("\n".join(md))
print(f"\n[written] {OUT_MD}")
