(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.DeltaTimeSales = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const BUY = "BUY";
  const SELL = "SELL";
  const JST_OFFSET_MS = 9 * 60 * 60 * 1000;
  const DEFAULT_CAPACITY = 500;
  const DEFAULT_POOL_SIZE = 32;

  const finite = value => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

  function jstClock(value, precision) {
    const time = typeof value === "number" ? value : Date.parse(value);
    if (!Number.isFinite(time)) return "—";
    const iso = new Date(time + JST_OFFSET_MS).toISOString();
    if (precision === "millisecond") return iso.slice(11, 23);
    if (precision === "second") return iso.slice(11, 19);
    return iso.slice(11, 16);
  }

  function exactValue(value) {
    if (!finite(value)) return "—";
    return String(value);
  }

  function compact(value) {
    if (!finite(value)) return "—";
    const amount = Number(value);
    const absolute = Math.abs(amount);
    if (absolute >= 1e9) return `${(amount / 1e9).toFixed(1)}B`;
    if (absolute >= 1e6) return `${(amount / 1e6).toFixed(1)}M`;
    if (absolute >= 1e3) return `${(amount / 1e3).toFixed(1)}K`;
    if (absolute >= 100) return amount.toFixed(0);
    if (absolute >= 10) return amount.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
    return amount.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  }

  function p95(values) {
    if (!values || !values.length) return 0;
    const sorted = [...values].sort((a, b) => a - b);
    return sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.95) - 1)];
  }

  function tradeKey(symbol, tradeId) {
    return `${String(symbol || "")}\u0000${String(tradeId)}`;
  }

  function normalizeTrade(raw, fallbackSymbol) {
    if (!raw || raw.trade_id === null || raw.trade_id === undefined) return null;
    const symbol = String(raw.symbol || fallbackSymbol || "");
    const side = String(raw.side || "").toUpperCase();
    const eventTime = Date.parse(raw.event_time);
    if (!symbol || (side !== BUY && side !== SELL) || !Number.isFinite(eventTime)) return null;
    if (!finite(raw.price) || !finite(raw.quantity) || !finite(raw.notional)) return null;
    if (Number(raw.price) <= 0 || Number(raw.quantity) <= 0 || Number(raw.notional) <= 0) return null;
    const sequence = raw.sequence === null || raw.sequence === undefined ? null : Number(raw.sequence);
    if (sequence !== null && (!Number.isSafeInteger(sequence) || sequence < 1)) return null;
    return {
      key: tradeKey(symbol, raw.trade_id),
      symbol,
      tradeId: String(raw.trade_id),
      eventTime,
      eventTimeIso: new Date(eventTime).toISOString(),
      price: String(raw.price),
      quantity: String(raw.quantity),
      notional: String(raw.notional),
      side,
      sequence,
    };
  }

  class TapeStore {
    constructor(options) {
      const config = options || {};
      this.capacity = Math.max(1, Math.round(Number(config.capacity) || DEFAULT_CAPACITY));
      this.trades = [];
      this.keys = new Set();
      this.streamId = null;
      this.expectedSequence = null;
      this.gap = false;
      this.gapCount = 0;
      this.droppedCount = 0;
      this.restartCount = 0;
      this.lastRestartStream = null;
      this.historyReceived = 0;
      this.liveReceived = 0;
      this.invalidReceived = 0;
      this.gapReasons = [];
    }

    recordGap(reasons) {
      this.gap = true;
      this.gapCount += 1;
      for (const reason of reasons || []) {
        if (!reason) continue;
        this.gapReasons.push(String(reason));
        if (this.gapReasons.length > 5) this.gapReasons.shift();
      }
    }

    merge(normalized) {
      let added = 0;
      for (const trade of normalized) {
        if (!trade || this.keys.has(trade.key)) continue;
        this.keys.add(trade.key);
        this.trades.push(trade);
        added += 1;
      }
      if (added) {
        this.trades.sort((a, b) => a.eventTime - b.eventTime || a.tradeId.localeCompare(b.tradeId, "en", { numeric: true }));
        if (this.trades.length > this.capacity) {
          const removed = this.trades.splice(0, this.trades.length - this.capacity);
          for (const trade of removed) this.keys.delete(trade.key);
        }
      }
      return added;
    }

    mergeHistory(rows, fallbackSymbol) {
      const normalized = [];
      for (const raw of rows || []) {
        this.historyReceived += 1;
        const trade = normalizeTrade(raw, fallbackSymbol);
        if (trade) normalized.push(trade);
        else this.invalidReceived += 1;
      }
      return this.merge(normalized);
    }

    ingestBatch(payload, fallbackSymbol) {
      const batch = payload || {};
      const streamId = typeof batch.stream_id === "string" && batch.stream_id ? batch.stream_id : null;
      const first = Number(batch.first_sequence);
      const last = Number(batch.last_sequence);
      const accepted = Number(batch.accepted_count);
      const dropped = Number(batch.dropped_count);
      const rawTrades = Array.isArray(batch.trades) ? batch.trades : [];
      let restart = false;
      const reasons = [];

      if (!streamId) reasons.push("MISSING STREAM");
      if (!Number.isSafeInteger(first) || first < 1 || !Number.isSafeInteger(last) || last < first) reasons.push("INVALID BATCH RANGE");
      if (!Number.isSafeInteger(accepted) || accepted < 0 || accepted !== rawTrades.length) reasons.push("ACCEPTED COUNT MISMATCH");
      if (Number.isSafeInteger(first) && Number.isSafeInteger(last) && last - first + 1 !== rawTrades.length) reasons.push("SEQUENCE RANGE MISMATCH");
      if (!Number.isSafeInteger(dropped) || dropped < 0) reasons.push("INVALID DROPPED COUNT");

      if (streamId && this.streamId && streamId !== this.streamId) {
        restart = true;
        this.restartCount += 1;
        this.lastRestartStream = streamId;
        this.expectedSequence = null;
        this.gap = false;
        this.gapReasons = [];
      }
      if (streamId && this.streamId !== streamId) this.streamId = streamId;
      if (this.expectedSequence !== null && Number.isSafeInteger(first) && first !== this.expectedSequence) {
        reasons.push(`EXPECTED ${this.expectedSequence} GOT ${first}`);
      }
      if (Number.isSafeInteger(dropped) && dropped > 0) {
        this.droppedCount += dropped;
        reasons.push(`DROPPED ${dropped}`);
      }

      const normalized = [];
      for (let index = 0; index < rawTrades.length; index += 1) {
        this.liveReceived += 1;
        const trade = normalizeTrade(rawTrades[index], fallbackSymbol);
        if (!trade) {
          this.invalidReceived += 1;
          reasons.push("INVALID TRADE");
          continue;
        }
        if (Number.isSafeInteger(first) && trade.sequence !== first + index) {
          reasons.push("NONCONTIGUOUS TRADE SEQUENCE");
          continue;
        }
        normalized.push(trade);
      }
      if (Number.isSafeInteger(last)) this.expectedSequence = last + 1;
      const uniqueReasons = [...new Set(reasons)];
      if (uniqueReasons.length) this.recordGap(uniqueReasons);
      const added = this.merge(normalized);
      return { added, restart, gap: this.gap, reasons: uniqueReasons };
    }

    filtered(filters) {
      const config = filters || {};
      const side = config.side === BUY || config.side === SELL ? config.side : "ALL";
      const minimumQuantity = Math.max(0, Number(config.minimumQuantity) || 0);
      const minimumNotional = Math.max(0, Number(config.minimumNotional) || 0);
      const largeThreshold = Math.max(0, Number(config.largeThreshold) || 0);
      return this.trades.filter(trade => {
        if (side !== "ALL" && trade.side !== side) return false;
        if (Number(trade.quantity) < minimumQuantity) return false;
        if (Number(trade.notional) < minimumNotional) return false;
        if (config.largeOnly && Number(trade.notional) < largeThreshold) return false;
        return true;
      });
    }
  }

  class TimeSalesView {
    constructor(options) {
      const config = options || {};
      this.viewport = config.viewport;
      this.rowsElement = config.rowsElement;
      this.spacer = config.spacer;
      this.detail = config.detail;
      this.stateElement = config.stateElement;
      this.gapElement = config.gapElement;
      this.countElement = config.countElement;
      this.filterElement = config.filterElement;
      this.onSelect = config.onSelect || function () {};
      this.onStreamRestart = config.onStreamRestart || function () {};
      this.onAcceptedTrades = config.onAcceptedTrades || function () {};
      this.store = new TapeStore({ capacity: config.capacity || DEFAULT_CAPACITY });
      this.poolSize = clamp(Math.round(Number(config.poolSize) || DEFAULT_POOL_SIZE), 20, 40);
      this.rowHeight = Math.max(28, Math.round(Number(config.rowHeight) || 28));
      this.filters = { side: "ALL", minimumQuantity: 0, minimumNotional: 0, largeOnly: false, largeThreshold: 10000 };
      this.connected = false;
      this.selectedKey = null;
      this.linkedKeys = new Set();
      this.selectionError = null;
      this.currentRows = [];
      this.pool = [];
      this.renderTimes = [];
      this.drawPending = false;
      this.visibleNodeCount = 0;
      this.createPool();
      this.bindEvents();
      this.render();
    }

    createPool() {
      if (!this.rowsElement || typeof document === "undefined") return;
      for (let index = 0; index < this.poolSize; index += 1) {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "tape-row";
        row.setAttribute("role", "row");
        row.innerHTML = '<span class="tape-time"></span><span class="tape-price"></span><span class="tape-qty"></span><span class="tape-side"></span>';
        row.addEventListener("click", () => {
          const visibleIndex = Number(row.dataset.visibleIndex);
          const trade = this.currentRows[visibleIndex];
          if (trade) this.selectTrade(trade, true);
        });
        this.rowsElement.appendChild(row);
        this.pool.push(row);
      }
    }

    bindEvents() {
      if (!this.viewport) return;
      this.viewport.addEventListener("scroll", () => this.scheduleRender());
      this.viewport.addEventListener("keydown", event => {
        if (!["ArrowUp", "ArrowDown", "Enter", "Escape"].includes(event.key)) return;
        event.preventDefault();
        if (event.key === "Escape") {
          this.selectedKey = null;
          this.selectionError = null;
          this.render();
          return;
        }
        if (!this.currentRows.length) return;
        let index = this.currentRows.findIndex(trade => trade.key === this.selectedKey);
        if (index < 0) index = 0;
        if (event.key === "ArrowUp") index -= 1;
        if (event.key === "ArrowDown") index += 1;
        index = clamp(index, 0, this.currentRows.length - 1);
        const trade = this.currentRows[index];
        this.selectTrade(trade, event.key === "Enter");
        const top = index * this.rowHeight;
        if (top < this.viewport.scrollTop) this.viewport.scrollTop = top;
        else if (top + this.rowHeight > this.viewport.scrollTop + this.viewport.clientHeight) {
          this.viewport.scrollTop = top + this.rowHeight - this.viewport.clientHeight;
        }
      });
    }

    setConnected(connected) {
      this.connected = Boolean(connected);
      this.updateStatus();
    }

    mergeHistory(rows, symbol) {
      const atTop = !this.viewport || this.viewport.scrollTop <= 2;
      const added = this.store.mergeHistory(rows, symbol);
      if (atTop && this.viewport) this.viewport.scrollTop = 0;
      this.render();
      return added;
    }

    ingestBatch(payload, symbol) {
      const atTop = !this.viewport || this.viewport.scrollTop <= 2;
      const before = new Set(this.store.keys);
      const result = this.store.ingestBatch(payload, symbol);
      const accepted = this.store.trades.filter(trade => !before.has(trade.key));
      if (accepted.length) { try { this.onAcceptedTrades(accepted, result); } catch (_) {} }
      if (result.restart) this.onStreamRestart(this.store.streamId);
      if (atTop && this.viewport) this.viewport.scrollTop = 0;
      this.render();
      return result;
    }

    setFilters(next) {
      this.filters = Object.assign({}, this.filters, next || {});
      if (this.viewport) this.viewport.scrollTop = 0;
      this.render();
    }

    isFiltered() {
      return this.filters.side !== "ALL" || Number(this.filters.minimumQuantity) > 0 ||
        Number(this.filters.minimumNotional) > 0 || Boolean(this.filters.largeOnly);
    }

    selectTrade(trade, notify) {
      if (!trade) return;
      this.selectedKey = trade.key;
      this.selectionError = null;
      this.updateDetail(trade);
      this.render();
      if (notify) this.onSelect(trade);
    }

    markSelectionError(message) {
      this.selectionError = message || "BAR NOT LOADED";
      this.updateStatus();
    }

    highlightBucket(selection) {
      this.linkedKeys.clear();
      if (selection && Number.isFinite(selection.barTime) && finite(selection.price) && finite(selection.step)) {
        const start = Number(selection.barTime);
        const end = start + Math.max(1, Number(selection.timeframeMs) || 60000);
        const low = Number(selection.price);
        const high = low + Number(selection.step);
        const epsilon = Math.max(1e-12, Number(selection.tick) * 1e-6 || 1e-12);
        for (const trade of this.store.trades) {
          const price = Number(trade.price);
          if (trade.eventTime >= start && trade.eventTime < end && price + epsilon >= low && price < high - epsilon) {
            this.linkedKeys.add(trade.key);
          }
        }
      }
      this.render();
    }

    updateDetail(trade) {
      if (!this.detail || !trade) return;
      this.detail.textContent = `JST ${jstClock(trade.eventTime, "millisecond")} · UTC ${trade.eventTimeIso} · EXCHANGE EVENT_TIME · ${trade.side} · PRICE ${exactValue(trade.price)} · QTY ${exactValue(trade.quantity)} · NOTIONAL ${exactValue(trade.notional)} · TRADE ${trade.tradeId}`;
    }

    scheduleRender() {
      if (this.drawPending) return;
      this.drawPending = true;
      const schedule = typeof requestAnimationFrame === "function" ? requestAnimationFrame : callback => setTimeout(callback, 0);
      schedule(() => { this.drawPending = false; this.render(); });
    }

    render() {
      const started = typeof performance !== "undefined" ? performance.now() : Date.now();
      this.currentRows = this.store.filtered(this.filters).slice().reverse();
      if (this.spacer) this.spacer.style.height = `${this.currentRows.length * this.rowHeight}px`;
      const start = this.viewport ? Math.floor(this.viewport.scrollTop / this.rowHeight) : 0;
      this.visibleNodeCount = 0;
      for (let poolIndex = 0; poolIndex < this.pool.length; poolIndex += 1) {
        const visibleIndex = start + poolIndex;
        const trade = this.currentRows[visibleIndex];
        const row = this.pool[poolIndex];
        if (!trade) {
          row.hidden = true;
          row.removeAttribute("data-key");
          continue;
        }
        this.visibleNodeCount += 1;
        const large = Number(trade.notional) >= Number(this.filters.largeThreshold);
        row.hidden = false;
        row.dataset.key = trade.key;
        row.dataset.visibleIndex = String(visibleIndex);
        row.style.transform = `translateY(${visibleIndex * this.rowHeight}px)`;
        row.className = `tape-row ${trade.side === BUY ? "buy" : "sell"}${large ? " large" : ""}${trade.key === this.selectedKey ? " selected" : ""}${this.linkedKeys.has(trade.key) ? " linked" : ""}`;
        row.querySelector(".tape-time").textContent = jstClock(trade.eventTime, "millisecond");
        row.querySelector(".tape-price").textContent = compact(trade.price);
        row.querySelector(".tape-qty").textContent = compact(trade.quantity);
        row.querySelector(".tape-side").textContent = trade.side === BUY ? "B" : "S";
        row.title = `JST ${jstClock(trade.eventTime, "millisecond")} · UTC ${trade.eventTimeIso} · PRICE ${trade.price} · QTY ${trade.quantity} · NOTIONAL ${trade.notional} · ${trade.side}`;
        row.setAttribute("aria-label", row.title);
      }
      const elapsed = (typeof performance !== "undefined" ? performance.now() : Date.now()) - started;
      this.renderTimes.push(elapsed);
      if (this.renderTimes.length > 120) this.renderTimes.shift();
      this.updateStatus();
    }

    updateStatus() {
      if (this.stateElement) {
        const text = !this.connected ? "RECONNECTING" : this.store.gap ? "TAPE GAP" : "LIVE";
        this.stateElement.textContent = text;
        this.stateElement.dataset.state = text.replace(/ /g, "_");
      }
      if (this.gapElement) {
        const restart = this.store.lastRestartStream ? `STREAM RESTART ${this.store.lastRestartStream.slice(0, 8)}` : "STREAM RESTART —";
        const gap = this.store.gap ? `TAPE GAP · ${this.store.gapReasons.join(" / ") || "DETECTED"}` : "TAPE GAP · —";
        this.gapElement.textContent = `${gap} · DROP ${this.store.droppedCount} · ${restart}${this.selectionError ? ` · ${this.selectionError}` : ""}`;
        this.gapElement.classList.toggle("warning", this.store.gap || Boolean(this.selectionError));
      }
      if (this.filterElement) {
        this.filterElement.textContent = `FILTER ${this.filters.side} · QTY ≥ ${this.filters.minimumQuantity} · NOTIONAL ≥ ${this.filters.minimumNotional} · LARGE ONLY ${this.filters.largeOnly ? "ON" : "OFF"} · LARGE ≥ ${this.filters.largeThreshold}`;
        this.filterElement.classList.toggle("active", this.isFiltered());
      }
      if (this.countElement) {
        this.countElement.textContent = `HIST ${this.store.historyReceived} · LIVE ${this.store.liveReceived} · KEPT ${this.store.trades.length}/${this.store.capacity} · SHOWN ${this.currentRows.length} · DOM ${this.visibleNodeCount}/${this.poolSize} · GAPS ${this.store.gapCount} · RENDER P95 ${p95(this.renderTimes).toFixed(2)}ms`;
      }
    }
  }

  return {
    TapeStore,
    TimeSalesView,
    normalizeTrade,
    tradeKey,
    jstClock,
    exactValue,
    compact,
    p95,
  };
});


