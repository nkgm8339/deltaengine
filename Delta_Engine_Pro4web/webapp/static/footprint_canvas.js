(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.DeltaFootprint = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const BUY = "#19C979";
  const SELL = "#FF4058";
  const POC = "#F4C542";
  const CYAN = "#25B7E8";
  const TEXT = "#F1F5FF";
  const SUB = "#C9D3EA";
  const MUTED = "#6E7B96";
  const GRID = "#273654";
  const BG = "#070D18";
  const FONT = '"Cascadia Mono","JetBrains Mono",ui-monospace,monospace';
  const AXIS_FONT_PX = 12;
  const META_FONT_PX = 11;
  const CELL_FONT_PX = 14;
  const STANDARD_CELL_FONT_PX = 12;
  const DENSE_CELL_FONT_PX = 11;
  const NICE = [1, 2, 5];
  const JST_OFFSET_MS = 9 * 60 * 60 * 1000;
  const DOM_TRADE_PULSE_COLOR = "#FFD54A";
  const DEFAULT_DOM_TRADE_PULSE_DURATION_MS = 400;
  const DEFAULT_DOM_TRADE_PULSE_MAX_ACTIVE = 256;

  const finite = value => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
  const number = value => finite(value) ? Number(value) : 0;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const timeOf = bar => Date.parse(bar && bar.bar_time);

  function jstClock(value, precision) {
    const time = Number(value);
    if (!Number.isFinite(time)) return "—";
    const iso = new Date(time + JST_OFFSET_MS).toISOString();
    if (precision === "millisecond") return iso.slice(11, 23);
    if (precision === "second") return iso.slice(11, 19);
    return iso.slice(11, 16);
  }

  function priceDigits(step) {
    if (!finite(step) || Number(step) <= 0) return 1;
    const text = Number(step).toFixed(10).replace(/0+$/, "");
    const dot = text.indexOf(".");
    return dot < 0 ? 0 : text.length - dot - 1;
  }

  function inferTickSize(bars, fallback) {
    const prices = [];
    for (const bar of bars || []) {
      const levels = bar && bar.footprint && Array.isArray(bar.footprint.levels)
        ? bar.footprint.levels : [];
      for (const level of levels) if (finite(level.price)) prices.push(Number(level.price));
    }
    prices.sort((a, b) => a - b);
    let best = Infinity;
    for (let i = 1; i < prices.length; i += 1) {
      const gap = prices[i] - prices[i - 1];
      if (gap > 1e-10 && gap < best) best = gap;
    }
    if (Number.isFinite(best)) return Number(best.toPrecision(10));
    return finite(fallback) && Number(fallback) > 0 ? Number(fallback) : 0.1;
  }

  function autoMultiplier(minPrice, maxPrice, tickSize, targetRows) {
    const tick = Math.max(Number(tickSize) || 0.1, 1e-10);
    const spanTicks = Math.max(1, Math.ceil((maxPrice - minPrice) / tick) + 1);
    const target = clamp(Number(targetRows) || 30, 20, 40);
    if (spanTicks <= target) return 1;
    const required = spanTicks / target;
    const exponent = Math.floor(Math.log10(Math.max(1, required)));
    for (let power = exponent; power <= exponent + 2; power += 1) {
      const scale = Math.pow(10, power);
      for (const base of NICE) if (base * scale >= required) return base * scale;
    }
    return Math.ceil(required);
  }

  function bucketLevels(levels, tickSize, multiplier) {
    const tick = Math.max(Number(tickSize) || 0.1, 1e-10);
    const mult = Math.max(1, Math.round(Number(multiplier) || 1));
    const step = tick * mult;
    const digits = Math.min(10, Math.max(priceDigits(tick), priceDigits(step)));
    const buckets = new Map();
    for (const level of levels || []) {
      if (!finite(level.price)) continue;
      const rawIndex = Math.round(Number(level.price) / tick);
      const bucketIndex = Math.floor(rawIndex / mult) * mult;
      const key = String(bucketIndex);
      const row = buckets.get(key) || {
        index: bucketIndex,
        price: Number((bucketIndex * tick).toFixed(digits)),
        bid: 0,
        ask: 0,
      };
      row.bid += Math.max(0, number(level.bid));
      row.ask += Math.max(0, number(level.ask));
      buckets.set(key, row);
    }
    return [...buckets.values()].sort((a, b) => b.index - a.index);
  }

  function bucketIndex(price, tickSize, multiplier) {
    if (!finite(price)) return null;
    const tick = Math.max(Number(tickSize) || 0.1, 1e-10);
    const mult = Math.max(1, Math.round(Number(multiplier) || 1));
    return Math.floor(Math.round(Number(price) / tick) / mult) * mult;
  }

  function prepareBook(book, tickSize, multiplier) {
    const state = String(book && book.sync_state || "NO_SNAPSHOT");
    const synced = state === "SYNCED";
    const raw = [];
    if (synced) {
      for (const level of Array.isArray(book.bids) ? book.bids : []) {
        if (finite(level.price) && finite(level.qty) && Number(level.price) > 0 && Number(level.qty) > 0) {
          raw.push({ price: level.price, bid: level.qty, ask: 0 });
        }
      }
      for (const level of Array.isArray(book.asks) ? book.asks : []) {
        if (finite(level.price) && finite(level.qty) && Number(level.price) > 0 && Number(level.qty) > 0) {
          raw.push({ price: level.price, bid: 0, ask: level.qty });
        }
      }
    }
    const levels = bucketLevels(raw, tickSize, multiplier);
    const byIndex = new Map(levels.map(level => [level.index, level]));
    const maximum = Math.max(1e-12, ...levels.map(level => Math.max(level.bid, level.ask)));
    let bidWall = null;
    let askWall = null;
    for (const level of levels) {
      if (level.bid > 0 && (!bidWall || level.bid > bidWall.bid)) bidWall = level;
      if (level.ask > 0 && (!askWall || level.ask > askWall.ask)) askWall = level;
    }
    return {
      state,
      synced,
      levels,
      byIndex,
      maximum,
      bidWall: bidWall ? bidWall.index : null,
      askWall: askWall ? askWall.index : null,
      bestBid: finite(book && book.best_bid) ? Number(book.best_bid) : null,
      bestAsk: finite(book && book.best_ask) ? Number(book.best_ask) : null,
      bestBidIndex: bucketIndex(book && book.best_bid, tickSize, multiplier),
      bestAskIndex: bucketIndex(book && book.best_ask, tickSize, multiplier),
      spread: finite(book && book.spread) ? Number(book.spread) : null,
      ageMs: finite(book && book.age_ms) ? Number(book.age_ms) : null,
      lastUpdateId: book && book.last_update_id !== undefined ? book.last_update_id : null,
      eventTime: book && book.event_time || null,
    };
  }

  function valueArea(levels, percent) {
    if (!levels || !levels.length) return { poc: null, vah: null, val: null, inValue: new Set() };
    const totals = levels.map(level => level.bid + level.ask);
    let pocIndex = 0;
    for (let i = 1; i < totals.length; i += 1) if (totals[i] > totals[pocIndex]) pocIndex = i;
    const target = totals.reduce((sum, value) => sum + value, 0) * clamp(Number(percent) || 70, 30, 95) / 100;
    let high = pocIndex;
    let low = pocIndex;
    let accumulated = totals[pocIndex];
    while (accumulated < target && (high > 0 || low < levels.length - 1)) {
      const above = high > 0 ? totals[high - 1] : -1;
      const below = low < levels.length - 1 ? totals[low + 1] : -1;
      if (above >= below) { high -= 1; accumulated += above; }
      else { low += 1; accumulated += below; }
    }
    const inValue = new Set();
    for (let i = high; i <= low; i += 1) inValue.add(levels[i].index);
    return { poc: levels[pocIndex].index, vah: levels[high].index, val: levels[low].index, inValue };
  }

  function imbalanceFlags(levels, ratio, minVolume, stackCount, bucketStep) {
    const ascending = [...(levels || [])].sort((a, b) => a.index - b.index);
    let indexStep = Math.max(1, Math.round(Number(bucketStep) || 0));
    if (!Number(bucketStep)) {
      indexStep = Infinity;
      for (let i = 1; i < ascending.length; i += 1) {
        const gap = ascending[i].index - ascending[i - 1].index;
        if (gap > 0 && gap < indexStep) indexStep = gap;
      }
      if (!Number.isFinite(indexStep)) indexStep = 1;
    }
    const flags = new Map();
    const buyIndexes = [];
    const sellIndexes = [];
    const threshold = Math.max(1, Number(ratio) || 3);
    const minimum = Math.max(0, Number(minVolume) || 0);
    const qualifies = (numerator, denominator, combined) => {
      if (combined < minimum) return false;
      return denominator === 0 ? numerator >= minimum && numerator > 0 : numerator / denominator >= threshold;
    };
    for (let i = 0; i < ascending.length; i += 1) {
      const row = ascending[i];
      const lower = i > 0 ? ascending[i - 1] : null;
      const higher = i + 1 < ascending.length ? ascending[i + 1] : null;
      const buy = lower && lower.index === row.index - indexStep &&
        qualifies(row.ask, lower.bid, row.ask + row.bid + lower.ask + lower.bid);
      const sell = higher && higher.index === row.index + indexStep &&
        qualifies(row.bid, higher.ask, row.ask + row.bid + higher.ask + higher.bid);
      if (buy) buyIndexes.push(row.index);
      if (sell) sellIndexes.push(row.index);
      flags.set(row.index, { buy: Boolean(buy), sell: Boolean(sell), buyStack: false, sellStack: false });
    }
    const markStacks = (indexes, key) => {
      const needed = Math.max(2, Math.round(Number(stackCount) || 3));
      let start = 0;
      for (let i = 1; i <= indexes.length; i += 1) {
        if (i === indexes.length || indexes[i] !== indexes[i - 1] + indexStep) {
          if (i - start >= needed) for (let j = start; j < i; j += 1) flags.get(indexes[j])[key] = true;
          start = i;
        }
      }
    };
    markStacks(buyIndexes, "buyStack");
    markStacks(sellIndexes, "sellStack");
    return flags;
  }

  function compact(value) {
    const amount = number(value);
    const absolute = Math.abs(amount);
    if (absolute >= 1e6) return `${(amount / 1e6).toFixed(1)}M`;
    if (absolute >= 1e3) return `${(amount / 1e3).toFixed(1)}K`;
    if (absolute >= 100) return amount.toFixed(0);
    if (absolute >= 10) return amount.toFixed(1);
    return amount.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  }

  function exactValue(value) {
    if (!finite(value)) return "—";
    return Number(value).toLocaleString("en-US", { useGrouping: false, maximumFractionDigits: 8 });
  }

  function bucketLabel(row, frame) {
    const digits = priceDigits(frame.step);
    const low = row.price.toFixed(digits);
    if (frame.multiplier <= 1) return low;
    const high = (row.price + frame.step - frame.tick).toFixed(Math.max(digits, priceDigits(frame.tick)));
    return `${low}–${high}`;
  }

  function p95(values) {
    if (!values || !values.length) return 0;
    const sorted = [...values].sort((a, b) => a - b);
    return sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.95) - 1)];
  }

  function timeframeMilliseconds(value) {
    const match = /^(\d+)([smhd])$/i.exec(String(value || "1m"));
    if (!match) return 60000;
    return Number(match[1]) * ({ s: 1000, m: 60000, h: 3600000, d: 86400000 }[match[2].toLowerCase()] || 60000);
  }

  function passiveSideForAggressor(side) {
    const normalized = String(side || "").toUpperCase();
    if (normalized === "BUY") return "ASK";
    if (normalized === "SELL") return "BID";
    return null;
  }

  function monotonicNow() {
    return typeof performance !== "undefined" && typeof performance.now === "function"
      ? performance.now() : Date.now();
  }

  class DomTradePulseStore {
    constructor(options) {
      const config = options || {};
      this.durationMs = clamp(
        Number(config.durationMs) || DEFAULT_DOM_TRADE_PULSE_DURATION_MS,
        300,
        500
      );
      this.maxActive = clamp(
        Math.round(Number(config.maxActive) || DEFAULT_DOM_TRADE_PULSE_MAX_ACTIVE),
        1,
        DEFAULT_DOM_TRADE_PULSE_MAX_ACTIVE
      );
      this.now = typeof config.now === "function" ? config.now : monotonicNow;
      this.entries = new Map();
      this.lastClearReason = null;
      this.stats = {
        tradesReceived: 0,
        pulsesStarted: 0,
        pulsesCoalesced: 0,
        skippedUnsynced: 0,
        skippedInvalid: 0,
        skippedOffscreen: 0,
        clearedOnBoundary: 0,
        evictedCapacity: 0,
        maxActiveEntries: 0,
      };
    }

    prune(atMs) {
      const now = Number.isFinite(Number(atMs)) ? Number(atMs) : this.now();
      for (const [key, entry] of this.entries) {
        if (entry.expiresAt <= now) this.entries.delete(key);
      }
      return this.entries.size;
    }

    evictOldest() {
      let oldestKey = null;
      let oldestStartedAt = Infinity;
      for (const [key, entry] of this.entries) {
        if (entry.startedAt < oldestStartedAt) {
          oldestKey = key;
          oldestStartedAt = entry.startedAt;
        }
      }
      if (oldestKey !== null) {
        this.entries.delete(oldestKey);
        this.stats.evictedCapacity += 1;
      }
    }

    ingest(trades, context) {
      const rows = Array.isArray(trades) ? trades : [];
      const frame = context || {};
      const now = Number.isFinite(Number(frame.now)) ? Number(frame.now) : this.now();
      const tick = Number(frame.tick);
      const multiplier = Math.max(1, Math.round(Number(frame.multiplier) || 1));
      const rowIndexes = frame.rowIndexes instanceof Set
        ? frame.rowIndexes
        : new Set(Array.isArray(frame.rowIndexes) ? frame.rowIndexes : []);
      const synced = frame.synced === true;
      const result = { started: 0, coalesced: 0, skippedUnsynced: 0, skippedInvalid: 0, skippedOffscreen: 0 };
      this.prune(now);

      for (const trade of rows) {
        this.stats.tradesReceived += 1;
        if (!synced || !Number.isFinite(tick) || tick <= 0) {
          this.stats.skippedUnsynced += 1;
          result.skippedUnsynced += 1;
          continue;
        }
        const passiveSide = passiveSideForAggressor(trade && trade.side);
        const price = Number(trade && trade.price);
        if (!passiveSide || !Number.isFinite(price) || price <= 0) {
          this.stats.skippedInvalid += 1;
          result.skippedInvalid += 1;
          continue;
        }
        const nativeTickIndex = Math.round(price / tick);
        const displayBucketIndex = Math.floor(nativeTickIndex / multiplier) * multiplier;
        if (!Number.isSafeInteger(nativeTickIndex)) {
          this.stats.skippedInvalid += 1;
          result.skippedInvalid += 1;
          continue;
        }
        if (rowIndexes.size && !rowIndexes.has(displayBucketIndex)) {
          this.stats.skippedOffscreen += 1;
          result.skippedOffscreen += 1;
          continue;
        }
        const key = `${passiveSide}:${nativeTickIndex}`;
        const existing = this.entries.get(key);
        if (existing) {
          existing.startedAt = now;
          existing.expiresAt = now + this.durationMs;
          existing.hitCount += 1;
          existing.lastTradeId = trade.tradeId ?? trade.trade_id ?? null;
          existing.lastSequence = trade.sequence ?? null;
          this.stats.pulsesCoalesced += 1;
          result.coalesced += 1;
          continue;
        }
        if (this.entries.size >= this.maxActive) this.evictOldest();
        this.entries.set(key, {
          key,
          passiveSide,
          nativeTickIndex,
          price,
          startedAt: now,
          expiresAt: now + this.durationMs,
          hitCount: 1,
          lastTradeId: trade.tradeId ?? trade.trade_id ?? null,
          lastSequence: trade.sequence ?? null,
        });
        this.stats.pulsesStarted += 1;
        result.started += 1;
        this.stats.maxActiveEntries = Math.max(this.stats.maxActiveEntries, this.entries.size);
      }
      return result;
    }

    activeCells(frame, atMs) {
      const view = frame || {};
      const now = Number.isFinite(Number(atMs)) ? Number(atMs) : this.now();
      this.prune(now);
      if (!view.book || view.book.synced !== true || !Number.isFinite(Number(view.tick))) return [];
      const multiplier = Math.max(1, Math.round(Number(view.multiplier) || 1));
      const rowByIndex = new Map((view.rows || []).map((row, rowIndex) => [row.index, rowIndex]));
      const grouped = new Map();
      const holdMs = this.durationMs * 0.7;
      for (const entry of this.entries.values()) {
        const displayBucketIndex = Math.floor(entry.nativeTickIndex / multiplier) * multiplier;
        const rowIndex = rowByIndex.get(displayBucketIndex);
        if (rowIndex === undefined) continue;
        const ageMs = Math.max(0, now - entry.startedAt);
        const remainingMs = Math.max(0, entry.expiresAt - now);
        const opacity = ageMs <= holdMs
          ? 1
          : clamp(remainingMs / Math.max(1, this.durationMs - holdMs), 0, 1);
        const key = `${entry.passiveSide}:${displayBucketIndex}`;
        const existing = grouped.get(key);
        if (existing) {
          existing.opacity = Math.max(existing.opacity, opacity);
          existing.hitCount += entry.hitCount;
          existing.expiresAt = Math.max(existing.expiresAt, entry.expiresAt);
        } else {
          grouped.set(key, {
            passiveSide: entry.passiveSide,
            displayBucketIndex,
            rowIndex,
            opacity,
            hitCount: entry.hitCount,
            expiresAt: entry.expiresAt,
          });
        }
      }
      return [...grouped.values()];
    }

    clear(reason) {
      const cleared = this.entries.size;
      this.entries.clear();
      this.lastClearReason = String(reason || "CLEAR");
      if (cleared) this.stats.clearedOnBoundary += 1;
      return cleared;
    }

    snapshot(atMs) {
      this.prune(atMs);
      return Object.assign({}, this.stats, {
        activeEntries: this.entries.size,
        durationMs: this.durationMs,
        maxActive: this.maxActive,
        lastClearReason: this.lastClearReason,
      });
    }
  }

  class CanvasChart {
    constructor(options) {
      this.canvas = options.canvas;
      this.tooltip = options.tooltip;
      this.detail = options.detail;
      this.status = options.status;
      this.domStatus = options.domStatus || null;
      this.showDom = options.showDom !== false;
      this.onNeedHistory = options.onNeedHistory || function () {};
      this.onViewport = options.onViewport || function () {};
      this.onSelection = options.onSelection || function () {};
      this.ctx = this.canvas.getContext("2d");
      this.baseCanvas = typeof OffscreenCanvas === "function" ? new OffscreenCanvas(1, 1) : null;
      this.baseCtx = this.baseCanvas ? this.baseCanvas.getContext("2d") : null;
      this.baseValid = false;
      this.data = { bars: [], liveBar: null, currentPrice: null, book: null, vaPct: 70, priceStep: "AUTO", ratio: 3, minVolume: 0, stack: 3 };
      this.visibleBars = 10;
      this.offset = 0;
      this.lock = true;
      this.frame = null;
      this.geometry = null;
      this.selection = null;
      this.keyboardCell = null;
      this.drag = null;
      this.domTradePulseEnabled = options.domTradePulseEnabled !== false;
      this.domTradePulses = new DomTradePulseStore({
        durationMs: options.domTradePulseDurationMs,
        maxActive: options.domTradePulseMaxActive,
        now: options.domTradePulseNow,
      });
      this.domTradePulseFrameHandle = null;
      this.domTradePulseFrameKind = null;
      this.domTradePulseIdentity = { symbol: null, streamId: null, mode: null, bookStreamId: null };
      this.dirty = new Set(["viewport", "history", "selection"]);
      this.drawPending = false;
      this.renderTimes = [];
      this.resizeObserver = typeof ResizeObserver === "function"
        ? new ResizeObserver(() => this.invalidate("viewport")) : null;
      if (this.resizeObserver) this.resizeObserver.observe(this.canvas.parentElement);
      this.bindEvents();
      this.invalidate("viewport");
    }

    setData(data, layer) {
      if (data && Object.prototype.hasOwnProperty.call(data, "book")) {
        const nextBook = data.book;
        const nextBookStreamId = nextBook && typeof nextBook.book_stream_id === "string"
          ? nextBook.book_stream_id : null;
        if (this.domTradePulseIdentity.bookStreamId && nextBookStreamId &&
            this.domTradePulseIdentity.bookStreamId !== nextBookStreamId) {
          this.clearDomTradePulses("BOOK_STREAM_RESTART");
        }
        if (nextBookStreamId) this.domTradePulseIdentity.bookStreamId = nextBookStreamId;
        if (!nextBook || nextBook.sync_state !== "SYNCED") this.clearDomTradePulses("BOOK_FAIL_CLOSED");
      }
      this.data = Object.assign({}, this.data, data || {});
      if (this.lock) this.offset = 0;
      let dirtyLayer = layer || "liveFootprint";
      if (dirtyLayer === "reference" && this.frame && finite(this.data.currentPrice)) {
        const high = this.frame.rows.length ? this.frame.rows[0].price : null;
        const low = this.frame.rows.length ? this.frame.rows[this.frame.rows.length - 1].price : null;
        if (high == null || low == null || Number(this.data.currentPrice) > high || Number(this.data.currentPrice) < low) dirtyLayer = "viewport";
      }
      if (dirtyLayer === "liveDom" && this.bookOutsideFrame()) dirtyLayer = "viewport";
      this.invalidate(dirtyLayer);
    }

    setDomTradePulseEnabled(enabled) {
      const next = Boolean(enabled);
      if (next === this.domTradePulseEnabled) return;
      this.domTradePulseEnabled = next;
      if (!next) this.clearDomTradePulses("FEATURE_DISABLED");
    }

    ingestDomTradePulses(trades, meta) {
      if (!this.domTradePulseEnabled) return { disabled: true, started: 0, coalesced: 0 };
      const context = meta || {};
      for (const field of ["symbol", "streamId", "mode"]) {
        const next = context[field] === null || context[field] === undefined
          ? null : String(context[field]);
        const current = this.domTradePulseIdentity[field];
        if (next && current && next !== current) this.clearDomTradePulses(`${field.toUpperCase()}_CHANGE`);
        if (next) this.domTradePulseIdentity[field] = next;
      }
      const frame = this.frame;
      const result = this.domTradePulses.ingest(trades, {
        now: this.domTradePulses.now(),
        synced: Boolean(frame && frame.book && frame.book.synced && this.data.book && this.data.book.sync_state === "SYNCED"),
        tick: frame && frame.tick,
        multiplier: frame && frame.multiplier,
        rowIndexes: frame ? new Set(frame.rows.map(row => row.index)) : new Set(),
      });
      if (result.started || result.coalesced) {
        this.invalidate("domTradePulse");
        this.scheduleDomTradePulseFrame();
      }
      return result;
    }

    scheduleDomTradePulseFrame() {
      if (!this.domTradePulseEnabled || this.domTradePulseFrameHandle !== null || !this.domTradePulses.entries.size) return;
      const schedule = typeof requestAnimationFrame === "function"
        ? requestAnimationFrame
        : callback => setTimeout(() => callback(this.domTradePulses.now()), 16);
      this.domTradePulseFrameKind = typeof requestAnimationFrame === "function" ? "raf" : "timer";
      this.domTradePulseFrameHandle = schedule(() => {
        this.domTradePulseFrameHandle = null;
        this.domTradePulses.prune(this.domTradePulses.now());
        this.invalidate("domTradePulse");
        if (this.domTradePulses.entries.size) this.scheduleDomTradePulseFrame();
      });
    }

    cancelDomTradePulseFrame() {
      if (this.domTradePulseFrameHandle === null) return;
      if (this.domTradePulseFrameKind === "raf" && typeof cancelAnimationFrame === "function") {
        cancelAnimationFrame(this.domTradePulseFrameHandle);
      } else {
        clearTimeout(this.domTradePulseFrameHandle);
      }
      this.domTradePulseFrameHandle = null;
      this.domTradePulseFrameKind = null;
    }

    clearDomTradePulses(reason) {
      const cleared = this.domTradePulses.clear(reason);
      this.cancelDomTradePulseFrame();
      if (cleared) this.invalidate("domTradePulse");
      return cleared;
    }

    getDomTradePulseStats() {
      return Object.assign(this.domTradePulses.snapshot(this.domTradePulses.now()), {
        enabled: this.domTradePulseEnabled,
        schedulerActive: this.domTradePulseFrameHandle !== null,
      });
    }

    destroy() {
      this.clearDomTradePulses("CANVAS_DESTROY");
      if (this.resizeObserver) this.resizeObserver.disconnect();
    }

    setVisibleBars(value, anchorRatio) {
      const next = clamp(Math.round(Number(value) || 10), 3, 20);
      if (next === this.visibleBars) return;
      const ratio = clamp(Number(anchorRatio) || 0.5, 0, 1);
      if (!this.lock) this.offset = Math.max(0, this.offset + Math.round((this.visibleBars - next) * (1 - ratio)));
      this.visibleBars = next;
      this.invalidate("viewport");
      this.emitViewport();
    }

    setOffset(value) {
      const maxOffset = Math.max(0, this.closedBars().length + (this.data.liveBar ? 1 : 0) - this.visibleBars);
      this.offset = clamp(Math.round(Number(value) || 0), 0, maxOffset);
      this.lock = this.offset === 0;
      if (this.offset + this.visibleBars >= this.closedBars().length - 2) this.onNeedHistory();
      this.invalidate("viewport");
      this.emitViewport();
    }

    returnLive() {
      this.offset = 0;
      this.lock = true;
      this.invalidate("viewport");
      this.emitViewport();
    }

    emitViewport() {
      this.onViewport({ visibleBars: this.visibleBars, offset: this.offset, lock: this.lock });
    }

    closedBars() {
      return (this.data.bars || []).filter(bar => Number.isFinite(timeOf(bar))).sort((a, b) => timeOf(a) - timeOf(b));
    }

    bookPrices() {
      if (!this.showDom || !this.data.book || this.data.book.sync_state !== "SYNCED") return [];
      const prices = [];
      for (const side of ["bids", "asks"]) for (const level of Array.isArray(this.data.book[side]) ? this.data.book[side] : []) {
        if (finite(level.price)) prices.push(Number(level.price));
      }
      return prices;
    }

    bookOutsideFrame() {
      if (!this.frame || !this.frame.rows.length) return false;
      const prices = this.bookPrices();
      if (!prices.length) return false;
      const high = this.frame.rows[0].price + this.frame.step;
      const low = this.frame.rows[this.frame.rows.length - 1].price;
      return prices.some(price => price < low || price >= high);
    }

    invalidate(layer) {
      this.dirty.add(layer);
      if (this.drawPending) return;
      this.drawPending = true;
      const schedule = typeof requestAnimationFrame === "function" ? requestAnimationFrame : callback => setTimeout(callback, 0);
      schedule(() => { this.drawPending = false; this.draw(); });
    }

    resizeBackingStore() {
      const rect = this.canvas.getBoundingClientRect();
      const width = Math.max(1, Math.round(rect.width || this.canvas.clientWidth || 1));
      const height = Math.max(1, Math.round(rect.height || this.canvas.clientHeight || 1));
      const dpr = clamp(Number(typeof devicePixelRatio === "number" ? devicePixelRatio : 1) || 1, 1, 4);
      const pixelWidth = Math.round(width * dpr);
      const pixelHeight = Math.round(height * dpr);
      let resized = false;
      if (this.canvas.width !== pixelWidth || this.canvas.height !== pixelHeight) {
        this.canvas.width = pixelWidth;
        this.canvas.height = pixelHeight;
        resized = true;
      }
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (this.baseCanvas && (this.baseCanvas.width !== pixelWidth || this.baseCanvas.height !== pixelHeight)) {
        this.baseCanvas.width = pixelWidth;
        this.baseCanvas.height = pixelHeight;
        this.baseValid = false;
        resized = true;
      }
      if (this.baseCtx) this.baseCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      return { width, height, dpr, resized };
    }

    availableBars() {
      const closed = this.closedBars();
      const live = this.data.liveBar;
      if (!live || !Number.isFinite(timeOf(live))) return closed;
      const liveTime = timeOf(live);
      const same = closed.findIndex(bar => timeOf(bar) === liveTime);
      if (same >= 0) return closed;
      return [...closed, live].sort((a, b) => timeOf(a) - timeOf(b));
    }

    buildFrame(width, height) {
      const all = this.availableBars();
      const end = Math.max(0, all.length - this.offset);
      const start = Math.max(0, end - this.visibleBars);
      const visible = all.slice(start, end);
      const tick = inferTickSize(visible.length ? visible : all, this.data.tickSize);
      let minPrice = Infinity;
      let maxPrice = -Infinity;
      for (const bar of visible) {
        const levels = bar && bar.footprint && Array.isArray(bar.footprint.levels) ? bar.footprint.levels : [];
        for (const level of levels) if (finite(level.price)) {
          minPrice = Math.min(minPrice, Number(level.price));
          maxPrice = Math.max(maxPrice, Number(level.price));
        }
        for (const key of ["low", "high"]) if (finite(bar[key])) {
          minPrice = Math.min(minPrice, Number(bar[key]));
          maxPrice = Math.max(maxPrice, Number(bar[key]));
        }
      }
      for (const price of this.bookPrices()) {
        minPrice = Math.min(minPrice, price);
        maxPrice = Math.max(maxPrice, price);
      }
      if (!Number.isFinite(minPrice) || !Number.isFinite(maxPrice)) {
        minPrice = finite(this.data.currentPrice) ? Number(this.data.currentPrice) - tick * 10 : 0;
        maxPrice = finite(this.data.currentPrice) ? Number(this.data.currentPrice) + tick * 10 : tick * 20;
      }
      const requested = String(this.data.priceStep || "AUTO").toUpperCase();
      const multiplier = requested === "AUTO"
        ? autoMultiplier(minPrice, maxPrice, tick, 20)
        : Math.max(1, Math.round(Number(requested) || 1));
      const step = tick * multiplier;
      const prepared = visible.map(bar => {
        const raw = bar && bar.footprint && Array.isArray(bar.footprint.levels) ? bar.footprint.levels : [];
        const levels = bucketLevels(raw, tick, multiplier);
        const va = valueArea(levels, this.data.vaPct);
        const flags = imbalanceFlags(levels, this.data.ratio, this.data.minVolume, this.data.stack, multiplier);
        return {
          raw: bar,
          time: timeOf(bar),
          levels,
          byIndex: new Map(levels.map(level => [level.index, level])),
          va,
          flags,
          maxVolume: Math.max(1e-12, ...levels.map(level => Math.max(level.bid, level.ask))),
          live: Boolean(this.data.liveBar && timeOf(this.data.liveBar) === timeOf(bar)),
        };
      });
      let highIndex = Math.floor(maxPrice / tick / multiplier) * multiplier;
      let lowIndex = Math.floor(minPrice / tick / multiplier) * multiplier;
      for (const bar of prepared) for (const level of bar.levels) {
        highIndex = Math.max(highIndex, level.index);
        lowIndex = Math.min(lowIndex, level.index);
      }
      let rowCount = Math.floor((highIndex - lowIndex) / multiplier) + 1;
      if (rowCount < 20) {
        const missing = 20 - rowCount;
        highIndex += Math.ceil(missing / 2) * multiplier;
        lowIndex -= Math.floor(missing / 2) * multiplier;
        rowCount = 20;
      }
      let hiddenAbove = 0;
      let hiddenBelow = 0;
      if (rowCount > 40) {
        const centerPrice = finite(this.data.currentPrice) ? Number(this.data.currentPrice) : (maxPrice + minPrice) / 2;
        const center = Math.floor(centerPrice / tick / multiplier) * multiplier;
        const originalHigh = highIndex;
        const originalLow = lowIndex;
        highIndex = Math.min(originalHigh, center + 20 * multiplier);
        lowIndex = highIndex - 39 * multiplier;
        if (lowIndex < originalLow) { lowIndex = originalLow; highIndex = lowIndex + 39 * multiplier; }
        hiddenAbove = Math.max(0, Math.round((originalHigh - highIndex) / multiplier));
        hiddenBelow = Math.max(0, Math.round((lowIndex - originalLow) / multiplier));
        rowCount = 40;
      }
      const rows = [];
      for (let index = highIndex; index >= lowIndex; index -= multiplier) rows.push({
        index,
        price: index * tick,
      });
      const book = prepareBook(this.showDom ? this.data.book : null, tick, multiplier);
      return { allCount: all.length, start, end, bars: prepared, rows, tick, multiplier, step, requested, hiddenAbove, hiddenBelow, book };
    }

    buildGeometry(width, height, frame) {
      const axisWidth = width < 430 ? 62 : 74;
      const top = 30;
      const factsHeight = this.visibleBars <= 10 ? 58 : 34;
      const bottom = Math.max(top + 20, height - factsHeight);
      const domWidth = this.showDom ? clamp(Math.round(width * 0.19), 112, 146) : 0;
      const plotWidth = Math.max(1, width - axisWidth - domWidth - 4);
      const barWidth = plotWidth / Math.max(1, frame.bars.length || this.visibleBars);
      const rowHeight = (bottom - top) / Math.max(1, frame.rows.length);
      const domX = axisWidth + plotWidth;
      return { width, height, axisWidth, top, bottom, factsHeight, plotWidth, barWidth, rowHeight, domWidth, domX, domMid: domX + domWidth / 2 };
    }

    draw() {
      const started = typeof performance !== "undefined" ? performance.now() : Date.now();
      const size = this.resizeBackingStore();
      const ctx = this.ctx;
      const overlayOnly = !size.resized && this.baseValid && this.frame && this.geometry &&
        [...this.dirty].every(layer =>
          layer === "reference" || layer === "selection" || layer === "liveDom" || layer === "domTradePulse"
        );
      if (!overlayOnly) {
        this.frame = this.buildFrame(size.width, size.height);
        this.geometry = this.buildGeometry(size.width, size.height, this.frame);
        const base = this.baseCtx || ctx;
        base.clearRect(0, 0, this.geometry.width, this.geometry.height);
        base.fillStyle = BG;
        base.fillRect(0, 0, this.geometry.width, this.geometry.height);
        this.drawGrid(base, this.geometry, this.frame);
        this.drawBars(base, this.geometry, this.frame);
        this.baseValid = Boolean(this.baseCtx);
      } else if (this.showDom) {
        this.frame.book = prepareBook(this.data.book, this.frame.tick, this.frame.multiplier);
      }
      const g = this.geometry;
      if (this.baseCanvas && this.baseValid) {
        ctx.clearRect(0, 0, g.width, g.height);
        ctx.drawImage(this.baseCanvas, 0, 0, this.baseCanvas.width, this.baseCanvas.height, 0, 0, g.width, g.height);
      }
      if (this.showDom) this.drawBook(ctx, g, this.frame);
      if (this.showDom) this.drawDomTradePulses(ctx, g, this.frame);
      this.drawReferences(ctx, g, this.frame);
      this.drawSelection(ctx, g, this.frame);
      this.refreshSelectionDetail();
      const elapsed = (typeof performance !== "undefined" ? performance.now() : Date.now()) - started;
      this.renderTimes.push(elapsed);
      if (this.renderTimes.length > 120) this.renderTimes.shift();
      this.dirty.clear();
      this.updateStatus(size.dpr);
    }

    drawGrid(ctx, g, frame) {
      ctx.lineWidth = 1;
      ctx.strokeStyle = GRID;
      ctx.fillStyle = MUTED;
      ctx.font = `800 ${AXIS_FONT_PX}px ${FONT}`;
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      const stride = Math.max(1, Math.ceil(18 / g.rowHeight));
      frame.rows.forEach((row, rowIndex) => {
        const y = g.top + rowIndex * g.rowHeight;
        ctx.globalAlpha = rowIndex % stride === 0 ? 0.7 : 0.24;
        ctx.beginPath(); ctx.moveTo(g.axisWidth, y); ctx.lineTo(g.width, y); ctx.stroke();
        if (rowIndex % stride === 0) {
          ctx.globalAlpha = 1;
          ctx.fillText(row.price.toFixed(priceDigits(frame.step)), g.axisWidth - 5, y + g.rowHeight / 2);
        }
      });
      ctx.globalAlpha = 1;
      ctx.beginPath(); ctx.moveTo(g.axisWidth, g.top); ctx.lineTo(g.axisWidth, g.bottom); ctx.stroke();
      for (let i = 0; i <= frame.bars.length; i += 1) {
        const x = g.axisWidth + i * g.barWidth;
        ctx.globalAlpha = 0.5;
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, g.height); ctx.stroke();
      }
      if (this.showDom) {
        ctx.globalAlpha = 1;
        ctx.fillStyle = "rgba(9,17,31,.78)";
        ctx.fillRect(g.domX, 0, g.domWidth, g.height);
        ctx.strokeStyle = "#526482";
        ctx.beginPath(); ctx.moveTo(g.domX, 0); ctx.lineTo(g.domX, g.height); ctx.stroke();
        ctx.strokeStyle = GRID;
        ctx.beginPath(); ctx.moveTo(g.domMid, g.top); ctx.lineTo(g.domMid, g.bottom); ctx.stroke();
      }
      ctx.globalAlpha = 1;
      if (frame.hiddenAbove) { ctx.textAlign = "left"; ctx.fillText(`▲ +${frame.hiddenAbove}`, 3, g.top + 5); }
      if (frame.hiddenBelow) { ctx.textAlign = "left"; ctx.fillText(`▼ +${frame.hiddenBelow}`, 3, g.bottom - 5); }
    }

    drawBook(ctx, g, frame) {
      const book = frame.book || prepareBook(null, frame.tick, frame.multiplier);
      const half = g.domWidth / 2;
      ctx.save();
      ctx.font = `800 ${META_FONT_PX}px ${FONT}`;
      ctx.textBaseline = "middle";
      ctx.textAlign = "center";
      ctx.fillStyle = book.synced ? CYAN : POC;
      ctx.fillText("LIVE DOM", g.domX + g.domWidth / 2, 8);
      ctx.fillStyle = MUTED;
      ctx.fillText(book.synced ? "PASSIVE BID │ ASK" : book.state, g.domX + g.domWidth / 2, 22);
      if (!book.synced) {
        ctx.fillStyle = POC;
        ctx.font = `800 ${CELL_FONT_PX}px ${FONT}`;
        ctx.fillText("— │ —", g.domX + g.domWidth / 2, g.top + (g.bottom - g.top) / 2);
        ctx.restore();
        return;
      }
      const canText = g.rowHeight >= 8.5 && g.domWidth >= 100;
      frame.rows.forEach((row, rowIndex) => {
        const level = book.byIndex.get(row.index);
        if (!level) return;
        const y = g.top + rowIndex * g.rowHeight;
        const bidRatio = level.bid / book.maximum;
        const askRatio = level.ask / book.maximum;
        if (level.bid > 0) {
          ctx.globalAlpha = 0.12 + 0.62 * bidRatio;
          ctx.fillStyle = BUY;
          const width = Math.max(1, (half - 2) * bidRatio);
          ctx.fillRect(g.domMid - width - 1, y + 1, width, Math.max(1, g.rowHeight - 2));
        }
        if (level.ask > 0) {
          ctx.globalAlpha = 0.12 + 0.62 * askRatio;
          ctx.fillStyle = SELL;
          ctx.fillRect(g.domMid + 1, y + 1, Math.max(1, (half - 2) * askRatio), Math.max(1, g.rowHeight - 2));
        }
        ctx.globalAlpha = 1;
        if (row.index === book.bidWall && level.bid > 0) {
          ctx.strokeStyle = POC; ctx.lineWidth = 1.5;
          ctx.strokeRect(g.domX + 1.5, y + 1.5, Math.max(0, half - 3), Math.max(0, g.rowHeight - 3));
        }
        if (row.index === book.askWall && level.ask > 0) {
          ctx.strokeStyle = POC; ctx.lineWidth = 1.5;
          ctx.strokeRect(g.domMid + 1.5, y + 1.5, Math.max(0, half - 3), Math.max(0, g.rowHeight - 3));
        }
        if (row.index === book.bestBidIndex && level.bid > 0) {
          ctx.strokeStyle = CYAN; ctx.lineWidth = 1.5;
          ctx.strokeRect(g.domX + 1.5, y + 1.5, Math.max(0, half - 3), Math.max(0, g.rowHeight - 3));
        }
        if (row.index === book.bestAskIndex && level.ask > 0) {
          ctx.strokeStyle = CYAN; ctx.lineWidth = 1.5;
          ctx.strokeRect(g.domMid + 1.5, y + 1.5, Math.max(0, half - 3), Math.max(0, g.rowHeight - 3));
        }
        if (canText) {
          const fontSize = g.rowHeight >= 17 ? CELL_FONT_PX : g.rowHeight >= 13 ? STANDARD_CELL_FONT_PX : DENSE_CELL_FONT_PX;
          ctx.font = `800 ${fontSize}px ${FONT}`;
          ctx.fillStyle = TEXT;
          ctx.textAlign = "right";
          ctx.fillText(level.bid > 0 ? compact(level.bid) : "—", g.domMid - 3, y + g.rowHeight / 2);
          ctx.textAlign = "left";
          ctx.fillText(level.ask > 0 ? compact(level.ask) : "—", g.domMid + 3, y + g.rowHeight / 2);
        }
      });
      ctx.restore();
    }

    drawDomTradePulses(ctx, g, frame) {
      if (!this.domTradePulseEnabled || !frame || !frame.book || !frame.book.synced) return;
      const cells = this.domTradePulses.activeCells(frame, this.domTradePulses.now());
      if (!cells.length) return;
      const half = g.domWidth / 2;
      ctx.save();
      ctx.fillStyle = DOM_TRADE_PULSE_COLOR;
      ctx.strokeStyle = DOM_TRADE_PULSE_COLOR;
      ctx.lineWidth = 2;
      for (const cell of cells) {
        const y = g.top + cell.rowIndex * g.rowHeight;
        const x = cell.passiveSide === "ASK" ? g.domMid + 1 : g.domX + 1;
        const width = Math.max(1, half - 2);
        const height = Math.max(1, g.rowHeight - 2);
        ctx.globalAlpha = 0.5 * cell.opacity;
        ctx.fillRect(x, y + 1, width, height);
        ctx.globalAlpha = 0.96 * cell.opacity;
        ctx.strokeRect(x + 0.5, y + 1.5, Math.max(0, width - 1), Math.max(0, height - 1));
      }
      ctx.restore();
    }

    drawBars(ctx, g, frame) {
      const canText = g.rowHeight >= 8.5 && g.barWidth >= 34;
      frame.bars.forEach((bar, barIndex) => {
        const x = g.axisWidth + barIndex * g.barWidth;
        ctx.font = `800 ${g.barWidth >= 70 ? CELL_FONT_PX : g.barWidth >= 48 ? STANDARD_CELL_FONT_PX : META_FONT_PX}px ${FONT}`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = bar.live ? CYAN : SUB;
        const stamp = Number.isFinite(bar.time) ? jstClock(bar.time) : "—";
        ctx.fillText(stamp, x + g.barWidth / 2, 15);
        for (let rowIndex = 0; rowIndex < frame.rows.length; rowIndex += 1) {
          const row = frame.rows[rowIndex];
          const level = bar.byIndex.get(row.index);
          if (!level) continue;
          const y = g.top + rowIndex * g.rowHeight;
          const half = g.barWidth / 2;
          const bidAlpha = 0.08 + 0.58 * level.bid / bar.maxVolume;
          const askAlpha = 0.08 + 0.58 * level.ask / bar.maxVolume;
          ctx.globalAlpha = bidAlpha; ctx.fillStyle = SELL; ctx.fillRect(x + 1, y + 1, Math.max(0, half - 2), Math.max(1, g.rowHeight - 2));
          ctx.globalAlpha = askAlpha; ctx.fillStyle = BUY; ctx.fillRect(x + half + 1, y + 1, Math.max(0, half - 2), Math.max(1, g.rowHeight - 2));
          ctx.globalAlpha = 1;
          if (bar.va.inValue.has(row.index)) {
            ctx.fillStyle = "rgba(244,197,66,.06)"; ctx.fillRect(x + 1, y + 1, g.barWidth - 2, Math.max(1, g.rowHeight - 2));
          }
          if (row.index === bar.va.vah || row.index === bar.va.val) {
            ctx.strokeStyle = "rgba(244,197,66,.75)"; ctx.lineWidth = 1;
            ctx.beginPath();
            const boundaryY = row.index === bar.va.vah ? y + 1 : y + g.rowHeight - 1;
            ctx.moveTo(x + 1, boundaryY); ctx.lineTo(x + g.barWidth - 1, boundaryY); ctx.stroke();
          }
          if (row.index === bar.va.poc) {
            ctx.strokeStyle = POC; ctx.lineWidth = 1.2; ctx.strokeRect(x + 1.5, y + 1.5, Math.max(0, g.barWidth - 3), Math.max(0, g.rowHeight - 3));
          }
          const flags = bar.flags.get(row.index) || {};
          if (flags.sell) { ctx.strokeStyle = flags.sellStack ? POC : "#FF7A8D"; ctx.lineWidth = flags.sellStack ? 2 : 1; ctx.strokeRect(x + 1.5, y + 1.5, Math.max(0, half - 3), Math.max(0, g.rowHeight - 3)); }
          if (flags.buy) { ctx.strokeStyle = flags.buyStack ? POC : "#72FFC0"; ctx.lineWidth = flags.buyStack ? 2 : 1; ctx.strokeRect(x + half + 1.5, y + 1.5, Math.max(0, half - 3), Math.max(0, g.rowHeight - 3)); }
          if (canText) {
            const fontSize = g.rowHeight >= 17 ? CELL_FONT_PX : g.rowHeight >= 13 ? STANDARD_CELL_FONT_PX : DENSE_CELL_FONT_PX;
            ctx.font = `800 ${fontSize}px ${FONT}`;
            const maxTextWidth = Math.max(8, half - 5);
            ctx.fillStyle = TEXT; ctx.textAlign = "right"; ctx.fillText(compact(level.bid), x + half - 3, y + g.rowHeight / 2, maxTextWidth);
            ctx.textAlign = "left"; ctx.fillText(compact(level.ask), x + half + 3, y + g.rowHeight / 2, maxTextWidth);
          }
        }
        this.drawCandle(ctx, g, frame, bar, barIndex);
        this.drawFacts(ctx, g, bar, barIndex);
        if (bar.live) { ctx.strokeStyle = CYAN; ctx.lineWidth = 1.5; ctx.strokeRect(x + 1, 0.5, Math.max(0, g.barWidth - 2), g.height - 1); }
      });
    }

    priceY(price, g, frame) {
      if (!finite(price) || !frame.rows.length) return null;
      const topPrice = frame.rows[0].price;
      return g.top + ((topPrice - Number(price)) / frame.step + 0.5) * g.rowHeight;
    }

    drawCandle(ctx, g, frame, bar, barIndex) {
      const raw = bar.raw || {};
      if (![raw.open, raw.high, raw.low, raw.close].every(finite)) return;
      const center = g.axisWidth + (barIndex + 0.5) * g.barWidth;
      const high = this.priceY(raw.high, g, frame);
      const low = this.priceY(raw.low, g, frame);
      const open = this.priceY(raw.open, g, frame);
      const close = this.priceY(raw.close, g, frame);
      if (![high, low, open, close].every(Number.isFinite)) return;
      const color = Number(raw.close) >= Number(raw.open) ? BUY : SELL;
      ctx.save();
      ctx.strokeStyle = "rgba(241,245,255,.88)";
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(center, clamp(high, g.top, g.bottom)); ctx.lineTo(center, clamp(low, g.top, g.bottom)); ctx.stroke();
      const bodyTop = clamp(Math.min(open, close), g.top, g.bottom);
      const bodyBottom = clamp(Math.max(open, close), g.top, g.bottom);
      const bodyWidth = clamp(g.barWidth * 0.12, 3, 8);
      ctx.fillStyle = color;
      ctx.strokeStyle = TEXT;
      ctx.lineWidth = 0.8;
      ctx.fillRect(center - bodyWidth / 2, bodyTop, bodyWidth, Math.max(2, bodyBottom - bodyTop));
      ctx.strokeRect(center - bodyWidth / 2, bodyTop, bodyWidth, Math.max(2, bodyBottom - bodyTop));
      ctx.restore();
    }

    drawFacts(ctx, g, bar, barIndex) {
      const raw = bar.raw || {};
      const x = g.axisWidth + barIndex * g.barWidth;
      const center = x + g.barWidth / 2;
      const delta = finite(raw.delta) ? Number(raw.delta) : null;
      const volume = finite(raw.volume) ? Number(raw.volume) : null;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      if (this.visibleBars <= 10) {
        ctx.font = `800 ${META_FONT_PX}px ${FONT}`;
        ctx.fillStyle = delta == null ? MUTED : delta >= 0 ? BUY : SELL;
        const deltaText = delta == null ? "Δ —" : `Δ ${delta >= 0 ? "+" : ""}${compact(delta)}`;
        const volumeText = volume == null ? "V —" : `V ${compact(volume)}`;
        ctx.fillText(this.visibleBars <= 3 ? `${deltaText} · ${volumeText}` : deltaText, center, g.bottom + 4);
        ctx.fillStyle = SUB;
        if (this.visibleBars <= 3) {
          const cvd = finite(raw.cvd_change) ? `${Number(raw.cvd_change) >= 0 ? "+" : ""}${compact(raw.cvd_change)}` : "—";
          const oi = finite(raw.oi_change) ? `${Number(raw.oi_change) >= 0 ? "+" : ""}${compact(raw.oi_change)}` : "—";
          ctx.fillText(`CVD Δ ${cvd} · OI Δ ${oi}`, center, g.bottom + 17);
          ctx.fillStyle = number(raw.events_count) > 0 ? POC : MUTED;
          ctx.fillText(`EVENTS ${number(raw.events_count) > 0 ? Math.round(number(raw.events_count)) : "—"}`, center, g.bottom + 30);
        } else ctx.fillText(volumeText, center, g.bottom + 17);
      } else {
        ctx.fillStyle = delta == null ? MUTED : delta >= 0 ? BUY : SELL;
        ctx.fillRect(x + 2, g.bottom + 5, Math.max(1, g.barWidth - 4), 3);
      }
    }

    drawReferences(ctx, g, frame) {
      const lines = [
        { value: this.data.vwap, color: CYAN, dash: [5, 4], label: "VWAP" },
        { value: this.data.currentPrice, color: TEXT, dash: [], label: "LAST" },
      ];
      for (const line of lines) {
        const y = this.priceY(line.value, g, frame);
        if (!Number.isFinite(y) || y < g.top || y > g.bottom) continue;
        ctx.save();
        ctx.strokeStyle = line.color;
        ctx.lineWidth = 1;
        ctx.setLineDash(line.dash);
        ctx.beginPath(); ctx.moveTo(g.axisWidth, y); ctx.lineTo(g.width, y); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = line.color;
        ctx.font = `800 9px ${FONT}`;
        ctx.textAlign = "left";
        ctx.textBaseline = "bottom";
        ctx.fillText(line.label, g.axisWidth + 3, y - 1);
        ctx.restore();
      }
    }

    drawSelection(ctx, g, frame) {
      if (!this.selection) return;
      const resolved = this.resolveSelection();
      if (!resolved) return;
      const { barIndex, rowIndex } = resolved;
      const y = g.top + rowIndex * g.rowHeight;
      ctx.strokeStyle = TEXT;
      if (barIndex >= 0) {
        const x = g.axisWidth + barIndex * g.barWidth;
        ctx.globalAlpha = 0.55;
        ctx.lineWidth = 1;
        ctx.strokeRect(x + 1, g.top + 1, Math.max(0, g.barWidth - 2), Math.max(0, g.bottom - g.top - 2));
        ctx.globalAlpha = 1;
        ctx.lineWidth = 2;
        ctx.strokeRect(x + 1, y + 1, Math.max(0, g.barWidth - 2), Math.max(0, g.rowHeight - 2));
      } else {
        ctx.globalAlpha = 0.5;
        ctx.lineWidth = 1;
        ctx.strokeRect(g.axisWidth + 1, y + 1, Math.max(0, g.plotWidth - 2), Math.max(0, g.rowHeight - 2));
      }
      ctx.globalAlpha = 1;
      if (this.showDom) {
        ctx.lineWidth = this.selection.source === "DOM" ? 2 : 1;
        ctx.strokeRect(g.domX + 1, y + 1, Math.max(0, g.domWidth - 2), Math.max(0, g.rowHeight - 2));
      }
    }

    resolveSelection() {
      if (!this.selection || !this.frame) return null;
      const priceIndex = this.selection.priceIndex === null || this.selection.priceIndex === undefined
        ? bucketIndex(this.selection.price, this.frame.tick, this.frame.multiplier)
        : this.selection.priceIndex;
      const rowIndex = this.frame.rows.findIndex(row => row.index === priceIndex);
      if (rowIndex < 0) return null;
      const barIndex = this.selection.time === null || this.selection.time === undefined
        ? -1 : this.frame.bars.findIndex(bar => bar.time === this.selection.time);
      if (this.selection.time !== null && this.selection.time !== undefined && barIndex < 0) return null;
      this.selection.priceIndex = priceIndex;
      return { barIndex, rowIndex, priceIndex, row: this.frame.rows[rowIndex], bar: barIndex >= 0 ? this.frame.bars[barIndex] : null };
    }

    refreshSelectionDetail() {
      const resolved = this.resolveSelection();
      if (!resolved) return;
      const level = resolved.bar
        ? resolved.bar.byIndex.get(resolved.priceIndex) || { bid: 0, ask: 0, price: resolved.row.price }
        : this.frame.book.byIndex.get(resolved.priceIndex) || { bid: 0, ask: 0, price: resolved.row.price };
      this.updateDetail({
        area: resolved.bar ? "footprint" : "dom",
        barIndex: resolved.barIndex,
        rowIndex: resolved.rowIndex,
        time: resolved.bar ? resolved.bar.time : null,
        bar: resolved.bar,
        row: resolved.row,
        level,
        priceIndex: resolved.priceIndex,
        trade: this.selection.trade || null,
      });
    }

    selectionPayload(hit) {
      return {
        source: hit.area === "dom" ? "DOM" : this.selection && this.selection.source === "TAPE" ? "TAPE" : "FOOTPRINT",
        barTime: Number.isFinite(hit.time) ? hit.time : null,
        timeframeMs: hit.bar ? timeframeMilliseconds(hit.bar.raw && hit.bar.raw.timeframe) : null,
        price: hit.row.price,
        step: this.frame.step,
        tick: this.frame.tick,
        multiplier: this.frame.multiplier,
      };
    }

    hasBarAt(eventTime) {
      const time = typeof eventTime === "number" ? eventTime : Date.parse(eventTime);
      if (!Number.isFinite(time)) return false;
      return this.availableBars().some(bar => {
        const start = timeOf(bar);
        return time >= start && time < start + timeframeMilliseconds(bar.timeframe);
      });
    }

    selectTrade(trade) {
      const eventTime = trade && Number.isFinite(trade.eventTime) ? trade.eventTime : Date.parse(trade && (trade.event_time || trade.eventTimeIso));
      if (!Number.isFinite(eventTime) || !finite(trade && trade.price)) return false;
      const all = this.availableBars();
      const index = all.findIndex(bar => {
        const start = timeOf(bar);
        return eventTime >= start && eventTime < start + timeframeMilliseconds(bar.timeframe);
      });
      if (index < 0) return false;
      const maxOffset = Math.max(0, all.length - this.visibleBars);
      this.offset = clamp(all.length - 1 - index, 0, maxOffset);
      this.lock = this.offset === 0;
      this.selection = { time: timeOf(all[index]), priceIndex: null, price: Number(trade.price), source: "TAPE", trade };
      this.keyboardCell = null;
      this.invalidate("viewport");
      this.emitViewport();
      return true;
    }

    hitTest(clientX, clientY) {
      if (!this.frame || !this.geometry) return null;
      const rect = this.canvas.getBoundingClientRect();
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      const g = this.geometry;
      if (x < g.axisWidth || x >= g.width || y < g.top || y >= g.bottom) return null;
      const rowIndex = Math.floor((y - g.top) / g.rowHeight);
      const row = this.frame.rows[rowIndex];
      if (!row) return null;
      if (this.showDom && x >= g.domX) {
        const level = this.frame.book.byIndex.get(row.index) || { bid: 0, ask: 0, price: row.price };
        return { area: "dom", side: x < g.domMid ? "BID" : "ASK", barIndex: -1, rowIndex, time: null, bar: null, row, level, priceIndex: row.index, x, y };
      }
      const barIndex = Math.floor((x - g.axisWidth) / g.barWidth);
      const bar = this.frame.bars[barIndex];
      if (!bar) return null;
      const level = bar.byIndex.get(row.index) || { bid: 0, ask: 0, price: row.price };
      return { area: "footprint", barIndex, rowIndex, time: bar.time, bar, row, level, priceIndex: row.index, x, y };
    }

    selectCell(hit) {
      if (!hit) return;
      this.selection = { time: hit.area === "dom" ? null : hit.time, priceIndex: hit.priceIndex, price: hit.row.price, source: hit.area === "dom" ? "DOM" : "FOOTPRINT", trade: null };
      this.keyboardCell = { area: hit.area, barIndex: hit.barIndex, rowIndex: hit.rowIndex };
      this.updateDetail(hit);
      this.invalidate("selection");
      this.onSelection(this.selectionPayload(hit));
    }

    updateDetail(hit) {
      if (!this.detail || !hit) return;
      if (hit.area === "dom") {
        const book = this.frame.book;
        const bid = hit.level && hit.level.bid > 0 ? exactValue(hit.level.bid) : "—";
        const ask = hit.level && hit.level.ask > 0 ? exactValue(hit.level.ask) : "—";
        this.detail.textContent = `LIVE DOM · ${book.state} · PRICE ${bucketLabel(hit.row, this.frame)} · PASSIVE BID ${bid} × ASK ${ask} · SPREAD ${exactValue(book.spread)} · UPDATE ${book.lastUpdateId ?? "—"}`;
        return;
      }
      const utc = Number.isFinite(hit.time) ? new Date(hit.time).toISOString() : "—";
      const stamp = Number.isFinite(hit.time)
        ? `JST ${jstClock(hit.time, "millisecond")} · UTC ${utc} · EXCHANGE BAR_TIME`
        : "—";
      const flags = hit.bar.flags.get(hit.priceIndex) || {};
      const markers = [
        hit.priceIndex === hit.bar.va.poc ? "POC" : "",
        hit.priceIndex === hit.bar.va.vah ? "VAH" : "",
        hit.priceIndex === hit.bar.va.val ? "VAL" : "",
        hit.bar.va.inValue.has(hit.priceIndex) ? "VA" : "",
        flags.buy ? flags.buyStack ? "BUY STACK" : "BUY IMB" : "",
        flags.sell ? flags.sellStack ? "SELL STACK" : "SELL IMB" : "",
      ].filter(Boolean).join(" · ") || "—";
      const trade = hit.trade || this.selection && this.selection.trade;
      const tradeText = trade ? ` · TRADE ${trade.tradeId || trade.trade_id} ${trade.side} QTY ${exactValue(trade.quantity)} NOTIONAL ${exactValue(trade.notional)}` : "";
      this.detail.textContent = `${stamp} · PRICE ${bucketLabel(hit.row, this.frame)} · BID ${exactValue(hit.level.bid)} × ASK ${exactValue(hit.level.ask)} · ${markers}${tradeText}`;
    }

    showTooltip(hit, clientX, clientY) {
      if (!this.tooltip) return;
      if (!hit) { this.tooltip.hidden = true; return; }
      this.tooltip.textContent = hit.area === "dom"
        ? `LIVE DOM ${this.frame.book.state} · ${bucketLabel(hit.row, this.frame)} · PASSIVE BID ${hit.level.bid > 0 ? exactValue(hit.level.bid) : "—"} × ASK ${hit.level.ask > 0 ? exactValue(hit.level.ask) : "—"}`
        : `JST ${jstClock(hit.time, "second")} · UTC ${new Date(hit.time).toISOString()} · ${bucketLabel(hit.row, this.frame)} · BID ${exactValue(hit.level.bid)} × ASK ${exactValue(hit.level.ask)}`;
      const rect = this.canvas.parentElement.getBoundingClientRect();
      this.tooltip.style.left = `${clamp(clientX - rect.left + 10, 4, Math.max(4, rect.width - 220))}px`;
      this.tooltip.style.top = `${clamp(clientY - rect.top + 10, 4, Math.max(4, rect.height - 30))}px`;
      this.tooltip.hidden = false;
    }

    bindEvents() {
      this.canvas.addEventListener("wheel", event => {
        event.preventDefault();
        const rect = this.canvas.getBoundingClientRect();
        const ratio = clamp((event.clientX - rect.left - (this.geometry ? this.geometry.axisWidth : 0)) /
          Math.max(1, this.geometry ? this.geometry.plotWidth : rect.width), 0, 1);
        this.setVisibleBars(this.visibleBars + (event.deltaY > 0 ? 1 : -1), ratio);
      }, { passive: false });
      this.canvas.addEventListener("pointerdown", event => {
        const hit = this.hitTest(event.clientX, event.clientY);
        this.drag = { x: event.clientX, offset: this.offset, moved: false, area: hit && hit.area || "footprint" };
        try { this.canvas.setPointerCapture(event.pointerId); } catch (_) {}
      });
      this.canvas.addEventListener("pointermove", event => {
        const hit = this.hitTest(event.clientX, event.clientY);
        this.showTooltip(hit, event.clientX, event.clientY);
        if (!this.drag || !this.geometry || this.drag.area === "dom") return;
        const barsMoved = Math.round((this.drag.x - event.clientX) / Math.max(1, this.geometry.barWidth));
        if (Math.abs(event.clientX - this.drag.x) > 4) this.drag.moved = true;
        if (this.drag.moved) this.setOffset(this.drag.offset + barsMoved);
      });
      const finish = event => {
        if (!this.drag) return;
        const moved = this.drag.moved;
        this.drag = null;
        try { this.canvas.releasePointerCapture(event.pointerId); } catch (_) {}
        if (!moved) this.selectCell(this.hitTest(event.clientX, event.clientY));
      };
      this.canvas.addEventListener("pointerup", finish);
      this.canvas.addEventListener("pointercancel", () => { this.drag = null; });
      this.canvas.addEventListener("pointerleave", () => { if (!this.drag) this.showTooltip(null); });
      this.canvas.addEventListener("contextmenu", event => {
        event.preventDefault(); this.selection = null; this.keyboardCell = null;
        if (this.detail) this.detail.textContent = "SELECT A PRICE CELL · ARROW KEYS MOVE · ESC CLEAR";
        this.invalidate("selection");
        this.onSelection(null);
      });
      this.canvas.addEventListener("keydown", event => {
        if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter", "Escape"].indexOf(event.key) < 0) return;
        event.preventDefault();
        if (event.key === "Escape") {
          this.selection = null; this.keyboardCell = null;
          if (this.detail) this.detail.textContent = "SELECT A PRICE CELL · ARROW KEYS MOVE · ESC CLEAR";
          this.invalidate("selection"); this.onSelection(null); return;
        }
        if (!this.frame || !this.frame.bars.length || !this.frame.rows.length) return;
        const current = this.keyboardCell || { area: "footprint", barIndex: this.frame.bars.length - 1, rowIndex: Math.floor(this.frame.rows.length / 2) };
        if (event.key === "ArrowLeft") {
          if (current.area === "dom") { current.area = "footprint"; current.barIndex = this.frame.bars.length - 1; }
          else current.barIndex -= 1;
        }
        if (event.key === "ArrowRight") {
          if (this.showDom && current.area === "footprint" && current.barIndex >= this.frame.bars.length - 1) {
            current.area = "dom"; current.barIndex = -1;
          } else if (current.area === "footprint") current.barIndex += 1;
        }
        if (event.key === "ArrowUp") current.rowIndex -= 1;
        if (event.key === "ArrowDown") current.rowIndex += 1;
        if (current.area === "footprint") current.barIndex = clamp(current.barIndex, 0, this.frame.bars.length - 1);
        current.rowIndex = clamp(current.rowIndex, 0, this.frame.rows.length - 1);
        this.keyboardCell = current;
        const row = this.frame.rows[current.rowIndex];
        if (current.area === "dom") {
          this.selectCell({ area: "dom", side: "BID", barIndex: -1, rowIndex: current.rowIndex, time: null, bar: null, row,
            level: this.frame.book.byIndex.get(row.index) || { bid: 0, ask: 0, price: row.price }, priceIndex: row.index });
        } else {
          const bar = this.frame.bars[current.barIndex];
          this.selectCell({ area: "footprint", barIndex: current.barIndex, rowIndex: current.rowIndex, time: bar.time, bar, row,
            level: bar.byIndex.get(row.index) || { bid: 0, ask: 0, price: row.price }, priceIndex: row.index });
        }
      });
    }

    updateStatus(dpr) {
      if (!this.status || !this.frame) return;
      const stepLabel = this.frame.requested === "AUTO"
        ? `AUTO → ${this.frame.multiplier} TICK` : `${this.frame.multiplier} TICK`;
      const p95Value = p95(this.renderTimes);
      this.status.textContent = `DISPLAY STEP ${stepLabel} · ${this.frame.rows.length} PRICE ROWS · DPR ${dpr.toFixed(2)} · RENDER P95 ${p95Value.toFixed(2)}ms`;
      if (this.domStatus) {
        const book = this.frame.book;
        this.domStatus.textContent = book.synced
          ? `DOM SYNCED · BID ${exactValue(book.bestBid)} · ASK ${exactValue(book.bestAsk)} · SPREAD ${exactValue(book.spread)} · AGE ${book.ageMs == null ? "—" : Math.round(book.ageMs) + "ms"}`
          : `DOM ${book.state} · BID — · ASK — · SPREAD —`;
        this.domStatus.classList.toggle("warning", !book.synced);
      }
    }
  }

  return {
    CanvasChart,
    DomTradePulseStore,
    passiveSideForAggressor,
    inferTickSize,
    autoMultiplier,
    bucketLevels,
    bucketIndex,
    prepareBook,
    valueArea,
    imbalanceFlags,
    exactValue,
    bucketLabel,
    priceDigits,
    jstClock,
    timeframeMilliseconds,
    p95,
  };
});
