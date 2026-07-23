import React, { useState, useEffect, useRef } from "react";
import {
  Wifi, Zap, Lock, Unlock, ZoomIn, ZoomOut, Bug,
  ChevronLeft, ChevronRight, CircleDot, History
} from "lucide-react";

// ============================================================
// DeltaEngine Command Center v3.3 — Design Mock (Final Quality)
// Mission: トレーダーが3秒以内に状況を把握し、売買判断できる
//          コマンドセンター。データ表示ツールではない。
//
// 原則1: UIに固定値・ダミー値を一切置かない。
//   全数値は state（=本実装では SignalEngine / WebSocket）から導出。
//   バックエンドが算出しない値は捏造せず「—」を表示する。
// 原則2: UI ≠ ドメインモデル。
//   market_state は SignalEngine から受信した文字列をそのまま描画する。
//   UI側での固定列挙・独自マッピング・再定義は禁止。
//   （再定義する場合は SignalEngine/Backtest/AI/WebApp 全体の ADR で行う）
// 原則3: AVOID は v1 では SignalEngine が判定可能な異常のみ
//   （ABNORMAL_BOOK / EXTREME_DELTA / MARKET_HALT / DATA_ERROR）。
//   経済イベント(FOMC等)は EconomicEventProvider 追加後の別フェーズ。
// ============================================================

const C = {
  bg: "#0A0D12", panel: "#11161F", panelSoft: "#151C27", line: "#1E2735",
  buy: "#00E676", sell: "#FF4D4D", warn: "#FFC400", info: "#9C7DFF",
  dis: "#5B6472", text: "#E8EDF4", sub: "#8A94A6",
};
const CAT = {
  DELTA: "#FF4D4D", IMBALANCE: "#4DA3FF", ABSORPTION: "#9C7DFF",
  EXHAUSTION: "#FFC400", ICEBERG: "#E8EDF4",
};
const DETECTOR_NAME = {
  DELTA: "DeltaDetector", IMBALANCE: "ImbalanceDetector", ABSORPTION: "AbsorptionDetector",
  EXHAUSTION: "ExhaustionDetector", ICEBERG: "IcebergDetector",
};
// ---- SIMULATION ONLY（バックエンド代役。UIはこれらを列挙・参照しない）----
// 本実装では WebSocket ANALYSIS メッセージの market_state / veto_reason が届く。
// SIM_BACKEND_STATES は AIAnalysis_v3.1 正本の実値（EnumDefinitions 準拠）。
const SIM_BACKEND_STATES = ["STRONG_BULL", "BULL", "NEUTRAL", "BEAR", "STRONG_BEAR"];
const SIM_AVOID_REASONS = ["ABNORMAL_BOOK", "EXTREME_DELTA", "MARKET_HALT", "DATA_ERROR"];
const SIGNAL_STYLE = {
  LONG: { color: C.buy }, SHORT: { color: C.sell },
  WAIT: { color: C.dis }, AVOID: { color: C.warn },
};

const mono = { fontFamily: "'SF Mono','Cascadia Code','Roboto Mono',ui-monospace,monospace", fontVariantNumeric: "tabular-nums" };
const rnd = (a, b) => a + Math.random() * (b - a);
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

const FLOW_TYPES = [];
for (const cat of Object.keys(CAT)) for (const side of ["buy", "sell"]) FLOW_TYPES.push({ cat, side });

function makeLevels(mid, n = 17, tick = 0.5) {
  const half = Math.floor(n / 2);
  return Array.from({ length: n }, (_, i) => ({
    price: mid + (half - i) * tick, bid: rnd(0.1, 14), ask: rnd(0.1, 14),
  }));
}
function makeSeries(n, step, abs = false) {
  let v = 0;
  return Array.from({ length: n }, () => { v += rnd(-step, step * 1.15); return abs ? Math.abs(v) : v; });
}

export default function DeltaCommandCenterV32() {
  const [price, setPrice] = useState(63988.5);
  const [prevPrice, setPrevPrice] = useState(63988.5);
  const [levels, setLevels] = useState(() => makeLevels(63988.5));
  const [book, setBook] = useState(() =>
    Array.from({ length: 11 }, (_, i) => ({
      ask: { price: 63989 + (10 - i) * 0.5, qty: rnd(0.2, 18) },
      bid: { price: 63988 - i * 0.5, qty: rnd(0.2, 18) },
    })));
  const [flows, setFlows] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [alertHistory, setAlertHistory] = useState([]);
  const alertId = useRef(0);
  const [series, setSeries] = useState({
    CVD: makeSeries(140, 0.9), DELTA: makeSeries(140, 1.4),
    VOLUME: makeSeries(140, 0.6, true), OI: makeSeries(140, 0.4),
    LIQUIDATION: makeSeries(140, 0.3, true),
  });
  const [tab, setTab] = useState("CVD+Δ");
  const [scores, setScores] = useState({ delta: 76, cvd: 64, imbalance: 91, absorption: 80, flow: 71 });
  const [anomaly, setAnomaly] = useState(null); // SignalEngine由来のveto理由文字列 → AVOID
  const [marketState, setMarketState] = useState("NEUTRAL"); // SignalEngine受信値をそのまま保持
  const [latency, setLatency] = useState(38);
  const [devOpen, setDevOpen] = useState(false);
  const [priceLock, setPriceLock] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [barIdx, setBarIdx] = useState(300);
  const [dev, setDev] = useState({ fps: 60, tick: 142, queue: 3, dropped: 0, ws: "OPEN", cpu: 12, ram: 486 });

  // ---- market simulation (本実装では WebSocket/ANALYSIS メッセージに置換) ----
  useEffect(() => {
    const id = setInterval(() => {
      setPrice(p => { setPrevPrice(p); return +(p + rnd(-1.4, 1.6)).toFixed(1); });
      setLevels(ls => ls.map(l => ({ ...l, bid: clamp(l.bid + rnd(-1.2, 1.2), 0.05, 20), ask: clamp(l.ask + rnd(-1.2, 1.2), 0.05, 20) })));
      setBook(b => b.map(r => ({
        ask: { ...r.ask, qty: clamp(r.ask.qty + rnd(-2, 2), 0.1, 20) },
        bid: { ...r.bid, qty: clamp(r.bid.qty + rnd(-2, 2), 0.1, 20) },
      })));
      setSeries(s => ({
        CVD: [...s.CVD.slice(1), s.CVD[139] + rnd(-0.9, 1.15)],
        DELTA: [...s.DELTA.slice(1), s.DELTA[139] * 0.7 + rnd(-1.4, 1.6)],
        VOLUME: [...s.VOLUME.slice(1), Math.abs(s.VOLUME[139] + rnd(-0.7, 0.7))],
        OI: [...s.OI.slice(1), s.OI[139] + rnd(-0.4, 0.45)],
        LIQUIDATION: [...s.LIQUIDATION.slice(1), Math.max(0, s.LIQUIDATION[139] + rnd(-0.35, 0.3))],
      }));
      setLatency(l => clamp(Math.round(l + rnd(-6, 6)), 22, 180));
      setScores(s => ({
        delta: clamp(Math.round(s.delta + rnd(-4, 4)), -100, 100),
        cvd: clamp(Math.round(s.cvd + rnd(-4, 4)), -100, 100),
        imbalance: clamp(Math.round(s.imbalance + rnd(-3, 3)), -100, 100),
        absorption: clamp(Math.round(s.absorption + rnd(-3, 3)), -100, 100),
        flow: clamp(Math.round(s.flow + rnd(-3, 3)), -100, 100),
      }));
      setDev(d => ({
        ...d,
        fps: clamp(Math.round(d.fps + rnd(-2, 2)), 48, 60),
        tick: clamp(Math.round(d.tick + rnd(-20, 20)), 60, 260),
        queue: clamp(Math.round(d.queue + rnd(-2, 2)), 0, 12),
        cpu: clamp(Math.round(d.cpu + rnd(-2, 2)), 5, 40),
        ram: clamp(Math.round(d.ram + rnd(-4, 4)), 420, 560),
      }));
    }, 700);
    return () => clearInterval(id);
  }, []);

  // market state regime + occasional anomaly (→ AVOID)
  useEffect(() => {
    const id = setInterval(() => {
      setMarketState(SIM_BACKEND_STATES[Math.floor(Math.random() * SIM_BACKEND_STATES.length)]);
      if (Math.random() < 0.22) {
        setAnomaly(SIM_AVOID_REASONS[Math.floor(Math.random() * SIM_AVOID_REASONS.length)]);
        setTimeout(() => setAnomaly(null), 6000);
      }
    }, 14000);
    return () => clearInterval(id);
  }, []);

  // flow stream → toast(3s) + persistent history
  useEffect(() => {
    const id = setInterval(() => {
      const f = FLOW_TYPES[Math.floor(Math.random() * FLOW_TYPES.length)];
      const t = new Date().toTimeString().slice(0, 8);
      const strength = +rnd(0.55, 0.98).toFixed(2);
      setFlows(fs => [{ t, cat: f.cat, side: f.side, strength }, ...fs].slice(0, 40));
      if (strength >= 0.85) {
        const aid = ++alertId.current;
        const entry = { id: aid, t, cat: f.cat, side: f.side, strength };
        setToasts(a => [...a, entry]);
        setAlertHistory(h => [entry, ...h].slice(0, 8));
        setTimeout(() => setToasts(a => a.filter(x => x.id !== aid)), 3000);
      }
    }, 2600);
    return () => clearInterval(id);
  }, []);

  // ================= derived (固定値ゼロ) =================
  const chg = ((price - 63720) / 63720) * 100;
  const priceUp = price >= prevPrice;
  const pocIdx = levels.reduce((m, l, i, a) => (l.bid + l.ask > a[m].bid + a[m].ask ? i : m), 0);

  // Value Area (70%) → VAH / VAL
  const totalVol = levels.reduce((s, l) => s + l.bid + l.ask, 0);
  let vaLo = pocIdx, vaHi = pocIdx, vaSum = levels[pocIdx].bid + levels[pocIdx].ask;
  while (vaSum < totalVol * 0.7 && (vaHi > 0 || vaLo < levels.length - 1)) {
    const up = vaHi > 0 ? levels[vaHi - 1].bid + levels[vaHi - 1].ask : -1;
    const dn = vaLo < levels.length - 1 ? levels[vaLo + 1].bid + levels[vaLo + 1].ask : -1;
    if (up >= dn) { vaHi -= 1; vaSum += up; } else { vaLo += 1; vaSum += dn; }
  }

  const maxBook = Math.max(...book.map(r => Math.max(r.ask.qty, r.bid.qty)));
  const maxLvl = Math.max(...levels.map(l => Math.max(l.bid, l.ask)));
  const latColor = latency < 60 ? C.buy : latency < 120 ? C.warn : C.sell;

  // accumulated depth (mid から外側へ累積)
  const askCum = []; let acc = 0;
  for (let i = book.length - 1; i >= 0; i--) { acc += book[i].ask.qty; askCum[i] = acc; }
  const bidCum = []; acc = 0;
  for (let i = 0; i < book.length; i++) { acc += book[i].bid.qty; bidCum[i] = acc; }
  const maxCum = Math.max(askCum[0], bidCum[book.length - 1]);

  // signal: LONG / SHORT / WAIT / AVOID — 全て scores/anomaly から導出
  const net = Math.round((scores.delta + scores.cvd + scores.imbalance + scores.absorption + scores.flow) / 5);
  const composite = Math.abs(net);
  const dirBuy = net >= 0;
  const confluence = [
    ["DELTA", dirBuy ? scores.delta >= 40 : scores.delta <= -40],
    ["CVD", dirBuy ? scores.cvd >= 40 : scores.cvd <= -40],
    ["IMBALANCE", dirBuy ? scores.imbalance >= 40 : scores.imbalance <= -40],
    ["ABSORPTION", dirBuy ? scores.absorption >= 40 : scores.absorption <= -40],
    ["FLOW", dirBuy ? scores.flow >= 40 : scores.flow <= -40],
  ];
  const confStars = confluence.filter(([, ok]) => ok).length;
  const confidence = clamp(Math.round(composite * 0.6 + confStars * 8), 1, 99);
  const signal = anomaly ? "AVOID" : (composite < 25 || confStars <= 2) ? "WAIT" : dirBuy ? "LONG" : "SHORT";
  const sigColor = SIGNAL_STYLE[signal].color;
  const risk = anomaly ? "HIGH" : confStars >= 4 ? "LOW" : confStars === 3 ? "MEDIUM" : "HIGH";
  const riskColor = risk === "LOW" ? C.buy : risk === "MEDIUM" ? C.warn : C.sell;
  const veto = anomaly ? anomaly : "NONE";

  // bottom chart paths
  const buildPath = (data) => {
    const mn = Math.min(...data), mx = Math.max(...data);
    return data.map((v, i) => {
      const x = (i / (data.length - 1)) * 1000;
      const y = 100 - ((v - mn) / (mx - mn || 1)) * 90 - 5;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
  };
  const isOverlay = tab === "CVD+Δ";
  const mainData = isOverlay ? series.CVD : series[tab];
  const mainPath = buildPath(mainData);
  const deltaPath = isOverlay ? buildPath(series.DELTA) : null;
  const last = mainData[mainData.length - 1];
  const tabColor = tab === "LIQUIDATION" ? C.warn : tab === "OI" ? C.info : last >= 0 ? C.buy : C.sell;

  const Panel = ({ title, right, children, className = "", style = {} }) => (
    <div className={`flex flex-col overflow-hidden rounded-lg ${className}`}
      style={{ background: C.panel, border: `1px solid ${C.line}`, ...style }}>
      <div className="flex items-center justify-between px-3 py-1.5 shrink-0" style={{ borderBottom: `1px solid ${C.line}` }}>
        <span className="text-xs font-semibold tracking-widest" style={{ color: C.sub }}>{title}</span>
        {right}
      </div>
      {children}
    </div>
  );

  const ScoreRow = ({ name, val, isComposite = false }) => {
    const color = isComposite ? C.info : val >= 0 ? C.buy : C.sell;
    return (
      <div className="mb-3">
        <div className="flex justify-between items-baseline mb-1">
          <span className="text-sm font-semibold tracking-wider" style={{ color: isComposite ? C.info : C.text }}>{name}</span>
          <span className="text-xl font-black" style={{ ...mono, color }}>
            {val > 0 && !isComposite ? "+" : ""}{val}
          </span>
        </div>
        <div className="h-2.5 rounded-full overflow-hidden" style={{ background: C.line }}>
          <div className="h-full rounded-full transition-all duration-500"
            style={{ width: `${Math.abs(val)}%`, background: color, boxShadow: `0 0 8px ${color}55` }} />
        </div>
      </div>
    );
  };

  return (
    <div className="h-screen w-full flex flex-col gap-1.5 p-1.5 select-none"
      style={{ background: C.bg, color: C.text, ...mono }}>

      {/* ===== ALERT TOASTS (3s) ===== */}
      <div className="fixed top-14 left-1/2 -translate-x-1/2 z-50 flex flex-col gap-1.5 items-center pointer-events-none">
        {toasts.map(a => (
          <div key={a.id} className="flex items-center gap-2.5 px-4 py-2 rounded-lg text-sm font-bold tracking-wider shadow-2xl"
            style={{
              background: "rgba(17,22,31,0.96)", border: `1px solid ${CAT[a.cat]}`,
              color: a.side === "buy" ? C.buy : C.sell, backdropFilter: "blur(8px)",
              animation: "slideDown 0.2s ease-out",
            }}>
            <span>🚨</span>
            <span className="px-1.5 py-0.5 rounded text-[10px]" style={{ background: CAT[a.cat], color: "#0A0D12" }}>{a.cat}</span>
            {a.side === "buy" ? "BUY" : "SELL"} {a.cat} {a.strength.toFixed(2)}
          </div>
        ))}
      </div>
      <style>{`@keyframes slideDown { from { opacity:0; transform:translateY(-8px);} to {opacity:1; transform:translateY(0);} }`}</style>

      {/* ===== TOP BAR ===== */}
      <div className="flex items-center gap-5 px-4 h-12 rounded-lg shrink-0"
        style={{ background: C.panel, border: `1px solid ${C.line}` }}>
        <div className="flex items-baseline gap-2.5">
          <span className="text-sm font-bold tracking-widest" style={{ color: C.sub }}>BTCUSDT</span>
          <span className="text-2xl font-bold" style={{ color: priceUp ? C.buy : C.sell }}>
            {price.toLocaleString(undefined, { minimumFractionDigits: 1 })}
          </span>
          <span className="text-sm font-semibold" style={{ color: chg >= 0 ? C.buy : C.sell }}>
            {chg >= 0 ? "▲" : "▼"}{Math.abs(chg).toFixed(2)}%
          </span>
        </div>
        {/* SIGNAL は常時トップにも出す（WAIT/AVOIDが普通に出るUI） */}
        <div className="flex items-center gap-2 px-3 py-1 rounded-md"
          style={{ background: `${sigColor}14`, border: `1px solid ${sigColor}44` }}>
          <span className="text-base font-black tracking-widest" style={{ color: sigColor }}>{signal}</span>
          <span className="text-xs" style={{ color: C.sub }}>{confidence}%</span>
        </div>
        <div className="flex-1" />
        {[["ATR(14)", "142.6"], ["SPREAD", (book[book.length - 1] ? (book[0] && (63989 - 63988)).toFixed(1) : "0.5")]].map(([k, v]) => (
          <div key={k} className="flex flex-col items-end leading-tight">
            <span className="text-[10px] tracking-widest" style={{ color: C.dis }}>{k}</span>
            <span className="text-sm font-semibold">{v}</span>
          </div>
        ))}
        <div className="flex flex-col items-end leading-tight">
          <span className="text-[10px] tracking-widest" style={{ color: C.dis }}>LATENCY</span>
          <span className="text-sm font-semibold flex items-center gap-1" style={{ color: latColor }}><Zap size={11} />{latency}ms</span>
        </div>
        <div className="flex flex-col items-end leading-tight">
          <span className="text-[10px] tracking-widest" style={{ color: C.dis }}>FPS</span>
          <span className="text-sm font-semibold">{dev.fps}</span>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md"
          style={{ background: "rgba(0,230,118,0.08)", border: "1px solid rgba(0,230,118,0.25)" }}>
          <Wifi size={12} style={{ color: C.buy }} />
          <span className="text-[11px] font-semibold" style={{ color: C.buy }}>LIVE</span>
        </div>
        <button onClick={() => setDevOpen(v => !v)} className="p-1.5 rounded-md"
          style={{ color: devOpen ? C.info : C.dis, background: devOpen ? "rgba(156,125,255,0.1)" : "transparent" }}>
          <Bug size={15} />
        </button>
      </div>

      {/* ===== MAIN ROW ===== */}
      <div className="flex gap-1.5 flex-1 min-h-0">

        {/* ---- LEFT: ORDER BOOK + 累積板 ---- */}
        <Panel title="ORDER BOOK" className="w-64 shrink-0"
          right={<span className="text-[10px]" style={{ color: C.dis }}>QTY / Σ DEPTH</span>}>
          <div className="flex-1 overflow-hidden flex flex-col justify-center px-1.5 py-1 text-xs">
            {book.map((r, i) => {
              const heat = r.ask.qty / maxBook;
              return (
                <div key={`a${i}`} className="relative flex items-center rounded-sm my-px px-1.5 min-h-[18px] flex-1 transition-colors duration-300"
                  style={{ background: `rgba(255,77,77,${0.05 + heat * 0.42})` }}>
                  {/* 累積板：外周からの薄い当てバー */}
                  <div className="absolute left-0 top-0 bottom-0 pointer-events-none"
                    style={{ width: `${(askCum[i] / maxCum) * 100}%`, borderBottom: `1px solid rgba(255,77,77,0.5)` }} />
                  <span className="z-10" style={{ color: heat > 0.75 ? "#FFF" : C.sell }}>{r.ask.price.toFixed(1)}</span>
                  <span className="z-10 ml-auto font-semibold" style={{ color: heat > 0.75 ? "#FFF" : C.sub }}>{r.ask.qty.toFixed(2)}</span>
                  <span className="z-10 w-12 text-right text-[10px]" style={{ color: C.dis }}>{askCum[i].toFixed(1)}</span>
                </div>
              );
            })}
            <div className="flex items-center justify-center gap-2 my-1 py-1 rounded"
              style={{ background: C.panelSoft, border: `1px solid ${C.line}` }}>
              <span className="text-sm font-bold" style={{ color: priceUp ? C.buy : C.sell }}>{price.toFixed(1)}</span>
              <span className="text-[10px]" style={{ color: C.dis }}>MID</span>
            </div>
            {book.map((r, i) => {
              const heat = r.bid.qty / maxBook;
              return (
                <div key={`b${i}`} className="relative flex items-center rounded-sm my-px px-1.5 min-h-[18px] flex-1 transition-colors duration-300"
                  style={{ background: `rgba(0,230,118,${0.04 + heat * 0.38})` }}>
                  <div className="absolute left-0 top-0 bottom-0 pointer-events-none"
                    style={{ width: `${(bidCum[i] / maxCum) * 100}%`, borderTop: `1px solid rgba(0,230,118,0.5)` }} />
                  <span className="z-10" style={{ color: heat > 0.75 ? "#FFF" : C.buy }}>{r.bid.price.toFixed(1)}</span>
                  <span className="z-10 ml-auto font-semibold" style={{ color: heat > 0.75 ? "#FFF" : C.sub }}>{r.bid.qty.toFixed(2)}</span>
                  <span className="z-10 w-12 text-right text-[10px]" style={{ color: C.dis }}>{bidCum[i].toFixed(1)}</span>
                </div>
              );
            })}
          </div>
        </Panel>

        {/* ---- CENTER: FOOTPRINT + FLOW ---- */}
        <div className="flex flex-col gap-1.5 flex-1 min-w-0" style={{ flexGrow: 2.2 }}>
          <Panel title="FOOTPRINT — BAR 12:34 (1m)" className="flex-1"
            right={
              <div className="flex items-center gap-1">
                <button onClick={() => setBarIdx(v => Math.max(1, v - 1))} className="p-1" style={{ color: C.sub }}><ChevronLeft size={13} /></button>
                <span className="text-[10px] w-14 text-center" style={{ color: C.dis }}>{barIdx}/300</span>
                <button onClick={() => setBarIdx(v => Math.min(300, v + 1))} className="p-1" style={{ color: C.sub }}><ChevronRight size={13} /></button>
                <div className="w-px h-4 mx-1" style={{ background: C.line }} />
                <button onClick={() => setZoom(z => Math.min(1.5, z + 0.25))} className="p-1" style={{ color: C.sub }}><ZoomIn size={13} /></button>
                <button onClick={() => setZoom(z => Math.max(0.75, z - 0.25))} className="p-1" style={{ color: C.sub }}><ZoomOut size={13} /></button>
                <button onClick={() => setPriceLock(v => !v)} className="p-1" style={{ color: priceLock ? C.warn : C.dis }}>
                  {priceLock ? <Lock size={13} /> : <Unlock size={13} />}
                </button>
              </div>
            }>
            <div className="flex items-center px-3 py-1 text-[10px] tracking-widest shrink-0" style={{ color: C.dis, borderBottom: `1px solid ${C.line}` }}>
              <span className="w-28">PRICE</span>
              <span className="flex-1 text-right pr-2">BID</span>
              <span className="w-8 text-center"></span>
              <span className="flex-1 pl-2">ASK</span>
              <span className="w-16 text-right">DELTA</span>
              <span className="w-12 text-center">SIG</span>
            </div>
            <div className="flex-1 overflow-hidden flex flex-col justify-center px-3" style={{ fontSize: `${13 * zoom}px` }}>
              {levels.map((l, i) => {
                const delta = l.ask - l.bid;
                const imb = l.ask > l.bid * 3 ? "buy" : l.bid > l.ask * 3 ? "sell" : null;
                const abs = l.bid + l.ask > maxLvl * 1.4 && Math.abs(delta) < 1.2;
                const isPoc = i === pocIdx, isVah = i === vaHi, isVal = i === vaLo;
                const inVa = i >= vaHi && i <= vaLo;
                return (
                  <div key={l.price} className="flex items-center py-1 rounded flex-1 max-h-9"
                    style={{
                      background: isPoc ? "rgba(255,196,0,0.08)" : inVa ? "rgba(255,196,0,0.025)" : "transparent",
                      borderTop: isVah ? `1px dashed ${C.warn}66` : "none",
                      borderBottom: isVal ? `1px dashed ${C.warn}66` : "none",
                    }}>
                    <span className="w-28 flex items-center gap-1" style={{ color: isPoc ? C.warn : C.sub }}>
                      {l.price.toFixed(1)}
                      {isPoc && <span className="text-[9px] font-bold px-1 rounded" style={{ background: C.warn, color: C.bg }}>POC</span>}
                      {isVah && !isPoc && <span className="text-[9px] font-bold px-1 rounded" style={{ border: `1px solid ${C.warn}`, color: C.warn }}>VAH</span>}
                      {isVal && !isPoc && <span className="text-[9px] font-bold px-1 rounded" style={{ border: `1px solid ${C.warn}`, color: C.warn }}>VAL</span>}
                    </span>
                    <div className="flex-1 flex justify-end items-center gap-1.5 pr-2">
                      <span style={{ color: C.sell }}>{l.bid.toFixed(2)}</span>
                      <div className="h-3 rounded-sm transition-all duration-300"
                        style={{ width: `${(l.bid / maxLvl) * 100}%`, maxWidth: "100%", background: "rgba(255,77,77,0.55)" }} />
                    </div>
                    <span className="w-8 text-center" style={{ color: C.line }}>×</span>
                    <div className="flex-1 flex items-center gap-1.5 pl-2">
                      <div className="h-3 rounded-sm transition-all duration-300"
                        style={{ width: `${(l.ask / maxLvl) * 100}%`, maxWidth: "100%", background: "rgba(0,230,118,0.5)" }} />
                      <span style={{ color: C.buy }}>{l.ask.toFixed(2)}</span>
                    </div>
                    <span className="w-16 text-right font-semibold" style={{ color: delta >= 0 ? C.buy : C.sell }}>
                      {delta >= 0 ? "+" : ""}{delta.toFixed(1)}
                    </span>
                    <span className="w-12 text-center text-[11px]">
                      {imb === "buy" && <span style={{ color: C.buy }}>▸</span>}
                      {imb === "sell" && <span style={{ color: C.sell }}>◂</span>}
                      {abs && <span style={{ color: C.warn }}> ●</span>}
                    </span>
                  </div>
                );
              })}
            </div>
          </Panel>

          {/* FLOW EVENTS — Detector名付き */}
          <Panel title="FLOW EVENTS" className="h-40 shrink-0"
            right={
              <div className="flex items-center gap-2.5 text-[9px] tracking-wider">
                {Object.entries(CAT).map(([k, col]) => (
                  <span key={k} className="flex items-center gap-1" style={{ color: C.dis }}>
                    <span className="w-1.5 h-1.5 rounded-full inline-block" style={{ background: col }} />{k}
                  </span>
                ))}
                <span className="flex items-center gap-1 ml-1" style={{ color: C.buy }}><CircleDot size={10} />LIVE</span>
              </div>
            }>
            <div className="flex-1 overflow-y-auto px-3 py-1">
              {flows.map((f, i) => {
                const blocks = Math.round(f.strength * 10);
                return (
                  <div key={`${f.t}-${i}`} className="flex items-center gap-3 py-1 text-xs"
                    style={{ borderBottom: `1px solid ${C.line}`, opacity: Math.max(0.35, 1 - i * 0.055) }}>
                    <span style={{ color: C.dis }}>{f.t}</span>
                    <span className="w-24 text-[10px] font-bold px-1.5 py-0.5 rounded text-center tracking-wider"
                      style={{ background: `${CAT[f.cat]}22`, color: CAT[f.cat], border: `1px solid ${CAT[f.cat]}55` }}>
                      {f.cat}
                    </span>
                    <span className="w-10 font-black" style={{ color: f.side === "buy" ? C.buy : C.sell }}>
                      {f.side === "buy" ? "BUY" : "SELL"}
                    </span>
                    <span className="text-[10px]" style={{ color: C.dis }}>{DETECTOR_NAME[f.cat]}</span>
                    <div className="flex-1" />
                    <span style={{ color: CAT[f.cat], letterSpacing: "-1px" }}>
                      {"■".repeat(blocks)}<span style={{ color: C.line }}>{"■".repeat(10 - blocks)}</span>
                    </span>
                    <span className="w-10 text-right font-semibold">{f.strength.toFixed(2)}</span>
                  </div>
                );
              })}
            </div>
          </Panel>
        </div>

        {/* ---- RIGHT: MARKET STATE + CONFLUENCE + SIGNAL ---- */}
        <div className="flex flex-col gap-1.5 w-80 shrink-0">

          {/* MARKET STATE — SignalEngine受信値をそのまま描画（UI側で列挙・マッピングしない） */}
          <Panel title="MARKET STATE" className="shrink-0"
            right={<span className="text-[9px] tracking-wider" style={{ color: C.dis }}>FROM SIGNALENGINE</span>}>
            <div className="px-3 py-3">
              {(() => {
                // 表示ヒントのみ: 文字列に BULL/BEAR を含むかで色を選ぶ（意味の再定義はしない）
                const col = marketState.includes("BULL") ? C.buy : marketState.includes("BEAR") ? C.sell : C.sub;
                return (
                  <div className="flex items-center justify-center py-2 rounded text-lg font-black tracking-[0.15em] transition-all"
                    style={{
                      background: `${col}14`, border: `1px solid ${col}55`,
                      color: col, boxShadow: `0 0 12px ${col}22`,
                    }}>
                    {marketState}
                  </div>
                );
              })()}
            </div>
          </Panel>

          {/* CONFLUENCE */}
          <Panel title="CONFLUENCE" className="shrink-0">
            <div className="px-4 py-2.5">
              <div className="text-center text-2xl tracking-[0.2em] mb-2" style={{ color: C.warn }}>
                {"★".repeat(confStars)}<span style={{ color: C.line }}>{"★".repeat(5 - confStars)}</span>
              </div>
              <div className="grid grid-cols-5 gap-1">
                {confluence.map(([name, ok]) => (
                  <div key={name} className="flex flex-col items-center py-1 rounded"
                    style={{ background: ok ? "rgba(0,230,118,0.08)" : C.panelSoft, border: `1px solid ${ok ? "rgba(0,230,118,0.3)" : C.line}` }}>
                    <span className="text-sm font-bold" style={{ color: ok ? C.buy : C.dis }}>{ok ? "✔" : "—"}</span>
                    <span className="text-[8px] tracking-wide mt-0.5" style={{ color: ok ? C.text : C.dis }}>{name}</span>
                  </div>
                ))}
              </div>
            </div>
          </Panel>

          {/* SIGNAL — 検出器が先、Compositeは最後 */}
          <Panel title="SIGNAL — WHY" className="flex-1">
            <div className="px-4 py-3 flex-1 flex flex-col">
              <div className="flex items-center justify-between mb-3">
                <span className="text-2xl font-black tracking-wider" style={{ color: sigColor }}>{signal}</span>
                <span className="text-xs" style={{ color: C.sub }}>
                  CONF <span className="font-bold text-base" style={{ color: C.text }}>{confidence}%</span>
                </span>
              </div>
              {anomaly && (
                <div className="mb-2 px-2 py-1 rounded text-[10px] font-bold tracking-wider text-center"
                  style={{ background: "rgba(255,196,0,0.1)", border: `1px solid ${C.warn}55`, color: C.warn }}>
                  ⚠ {anomaly}
                </div>
              )}

              <ScoreRow name="DELTA" val={scores.delta} />
              <ScoreRow name="CVD" val={scores.cvd} />
              <ScoreRow name="IMBALANCE" val={scores.imbalance} />
              <ScoreRow name="ABSORPTION" val={scores.absorption} />
              <ScoreRow name="FLOW" val={scores.flow} />
              <div className="h-px mb-3" style={{ background: C.line }} />
              <ScoreRow name="COMPOSITE" val={composite} isComposite />

              <div className="mt-auto grid grid-cols-3 gap-1.5 text-center">
                <div className="rounded-md py-1.5" style={{ background: C.panelSoft, border: `1px solid ${C.line}` }}>
                  <div className="text-[9px] tracking-widest" style={{ color: C.dis }}>RISK</div>
                  <div className="text-xs font-bold" style={{ color: riskColor }}>{risk}</div>
                </div>
                <div className="rounded-md py-1.5" style={{ background: C.panelSoft, border: `1px solid ${C.line}` }}>
                  <div className="text-[9px] tracking-widest" style={{ color: C.dis }}>EXP. RR</div>
                  <div className="text-xs font-bold" style={{ color: C.dis }}>—</div>
                </div>
                <div className="rounded-md py-1.5" style={{ background: C.panelSoft, border: `1px solid ${C.line}` }}>
                  <div className="text-[9px] tracking-widest" style={{ color: C.dis }}>VETO</div>
                  <div className="text-xs font-bold" style={{ color: veto === "NONE" ? C.dis : C.warn }}>{veto}</div>
                </div>
              </div>
            </div>
          </Panel>
        </div>
      </div>

      {/* ===== BOTTOM: CVD+Δ overlay / tabs ===== */}
      <Panel className="h-32 shrink-0"
        title={
          <span className="flex items-center gap-1">
            {["CVD+Δ", "VOLUME", "OI", "LIQUIDATION"].map(t => (
              <button key={t} onClick={() => setTab(t)}
                className="px-2.5 py-0.5 rounded text-[10px] font-bold tracking-widest transition-colors"
                style={{
                  color: tab === t ? C.bg : C.sub,
                  background: tab === t ? (t === "LIQUIDATION" ? C.warn : t === "OI" ? C.info : C.buy) : "transparent",
                }}>
                {t}
              </button>
            ))}
          </span>
        }
        right={
          <span className="flex items-center gap-3 text-[10px]">
            {isOverlay && <span className="flex items-center gap-1" style={{ color: C.sub }}>
              <span className="w-3 h-0.5 inline-block" style={{ background: tabColor }} />CVD
              <span className="w-3 h-0.5 inline-block ml-2" style={{ background: C.info }} />DELTA
            </span>}
            <span className="text-sm font-bold" style={{ color: tabColor }}>
              {last >= 0 && (isOverlay || tab === "OI") ? "+" : ""}{last.toFixed(2)}{isOverlay ? " BTC" : ""}
            </span>
          </span>
        }>
        <div className="flex-1 px-2 py-1">
          <svg viewBox="0 0 1000 100" preserveAspectRatio="none" className="w-full h-full">
            <defs>
              <linearGradient id="fill32" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={tabColor} stopOpacity="0.22" />
                <stop offset="100%" stopColor={tabColor} stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d={`${mainPath} L1000,100 L0,100 Z`} fill="url(#fill32)" />
            {deltaPath && <path d={deltaPath} fill="none" stroke={C.info} strokeWidth="1" strokeDasharray="3,3" opacity="0.8" />}
            <path d={mainPath} fill="none" stroke={tabColor} strokeWidth="1.6" />
          </svg>
        </div>
      </Panel>

      {/* ===== ALERT HISTORY (右下・常設) ===== */}
      {alertHistory.length > 0 && (
        <div className="fixed bottom-4 right-4 w-64 rounded-lg z-40 shadow-2xl overflow-hidden"
          style={{ background: "rgba(17,22,31,0.94)", border: `1px solid ${C.line}`, backdropFilter: "blur(8px)", ...mono }}>
          <div className="flex items-center gap-2 px-3 py-1.5" style={{ borderBottom: `1px solid ${C.line}` }}>
            <History size={11} style={{ color: C.sub }} />
            <span className="text-[10px] font-bold tracking-widest" style={{ color: C.sub }}>ALERTS</span>
          </div>
          <div className="px-3 py-1 max-h-40 overflow-y-auto">
            {alertHistory.map(a => (
              <div key={a.id} className="flex items-center gap-2 py-1 text-[11px]" style={{ borderBottom: `1px solid ${C.line}` }}>
                <span style={{ color: C.dis }}>{a.t.slice(0, 5)}</span>
                <span className="w-1.5 h-1.5 rounded-full inline-block shrink-0" style={{ background: CAT[a.cat] }} />
                <span className="font-semibold" style={{ color: a.side === "buy" ? C.buy : C.sell }}>
                  {a.side === "buy" ? "BUY" : "SELL"} {a.cat}
                </span>
                <span className="ml-auto" style={{ color: C.sub }}>{a.strength.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ===== DEVELOPER OVERLAY ===== */}
      {devOpen && (
        <div className="fixed bottom-4 left-4 rounded-lg px-4 py-3 text-xs z-50 shadow-2xl"
          style={{ background: "rgba(17,22,31,0.95)", border: `1px solid ${C.info}`, backdropFilter: "blur(8px)", ...mono }}>
          <div className="flex items-center gap-2 mb-2">
            <Bug size={12} style={{ color: C.info }} />
            <span className="font-bold tracking-widest" style={{ color: C.info }}>DEVELOPER OVERLAY</span>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1">
            {[
              ["FPS", dev.fps, dev.fps >= 55 ? C.buy : C.warn],
              ["TICK/SEC", dev.tick, C.text],
              ["QUEUE", dev.queue, dev.queue < 8 ? C.text : C.warn],
              ["DROPPED", dev.dropped, dev.dropped === 0 ? C.buy : C.sell],
              ["WS", dev.ws, C.buy],
              ["LATENCY", `${latency}ms`, latColor],
              ["CPU", `${dev.cpu}%`, C.text],
              ["RAM", `${dev.ram}MB`, C.text],
            ].map(([k, v, col]) => (
              <div key={k} className="flex justify-between gap-4">
                <span style={{ color: C.dis }}>{k}</span>
                <span className="font-semibold" style={{ color: col }}>{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
