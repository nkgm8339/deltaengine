(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.DeltaOrderBookHeatmap = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const MAX_SAFE = Number.MAX_SAFE_INTEGER;
  const JST_OFFSET_MS = 9 * 60 * 60 * 1000;
  const FONT = '"Cascadia Mono","JetBrains Mono",ui-monospace,monospace';
  const KNOWN_BOOK_STATES = new Set([
    "NO_SNAPSHOT", "NO_CONNECTION", "DISCONNECTED", "RESYNCING", "UNSYNCED",
    "STALE", "EMPTY", "LOCKED", "CROSSED", "INVALID", "GAP",
  ]);
  const HEAT_STOPS = [
    [0, [4, 18, 58]], [0.35, [8, 83, 171]], [0.62, [0, 213, 235]],
    [0.84, [255, 221, 54]], [1, [255, 255, 210]],
  ];
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const finite = value => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
  const positive = value => finite(value) && Number(value) > 0;
  const parseTime = value => typeof value === "number" ? value : Date.parse(value);
  const uuid = value => typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
  const FRAME_BUDGET_MS = 16;
  const p95 = values => percentile(values, 0.95);

  function percentile(values, quantile) {
    const sorted = (values || []).map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    if (!sorted.length) return 0;
    return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * quantile) - 1))];
  }

  function jstClock(value, precision) {
    const timestamp = Number(value);
    if (!Number.isFinite(timestamp)) return "—";
    const iso = new Date(timestamp + JST_OFFSET_MS).toISOString();
    if (precision === "millisecond") return iso.slice(11, 23);
    if (precision === "second") return iso.slice(11, 19);
    return iso.slice(11, 16);
  }

  function priceDigits(step) {
    if (!positive(step)) return 1;
    const text = Number(step).toFixed(10).replace(/0+$/, "");
    const dot = text.indexOf(".");
    return dot < 0 ? 0 : text.length - dot - 1;
  }

  function validateBookPayload(raw) {
    const payload = raw || {};
    const errors = [];
    const synced = payload.sync_state === "SYNCED";
    if (!uuid(payload.book_stream_id)) errors.push("INVALID STREAM ID");
    const sequence = Number(payload.book_sequence);
    const updateId = Number(payload.last_update_id);
    const depth = Number(payload.depth_levels);
    const eventTime = parseTime(payload.event_time);
    const projectionTime = parseTime(payload.projection_time);
    if (!Number.isSafeInteger(sequence) || sequence < 1) errors.push("INVALID BOOK SEQUENCE");
    if (!Number.isFinite(eventTime) || !Number.isFinite(projectionTime)) errors.push("INVALID TIME");
    if (!Number.isSafeInteger(updateId) || updateId < 0 || updateId > MAX_SAFE) errors.push("INVALID UPDATE ID");
    if (!Number.isSafeInteger(depth) || depth < 1) errors.push("INVALID DEPTH");
    const bids = Array.isArray(payload.bids) ? payload.bids : [];
    const asks = Array.isArray(payload.asks) ? payload.asks : [];
    if (!synced) {
      if (!KNOWN_BOOK_STATES.has(String(payload.sync_state || ""))) errors.push("UNKNOWN STATE");
      if (bids.length || asks.length || payload.best_bid != null || payload.best_ask != null || payload.spread != null) {
        errors.push("FAIL CLOSED LEVELS");
      }
    } else {
      const validLevels = (levels, descending) => levels.length > 0 && levels.every((level, index) => {
        if (!level || !positive(level.price) || !positive(level.qty)) return false;
        if (!index) return true;
        const previous = Number(levels[index - 1].price);
        const current = Number(level.price);
        return descending ? previous > current : previous < current;
      });
      if (!validLevels(bids, true) || !validLevels(asks, false)) errors.push("INVALID OR UNSORTED LEVELS");
      if (!positive(payload.best_bid) || !positive(payload.best_ask) || Number(payload.best_bid) >= Number(payload.best_ask)) errors.push("INVALID BEST");
      if (bids.length && Number(bids[0].price) !== Number(payload.best_bid)) errors.push("BEST BID MISMATCH");
      if (asks.length && Number(asks[0].price) !== Number(payload.best_ask)) errors.push("BEST ASK MISMATCH");
      const expectedSpread = Number(payload.best_ask) - Number(payload.best_bid);
      if (!positive(payload.spread) || Math.abs(Number(payload.spread) - expectedSpread) > Math.max(1e-10, Math.abs(expectedSpread) * 1e-9)) {
        errors.push("SPREAD MISMATCH");
      }
    }
    if (errors.length) return { valid: false, synced, errors, payload: null };
    return {
      valid: true,
      synced,
      errors,
      payload: {
        book_stream_id: payload.book_stream_id,
        book_sequence: sequence,
        event_time: eventTime,
        projection_time: projectionTime,
        last_update_id: updateId,
        depth_levels: depth,
        sync_state: payload.sync_state,
        bids: bids.map(level => ({ price: Number(level.price), qty: Number(level.qty) })),
        asks: asks.map(level => ({ price: Number(level.price), qty: Number(level.qty) })),
        best_bid: synced ? Number(payload.best_bid) : null,
        best_ask: synced ? Number(payload.best_ask) : null,
        spread: synced ? Number(payload.spread) : null,
        age_ms: finite(payload.age_ms) ? Math.max(0, Number(payload.age_ms)) : null,
      },
    };
  }

  function compactFrame(payload, receivedTime) {
    return {
      streamId: payload.book_stream_id,
      sequence: payload.book_sequence,
      eventTime: payload.event_time,
      projectionTime: payload.projection_time,
      lastUpdateId: payload.last_update_id,
      depthLevels: payload.depth_levels,
      syncState: payload.sync_state,
      bestBid: payload.best_bid,
      bestAsk: payload.best_ask,
      spread: payload.spread,
      ageMs: payload.age_ms,
      receivedTime,
      bidPrices: Float64Array.from(payload.bids.map(level => level.price)),
      bidQty: Float32Array.from(payload.bids.map(level => level.qty)),
      askPrices: Float64Array.from(payload.asks.map(level => level.price)),
      askQty: Float32Array.from(payload.asks.map(level => level.qty)),
    };
  }

  function publicFrame(frame) {
    const levels = (prices, quantities) => Array.from(prices, (price, index) => ({ price, qty: quantities[index] }));
    return {
      book_stream_id: frame.streamId,
      book_sequence: frame.sequence,
      event_time: frame.eventTime,
      projection_time: frame.projectionTime,
      last_update_id: frame.lastUpdateId,
      depth_levels: frame.depthLevels,
      sync_state: frame.syncState,
      best_bid: frame.bestBid,
      best_ask: frame.bestAsk,
      spread: frame.spread,
      age_ms: frame.ageMs,
      bids: levels(frame.bidPrices, frame.bidQty),
      asks: levels(frame.askPrices, frame.askQty),
    };
  }

  class HeatmapBookStore {
    constructor(options) {
      const config = options || {};
      this.maxAgeMs = positive(config.maxAgeMs) ? Number(config.maxAgeMs) : 900000;
      this.maxFrames = positive(config.maxFrames) ? Math.floor(Number(config.maxFrames)) : 9000;
      this.maxGaps = positive(config.maxGaps) ? Math.floor(Number(config.maxGaps)) : 2048;
      this.frames = [];
      this.gaps = [];
      this.activeGap = null;
      this.streamId = null;
      this.expectedSequence = null;
      this.lastEventTime = null;
      this.sessionStart = null;
      this.duplicates = 0;
      this.invalid = 0;
      this.restartCount = 0;
      this.deliveryGapCount = 0;
    }

    get gap() { return this.activeGap || (this.gaps.length ? this.gaps[this.gaps.length - 1] : null); }

    _appendGap(reason, start, end, extra) {
      const safeStart = Number.isFinite(Number(start)) ? Number(start) : Date.now();
      const safeEnd = Number.isFinite(Number(end)) ? Math.max(safeStart, Number(end)) : null;
      const marker = { reason, start: safeStart, end: safeEnd, ...(extra || {}) };
      this.gaps.push(marker);
      if (this.gaps.length > this.maxGaps) this.gaps.splice(0, this.gaps.length - this.maxGaps);
      return marker;
    }

    _startGap(reason, start, extra) {
      if (this.activeGap && this.activeGap.reason === reason) return this.activeGap;
      if (this.activeGap) this._closeGap(start);
      this.activeGap = this._appendGap(reason, start, null, extra);
      return this.activeGap;
    }

    _closeGap(end) {
      if (!this.activeGap) return;
      this.activeGap.end = Math.max(this.activeGap.start, Number(end) || this.activeGap.start);
      this.activeGap = null;
    }

    ingest(raw, nowMs) {
      const now = Number.isFinite(Number(nowMs)) ? Number(nowMs) : Date.now();
      const checked = validateBookPayload(raw);
      if (!checked.valid) {
        this.invalid += 1;
        const start = Number.isFinite(parseTime(raw && raw.projection_time)) ? parseTime(raw.projection_time) : now;
        this._startGap("INVALID BOOK PAYLOAD", start, { errors: checked.errors.slice() });
        this.prune(now);
        return { accepted: false, reason: "INVALID BOOK PAYLOAD", errors: checked.errors };
      }
      const payload = checked.payload;
      const sequence = payload.book_sequence;
      if (this.streamId && payload.book_stream_id !== this.streamId) {
        this.restartCount += 1;
        this._appendGap("BOOK STREAM RESTART", this.lastEventTime || payload.event_time, payload.event_time, {
          previous_stream: this.streamId, received_stream: payload.book_stream_id,
        });
        this.expectedSequence = null;
      }
      this.streamId = payload.book_stream_id;
      if (this.expectedSequence !== null) {
        if (sequence < this.expectedSequence) {
          this.duplicates += 1;
          return { accepted: false, duplicate: true, reason: "DUPLICATE BOOK SEQUENCE" };
        }
        if (sequence > this.expectedSequence) {
          this.deliveryGapCount += 1;
          this._appendGap("BOOK DELIVERY GAP", this.lastEventTime || payload.event_time, payload.event_time, {
            expected: this.expectedSequence, received: sequence,
          });
        }
      }
      this.expectedSequence = sequence + 1;
      this.lastEventTime = Math.max(this.lastEventTime || payload.event_time, payload.event_time);
      if (!checked.synced) {
        this._startGap(`BOOK ${payload.sync_state}`, payload.projection_time, { sequence });
        this.prune(now);
        return { accepted: true, synced: false, frame: null };
      }
      this._closeGap(payload.event_time);
      const frame = compactFrame(payload, now);
      this.frames.push(frame);
      if (this.sessionStart === null) this.sessionStart = frame.eventTime;
      this.prune(now);
      return { accepted: true, synced: true, frame };
    }

    markDisconnected(atMs) { this._startGap("WEBSOCKET DISCONNECT", atMs, {}); }
    markLocalStale(atMs) { this._startGap("LOCAL STALE", atMs, {}); }
    prune(nowMs) {
      const now = Number(nowMs);
      if (!Number.isFinite(now)) return;
      const cutoff = now - this.maxAgeMs;
      let first = 0;
      while (first < this.frames.length && this.frames[first].eventTime < cutoff) first += 1;
      if (first) this.frames.splice(0, first);
      if (this.frames.length > this.maxFrames) this.frames.splice(0, this.frames.length - this.maxFrames);
      this.gaps = this.gaps.filter(gap => (gap.end == null ? now : gap.end) >= cutoff);
      if (this.gaps.length > this.maxGaps) this.gaps.splice(0, this.gaps.length - this.maxGaps);
    }
    visibleFrames(start, end) {
      const inside = this.frames.filter(frame => frame.eventTime >= start && frame.eventTime <= end);
      const previous = [...this.frames].reverse().find(frame => frame.eventTime < start);
      return previous ? [previous, ...inside] : inside;
    }
    visibleGaps(start, end) { return this.gaps.filter(gap => gap.start <= end && (gap.end == null || gap.end >= start)); }
    snapshot() { return this.frames.map(frame => publicFrame(frame)); }
    estimatedBytes() {
      return this.frames.reduce((total, frame) => total + 128 + frame.bidPrices.byteLength + frame.bidQty.byteLength + frame.askPrices.byteLength + frame.askQty.byteLength, 0);
    }
  }

  class HeatmapTradeStore {
    constructor(options) {
      const config = options || {};
      this.maxAgeMs = positive(config.maxAgeMs) ? Number(config.maxAgeMs) : 900000;
      this.capacity = positive(config.capacity) ? Math.floor(Number(config.capacity)) : 100000;
      this.maxMarkers = positive(config.maxMarkers) ? Math.floor(Number(config.maxMarkers)) : 1024;
      this.trades = [];
      this.keys = new Set();
      this.markers = [];
      this.retentionLimited = false;
    }
    ingest(trades, nowMs, context) {
      const metadata = context || {};
      let added = 0;
      for (const raw of trades || []) {
        const streamId = String(raw.stream_id || raw.streamId || metadata.stream_id || metadata.streamId || "");
        const tradeId = raw.trade_id != null ? raw.trade_id : raw.tradeId;
        const sequence = Number(raw.sequence);
        const eventTime = parseTime(raw.event_time != null ? raw.event_time : raw.eventTime);
        const price = Number(raw.price), quantity = Number(raw.quantity), notional = Number(raw.notional);
        const side = String(raw.side || "").toUpperCase();
        if (!streamId || tradeId == null || !Number.isSafeInteger(sequence) || sequence < 1 || !Number.isFinite(eventTime) ||
            !positive(price) || !positive(quantity) || !positive(notional) || !["BUY", "SELL"].includes(side)) continue;
        const key = `${streamId}\u0000${tradeId}\u0000${sequence}`;
        if (this.keys.has(key)) continue;
        this.keys.add(key);
        this.trades.push({ key, streamId, tradeId: String(tradeId), sequence, eventTime, price, quantity, notional, side });
        added += 1;
      }
      if (added) this.trades.sort((a, b) => a.eventTime - b.eventTime || a.sequence - b.sequence);
      this.prune(nowMs);
      return { added, count: this.trades.length };
    }
    recordContinuity(result, streamId, atMs) {
      const outcome = result || {};
      if (!outcome.gap && !outcome.restart) return;
      const reason = outcome.restart ? "TAPE STREAM RESTART" : "TAPE GAP";
      this.markers.push({ reason, time: Number(atMs) || Date.now(), streamId: streamId || null, details: (outcome.reasons || []).slice() });
      if (this.markers.length > this.maxMarkers) this.markers.splice(0, this.markers.length - this.maxMarkers);
    }
    prune(nowMs) {
      const now = Number(nowMs);
      if (!Number.isFinite(now)) return;
      const cutoff = now - this.maxAgeMs;
      let first = 0;
      while (first < this.trades.length && this.trades[first].eventTime < cutoff) first += 1;
      if (first) this.trades.splice(0, first);
      if (this.trades.length > this.capacity) {
        this.trades.splice(0, this.trades.length - this.capacity);
        this.retentionLimited = true;
      }
      this.keys = new Set(this.trades.map(trade => trade.key));
      this.markers = this.markers.filter(marker => marker.time >= cutoff);
    }
    visibleTrades(start, end) {
      let low = 0, high = this.trades.length;
      while (low < high) { const middle = (low + high) >> 1; if (this.trades[middle].eventTime < start) low = middle + 1; else high = middle; }
      const first = low; high = this.trades.length;
      while (low < high) { const middle = (low + high) >> 1; if (this.trades[middle].eventTime <= end) low = middle + 1; else high = middle; }
      return this.trades.slice(first, low);
    }
    snapshot() { return this.trades.map(trade => ({ ...trade })); }
  }

  function frameLevels(frame, side) {
    if (!frame) return [];
    if (side === "BID" && frame.bidPrices) return Array.from(frame.bidPrices, (price, index) => ({ price, qty: frame.bidQty[index] }));
    if (side === "ASK" && frame.askPrices) return Array.from(frame.askPrices, (price, index) => ({ price, qty: frame.askQty[index] }));
    const source = side === "BID" ? frame.bids : frame.asks;
    return Array.isArray(source) ? source : [];
  }

  function frameValue(frame, compactKey, publicKey) {
    return frame && frame[compactKey] !== undefined ? frame[compactKey] : frame && frame[publicKey];
  }

  function inferBookTick(frames, fallback) {
    let smallest = Infinity;
    for (const frame of frames || []) {
      for (const side of ["BID", "ASK"]) {
        const levels = frameLevels(frame, side);
        for (let index = 1; index < levels.length; index += 1) {
          const gap = Math.abs(Number(levels[index - 1].price) - Number(levels[index].price));
          if (gap > 1e-10 && gap < smallest) smallest = gap;
        }
      }
      const spread = Number(frameValue(frame, "spread", "spread"));
      if (spread > 1e-10 && spread < smallest) smallest = spread;
    }
    if (Number.isFinite(smallest)) return Number(smallest.toPrecision(10));
    return positive(fallback) ? Number(fallback) : null;
  }

  function niceMultiplier(required) {
    const target = Math.max(1, Number(required) || 1);
    const exponent = Math.floor(Math.log10(target));
    for (let power = exponent; power <= exponent + 2; power += 1) {
      const scale = Math.pow(10, power);
      for (const base of [1, 2, 5]) if (base * scale >= target) return Math.max(1, Math.round(base * scale));
    }
    return Math.max(1, Math.ceil(target));
  }

  function selectDisplayStep(tickSize, sourceRows, mode, targetRows) {
    if (!positive(tickSize)) return null;
    if ([1, 2, 5, 10].includes(Number(mode))) return Number(mode);
    const rows = Math.max(1, Number(sourceRows) || 1);
    const target = clamp(Number(targetRows) || 65, 40, 90);
    return niceMultiplier(rows / target);
  }

  function bucketBookFrame(frame, tickSize, multiplier) {
    const tick = Number(tickSize), mult = Math.max(1, Math.round(Number(multiplier) || 1));
    if (!(tick > 0)) return [];
    const cacheKey = `${tick}:${mult}`;
    if (frame && frame.bidPrices && frame._bucketCache && frame._bucketCache.has(cacheKey)) return frame._bucketCache.get(cacheKey);
    const buckets = new Map();
    const add = (side, prices, quantities) => {
      for (let levelIndex = 0; levelIndex < prices.length; levelIndex += 1) {
        const price = Number(prices[levelIndex]), quantity = Number(quantities[levelIndex]);
        if (!(price > 0) || !(quantity > 0)) continue;
        const index = Math.floor(Math.round(price / tick) / mult) * mult;
        const key = `${side}:${index}`;
        const bucket = buckets.get(key) || { side, index, price: index * tick, quantity: 0, level_count: 0 };
        bucket.quantity += quantity;
        bucket.level_count += 1;
        buckets.set(key, bucket);
      }
    };
    if (frame && frame.bidPrices) {
      add("BID", frame.bidPrices, frame.bidQty); add("ASK", frame.askPrices, frame.askQty);
    } else {
      const bids = frameLevels(frame, "BID"), asks = frameLevels(frame, "ASK");
      add("BID", bids.map(level => level.price), bids.map(level => level.qty));
      add("ASK", asks.map(level => level.price), asks.map(level => level.qty));
    }
    const output = [...buckets.values()];
    if (frame && frame.bidPrices) { if (!frame._bucketCache) frame._bucketCache = new Map(); frame._bucketCache.set(cacheKey, output); if (frame._bucketCache.size > 6) frame._bucketCache.delete(frame._bucketCache.keys().next().value); }
    return output;
  }

  function buildTimeColumns(frames, start, end, width) {
    const left = Number(start), right = Number(end), count = Math.max(1, Math.floor(Number(width) || 1));
    if (!(right > left)) return [];
    const duration = right - left;
    return Array.from({ length: count }, (_, index) => ({
      start: left + duration * index / count,
      end: left + duration * (index + 1) / count,
    }));
  }

  function uncoveredSegments(start, end, gaps) {
    let segments = [[start, end]];
    for (const gap of gaps || []) {
      const gapStart = Number(gap.start), gapEnd = gap.end == null ? Infinity : Number(gap.end);
      if (!(gapEnd > start && gapStart < end)) continue;
      const next = [];
      for (const [left, right] of segments) {
        if (gapEnd <= left || gapStart >= right) next.push([left, right]);
        else {
          if (gapStart > left) next.push([left, Math.min(gapStart, right)]);
          if (gapEnd < right) next.push([Math.max(gapEnd, left), right]);
        }
      }
      segments = next;
      if (!segments.length) break;
    }
    return segments.filter(([left, right]) => right > left);
  }

  function durationWeightedCells(intervals, columns, gaps) {
    const output = (columns || []).map(() => ({ duration: 0, values: new Map(), levels: new Map() }));
    if (!output.length || !intervals || !intervals.length) return output.map(() => []);
    const firstStart = columns[0].start;
    const columnWidth = columns[0].end - columns[0].start;
    for (const interval of intervals) {
      const left = Math.max(Number(interval.start), columns[0].start);
      const right = Math.min(Number(interval.end), columns[columns.length - 1].end);
      if (!(right > left)) continue;
      for (const [segmentStart, segmentEnd] of uncoveredSegments(left, right, gaps)) {
        const first = clamp(Math.floor((segmentStart - firstStart) / columnWidth), 0, columns.length - 1);
        const last = clamp(Math.floor((Math.max(segmentStart, segmentEnd - 1e-7) - firstStart) / columnWidth), 0, columns.length - 1);
        for (let columnIndex = first; columnIndex <= last; columnIndex += 1) {
          const column = columns[columnIndex];
          const overlap = Math.max(0, Math.min(segmentEnd, column.end) - Math.max(segmentStart, column.start));
          if (!overlap) continue;
          const target = output[columnIndex];
          target.duration += overlap;
          for (const cell of interval.cells || []) {
            const key = `${cell.side}:${cell.index}`;
            target.values.set(key, (target.values.get(key) || 0) + Number(cell.quantity) * overlap);
            target.levels.set(key, Math.max(target.levels.get(key) || 0, Number(cell.level_count) || 1));
          }
        }
      }
    }
    return output.map(column => {
      if (!(column.duration > 0)) return [];
      return [...column.values].map(([key, weighted]) => {
        const split = key.indexOf(":");
        return {
          side: key.slice(0, split),
          index: Number(key.slice(split + 1)),
          quantity: weighted / column.duration,
          level_count: column.levels.get(key) || 1,
        };
      });
    });
  }

  function durationWeightedRaster(intervals, columns, gaps, minIndex, maxIndex, multiplier) {
    const width = columns.length;
    const mult = Math.max(1, Math.round(Number(multiplier) || 1));
    const firstIndex = Math.floor(Number(minIndex) / mult) * mult;
    const lastIndex = Math.ceil(Number(maxIndex) / mult) * mult;
    const rows = Math.max(1, Math.round((lastIndex - firstIndex) / mult) + 1);
    const bid = new Float32Array(width * rows), ask = new Float32Array(width * rows), durations = new Float64Array(width);
    if (!width || !intervals.length) return { bid, ask, durations, width, rows, firstIndex, lastIndex, multiplier: mult };
    const origin = columns[0].start, columnWidth = columns[0].end - columns[0].start, rightEdge = columns[width - 1].end;
    for (const interval of intervals) {
      const left = Math.max(Number(interval.start), origin), right = Math.min(Number(interval.end), rightEdge);
      if (!(right > left)) continue;
      const segments = gaps && gaps.length ? uncoveredSegments(left, right, gaps) : [[left, right]];
      for (const segment of segments) {
        const firstColumn = clamp(Math.floor((segment[0] - origin) / columnWidth), 0, width - 1);
        const lastColumn = clamp(Math.floor((Math.max(segment[0], segment[1] - 1e-7) - origin) / columnWidth), 0, width - 1);
        for (let columnIndex = firstColumn; columnIndex <= lastColumn; columnIndex += 1) {
          const overlap = Math.max(0, Math.min(segment[1], columns[columnIndex].end) - Math.max(segment[0], columns[columnIndex].start));
          if (!overlap) continue;
          durations[columnIndex] += overlap;
          const base = columnIndex * rows;
          for (const cell of interval.cells || []) {
            const row = Math.round((Number(cell.index) - firstIndex) / mult);
            if (row < 0 || row >= rows) continue;
            (cell.side === "BID" ? bid : ask)[base + row] += Number(cell.quantity) * overlap;
          }
        }
      }
    }
    for (let columnIndex = 0; columnIndex < width; columnIndex += 1) {
      const duration = durations[columnIndex];
      if (!(duration > 0)) continue;
      const base = columnIndex * rows;
      for (let row = 0; row < rows; row += 1) { bid[base + row] /= duration; ask[base + row] /= duration; }
    }
    return { bid, ask, durations, width, rows, firstIndex, lastIndex, multiplier: mult };
  }

  function computeHeatScale(cells, multiplier) {
    const flat = Array.isArray(cells) && Array.isArray(cells[0]) ? cells.flat() : (cells || []);
    const values = [];
    for (const cell of flat) { const value = typeof cell === "number" ? cell : Number(cell && cell.quantity); if (value > 0) values.push(value); }
    const q95 = values.length >= 20 ? percentile(values, 0.95) : Math.max(...values, 0);
    const q50 = values.length >= 2 ? percentile(values, 0.50) : Math.max(...values, 0);
    const factor = clamp(Number(multiplier) || 1, 0.5, 4);
    return {
      q50,
      q95,
      intensity(quantity) {
        if (!(q95 > 0) || !(Number(quantity) > 0)) return 0;
        return clamp(Math.log1p(Number(quantity)) / Math.log1p(q95) * factor, 0, 1);
      },
    };
  }

  function aggregateTradeBubbles(trades, tickSize, multiplier, minNotional, pixelDurationMs) {
    const tick = Number(tickSize), mult = Math.max(1, Math.round(Number(multiplier) || 1));
    const pixelMs = Math.max(1, Number(pixelDurationMs) || 1);
    if (!(tick > 0)) return [];
    const aggregates = new Map();
    for (const trade of trades || []) {
      const eventTime = Number(trade.eventTime != null ? trade.eventTime : parseTime(trade.event_time));
      const notional = Number(trade.notional);
      if (!Number.isFinite(eventTime) || !(notional >= (Number(minNotional) || 0))) continue;
      const side = String(trade.side || "").toUpperCase();
      const index = Math.floor(Math.round(Number(trade.price) / tick) / mult) * mult;
      const timeBin = Math.floor(eventTime / pixelMs);
      const key = `${side}:${index}:${timeBin}`;
      const current = aggregates.get(key) || {
        side, index, price: index * tick, eventTime, quantity: 0, notional: 0, count: 0,
        firstEventTime: eventTime, lastEventTime: eventTime, newest: trade,
      };
      current.quantity += Number(trade.quantity);
      current.notional += notional;
      current.count += 1;
      current.eventTime = (current.eventTime * (current.count - 1) + eventTime) / current.count;
      current.firstEventTime = Math.min(current.firstEventTime, eventTime);
      current.lastEventTime = Math.max(current.lastEventTime, eventTime);
      const newestTime = Number(current.newest.eventTime != null ? current.newest.eventTime : parseTime(current.newest.event_time));
      if (eventTime >= newestTime) current.newest = trade;
      aggregates.set(key, current);
    }
    const output = [...aggregates.values()];
    const notionals = output.map(item => item.notional);
    const n95 = notionals.length >= 20 ? percentile(notionals, 0.95) : Math.max(...notionals, 0);
    return output.map(item => ({ ...item, radius: n95 > 0 ? 3 + 15 * Math.sqrt(clamp(item.notional / n95, 0, 1)) : 3 }));
  }

  function buildIntervals(frames, start, end, tickSize, multiplier, staleEnd) {
    const intervals = [];
    for (let index = 0; index < frames.length; index += 1) {
      const frame = frames[index];
      const frameTime = Number(frameValue(frame, "eventTime", "event_time"));
      const nextTime = index + 1 < frames.length ? Number(frameValue(frames[index + 1], "eventTime", "event_time")) : Number(staleEnd || end);
      const left = Math.max(start, frameTime);
      const right = Math.min(end, nextTime);
      if (right > left) intervals.push({ start: left, end: right, frame, cells: bucketBookFrame(frame, tickSize, multiplier) });
    }
    return intervals;
  }

  function heatRgb(intensity) {
    const value = clamp(Number(intensity) || 0, 0, 1);
    if (value <= 0) return [0, 0, 0];
    let left = HEAT_STOPS[0], right = HEAT_STOPS[HEAT_STOPS.length - 1];
    for (let index = 1; index < HEAT_STOPS.length; index += 1) if (value <= HEAT_STOPS[index][0]) { left = HEAT_STOPS[index - 1]; right = HEAT_STOPS[index]; break; }
    const ratio = (value - left[0]) / Math.max(1e-9, right[0] - left[0]);
    return left[1].map((channel, index) => Math.round(channel + (right[1][index] - channel) * ratio));
  }

  function heatColor(intensity) {
    const rgb = heatRgb(intensity);
    return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
  }

  function packedRgba(red, green, blue, alpha) {
    const bytes = new Uint8Array([red, green, blue, alpha]);
    return new Uint32Array(bytes.buffer)[0];
  }

  class OrderBookHeatmapCanvas {
    constructor(options) {
      const config = options || {};
      this.canvas = config.canvas;
      this.status = config.status || null;
      this.detail = config.detail || null;
      this.tooltip = config.tooltip || null;
      this.bookStore = config.bookStore || new HeatmapBookStore();
      this.tradeStore = config.tradeStore || new HeatmapTradeStore();
      this.onTradeSelect = config.onTradeSelect || function () {};
      this.getLastPrice = config.getLastPrice || (() => null);
      this.viewMs = 300000;
      this.stepMode = "AUTO";
      this.intensityMultiplier = 1;
      this.minimumNotional = 0;
      this.showBubbles = true;
      this.showBidAsk = true;
      this.showLast = true;
      this.liveLock = true;
      this.timeOffsetMs = 0;
      this.pricePan = 0;
      this.priceZoom = 1;
      this.connected = false;
      this.visible = false;
      this.selection = null;
      this.hover = null;
      this.renderTimes = [];
      this.ingestTimes = [];
      this.lastFrame = null;
      this.sourceTick = null;
      this.lastBubbles = [];
      this.frameGeometry = null;
      this.baseDirty = true;
      this.drawPending = false;
      this.baseCanvas = typeof document !== "undefined" ? document.createElement("canvas") : null;
      this.rasterCanvas = typeof document !== "undefined" ? document.createElement("canvas") : null;
      this.rasterImage = null;
      this.backgroundPixel = packedRgba(8, 17, 31, 255);
      this.heatPixels = Uint32Array.from({ length: 256 }, (_, index) => { const rgb = heatRgb(index / 255); return packedRgba(rgb[0], rgb[1], rgb[2], 255); });
      this.bindEvents();
      if (typeof ResizeObserver !== "undefined" && this.canvas) {
        this.resizeObserver = new ResizeObserver(() => { this.baseDirty = true; this.requestDraw(true); });
        this.resizeObserver.observe(this.canvas);
      }
    }

    setVisible(visible) { this.visible = Boolean(visible); if (this.visible) { this.baseDirty = true; this.requestDraw(true); } }
    setConnected(connected, atMs) {
      this.connected = Boolean(connected);
      if (!this.connected) this.bookStore.markDisconnected(Number(atMs) || Date.now());
      this.baseDirty = true;
      this.requestDraw(true);
    }
    ingestBook(payload, nowMs) {
      const started = typeof performance !== "undefined" ? performance.now() : Date.now();
      const result = this.bookStore.ingest(payload, nowMs);
      if (result.frame) {
        const observedTick = inferBookTick([result.frame], null);
        if (observedTick && this.sourceTick === null) this.sourceTick = observedTick;
        else if (observedTick && this.sourceTick && Math.abs(observedTick - this.sourceTick) > Math.max(1e-10, this.sourceTick * 1e-8)) {
          this.bookStore._appendGap("TICK SIZE CHANGE", result.frame.eventTime, result.frame.eventTime, { previous: this.sourceTick, received: observedTick });
          this.sourceTick = observedTick;
        }
      }
      this.recordTiming(this.ingestTimes, (typeof performance !== "undefined" ? performance.now() : Date.now()) - started, 240);
      this.baseDirty = true;
      this.requestDraw(true);
      return result;
    }
    ingestTrades(trades, nowMs, context) {
      const started = typeof performance !== "undefined" ? performance.now() : Date.now();
      const result = this.tradeStore.ingest(trades, nowMs, context);
      this.recordTiming(this.ingestTimes, (typeof performance !== "undefined" ? performance.now() : Date.now()) - started, 240);
      this.baseDirty = true;
      this.requestDraw(true);
      return result;
    }
    recordTapeContinuity(result, streamId, atMs) { this.tradeStore.recordContinuity(result, streamId, atMs); this.baseDirty = true; this.requestDraw(true); }
    setViewMs(value) { this.viewMs = clamp(Number(value) || 300000, 10000, 900000); this.timeOffsetMs = 0; this.liveLock = true; this.baseDirty = true; this.requestDraw(true); }
    setStep(value) { this.stepMode = value === "AUTO" ? "AUTO" : clamp(Number(value) || 1, 1, 10); this.baseDirty = true; this.requestDraw(true); }
    adjustIntensity(delta) { this.intensityMultiplier = clamp(this.intensityMultiplier + Number(delta), 0.5, 4); this.baseDirty = true; this.requestDraw(true); }
    toggleBubbles() { this.showBubbles = !this.showBubbles; this.baseDirty = true; this.requestDraw(true); return this.showBubbles; }
    returnLive() { this.liveLock = true; this.timeOffsetMs = 0; this.pricePan = 0; this.priceZoom = 1; this.baseDirty = true; this.requestDraw(true); }
    focusTrade(trade) {
      if (!trade) return false;
      const eventTime = Number(trade.eventTime != null ? trade.eventTime : parseTime(trade.event_time));
      const price = Number(trade.price);
      if (!Number.isFinite(eventTime) || !Number.isFinite(price)) return false;
      const match = this.tradeStore.trades.find(item => item.tradeId === String(trade.tradeId != null ? trade.tradeId : trade.trade_id));
      if (!match) return false;
      this.selection = { time: eventTime, price, trade: match };
      this.liveLock = false;
      const latest = this.latestEventTime();
      this.timeOffsetMs = Math.max(0, latest - eventTime - this.viewMs / 2);
      this.baseDirty = true;
      this.requestDraw(true);
      return true;
    }

    latestEventTime() {
      const frame = this.bookStore.frames[this.bookStore.frames.length - 1];
      return frame ? frame.eventTime : Date.now();
    }
    recordTiming(target, value, limit) { target.push(Number(value) || 0); if (target.length > limit) target.splice(0, target.length - limit); }
    requestDraw(full) {
      if (full) this.baseDirty = true;
      if (!this.visible || !this.canvas || this.drawPending) return;
      this.drawPending = true;
      const schedule = typeof requestAnimationFrame === "function" ? requestAnimationFrame : callback => setTimeout(callback, 0);
      schedule(() => { this.drawPending = false; this.render(); });
    }

    resize() {
      const rect = this.canvas.getBoundingClientRect();
      const dpr = clamp(typeof devicePixelRatio === "number" ? devicePixelRatio : 1, 1, 4);
      const width = Math.max(1, Math.round(rect.width * dpr));
      const height = Math.max(1, Math.round(rect.height * dpr));
      if (this.canvas.width !== width || this.canvas.height !== height) {
        this.canvas.width = width;
        this.canvas.height = height;
        this.baseCanvas.width = width;
        this.baseCanvas.height = height;
        this.baseDirty = true;
      }
      return { width: rect.width, height: rect.height, dpr };
    }

    render() {
      if (!this.visible || !this.canvas) return;
      const size = this.resize();
      if (!(size.width > 0 && size.height > 0)) return;
      const started = typeof performance !== "undefined" ? performance.now() : Date.now();
      if (this.baseDirty) {
        const base = this.baseCanvas.getContext("2d", { alpha: false });
        base.setTransform(size.dpr, 0, 0, size.dpr, 0, 0);
        this.buildBase(base, size.width, size.height);
        this.baseDirty = false;
      }
      const context = this.canvas.getContext("2d");
      context.setTransform(1, 0, 0, 1, 0, 0);
      context.clearRect(0, 0, this.canvas.width, this.canvas.height);
      context.drawImage(this.baseCanvas, 0, 0);
      context.setTransform(size.dpr, 0, 0, size.dpr, 0, 0);
      this.drawInteraction(context);
      const elapsed = (typeof performance !== "undefined" ? performance.now() : Date.now()) - started;
      this.recordTiming(this.renderTimes, elapsed, 240);
      this.updateStatus();
    }

    buildBase(context, width, height) {
      const buildStarted = typeof performance !== "undefined" ? performance.now() : Date.now();
      const timing = {};
      context.fillStyle = "#070D18";
      context.fillRect(0, 0, width, height);
      const margin = { left: 8, top: 30, right: 96, bottom: 34 };
      const plot = { x: margin.left, y: margin.top, width: Math.max(1, width - margin.left - margin.right), height: Math.max(1, height - margin.top - margin.bottom) };
      const allFrames = this.bookStore.frames;
      if (!allFrames.length) {
        context.fillStyle = "#C9D3EA";
        context.font = `800 14px ${FONT}`;
        context.textAlign = "center";
        context.fillText("HEATMAP WARMING · SESSION START", width / 2, height / 2);
        this.frameGeometry = { plot, empty: true };
        return;
      }
      const latest = allFrames[allFrames.length - 1];
      const staleBoundary = latest.projectionTime + 2250;
      const now = Date.now();
      if (this.connected && now > staleBoundary && (!this.bookStore.activeGap || this.bookStore.activeGap.reason !== "LOCAL STALE")) {
        this.bookStore.markLocalStale(staleBoundary);
      }
      const liveEnd = this.connected ? Math.max(latest.eventTime, now) : latest.eventTime;
      const end = liveEnd - Math.max(0, this.timeOffsetMs);
      const start = end - this.viewMs;
      const frames = this.bookStore.visibleFrames(start, end);
      const tick = this.sourceTick || inferBookTick(frames.slice(-20), null);
      if (!tick) {
        context.fillStyle = "#FFE35D";
        context.font = `800 14px ${FONT}`;
        context.textAlign = "center";
        context.fillText("WAITING FOR TICK", width / 2, height / 2);
        this.frameGeometry = { plot, empty: true, start, end };
        return;
      }
      const latestLevels = [...frameLevels(latest, "BID"), ...frameLevels(latest, "ASK")];
      let sourceMin = Math.min(...latestLevels.map(level => Number(level.price)));
      let sourceMax = Math.max(...latestLevels.map(level => Number(level.price)));
      const mid = (latest.bestBid + latest.bestAsk) / 2;
      if (!Number.isFinite(sourceMin) || !Number.isFinite(sourceMax)) { sourceMin = mid - tick * 40; sourceMax = mid + tick * 40; }
      const sourceSpan = Math.max(tick * 12, sourceMax - sourceMin + tick * 6);
      const visibleSpan = sourceSpan / clamp(this.priceZoom, 0.25, 8);
      const center = mid + this.pricePan;
      const minPrice = center - visibleSpan / 2;
      const maxPrice = center + visibleSpan / 2;
      const sourceRows = Math.max(1, Math.ceil((maxPrice - minPrice) / tick));
      const targetRows = clamp(Math.floor(plot.height / 14), 40, 90);
      const multiplier = selectDisplayStep(tick, sourceRows, this.stepMode, targetRows) || 1;
      const step = tick * multiplier;
      const columns = buildTimeColumns(frames, start, end, Math.max(1, Math.floor(plot.width)));
      const gaps = this.bookStore.visibleGaps(start, end);
      const latestCarryEnd = this.connected ? Math.min(end, staleBoundary) : latest.eventTime;
      const intervals = buildIntervals(frames, start, end, tick, multiplier, latestCarryEnd);
      const raster = durationWeightedRaster(intervals, columns, gaps, Math.floor(minPrice / tick), Math.ceil(maxPrice / tick), multiplier);
      const heatValues = [];
      for (const plane of [raster.bid, raster.ask]) for (const value of plane) if (value > 0) heatValues.push(value);
      const scale = computeHeatScale(heatValues, this.intensityMultiplier);
      timing.aggregate = (typeof performance !== "undefined" ? performance.now() : Date.now()) - buildStarted;
      const xOf = time => plot.x + (Number(time) - start) / (end - start) * plot.width;
      const yOf = price => plot.y + (maxPrice - Number(price)) / (maxPrice - minPrice) * plot.height;
      const rowHeight = Math.max(1, step / (maxPrice - minPrice) * plot.height);

      context.save();
      context.beginPath();
      context.rect(plot.x, plot.y, plot.width, plot.height);
      context.clip();
      const rasterWidth = Math.max(1, Math.ceil(plot.width));
      const rasterHeight = Math.max(1, Math.ceil(plot.height));
      if (this.rasterCanvas.width !== rasterWidth || this.rasterCanvas.height !== rasterHeight) {
        this.rasterCanvas.width = rasterWidth;
        this.rasterCanvas.height = rasterHeight;
        this.rasterImage = null;
      }
      const rasterContext = this.rasterCanvas.getContext("2d", { alpha: false });
      const image = this.rasterImage || (this.rasterImage = rasterContext.createImageData(rasterWidth, rasterHeight));
      const pixels = image.data;
      const pixelWords = new Uint32Array(pixels.buffer);
      pixelWords.fill(this.backgroundPixel);
      for (let columnIndex = 0; columnIndex < raster.width; columnIndex += 1) {
        const base = columnIndex * raster.rows;
        for (let rasterRow = 0; rasterRow < raster.rows; rasterRow += 1) {
          const price = (raster.firstIndex + rasterRow * multiplier) * tick;
          const top = clamp(Math.floor(yOf(price + step) - plot.y), 0, rasterHeight - 1);
          const bottom = clamp(Math.ceil(top + rowHeight + 1), top + 1, rasterHeight);
          for (const [plane, upperHalf] of [[raster.bid, false], [raster.ask, true]]) {
            const quantity = plane[base + rasterRow];
            if (!(quantity > 0)) continue;
            const color = this.heatPixels[Math.round(scale.intensity(quantity) * 255)];
            const middle = Math.max(top + 1, Math.floor((top + bottom) / 2));
            const sideTop = upperHalf ? top : middle;
            const sideBottom = upperHalf ? middle : bottom;
            for (let row = sideTop; row < sideBottom; row += 1) {
              const offset = row * rasterWidth + Math.min(columnIndex, rasterWidth - 1);
              pixelWords[offset] = color;
            }
          }
        }
      }
      rasterContext.putImageData(image, 0, 0);
      context.drawImage(this.rasterCanvas, plot.x, plot.y, plot.width, plot.height);
      timing.raster = (typeof performance !== "undefined" ? performance.now() : Date.now()) - buildStarted - timing.aggregate;
      this.drawBookGaps(context, gaps, plot, start, end);
      this.drawTapeMarkers(context, plot, start, end);

      const visibleTrades = this.tradeStore.visibleTrades(start, end);
      const bubbles = this.showBubbles ? aggregateTradeBubbles(visibleTrades, tick, multiplier, this.minimumNotional, (end - start) / plot.width) : [];
      this.lastBubbles = [];
      for (const bubble of bubbles) {
        if (bubble.price < minPrice || bubble.price > maxPrice) continue;
        let x = xOf(bubble.eventTime);
        if (bubble.side === "BUY") x += 2; else x -= 2;
        const y = yOf(bubble.price + step / 2);
        context.beginPath();
        context.arc(x, y, bubble.radius, 0, Math.PI * 2);
        context.fillStyle = bubble.side === "BUY" ? "rgba(57,248,157,.72)" : "rgba(255,54,95,.72)";
        context.fill();
        context.lineWidth = 1.5;
        context.strokeStyle = "#05070D";
        context.stroke();
        this.lastBubbles.push({ ...bubble, x, y });
      }
      if (this.showBidAsk) {
        this.drawPriceLine(context, plot, yOf, latest.bestBid, "#39F89D", "BID");
        this.drawPriceLine(context, plot, yOf, latest.bestAsk, "#FF365F", "ASK");
      }
      const lastPrice = Number(this.getLastPrice());
      if (this.showLast && Number.isFinite(lastPrice)) this.drawPriceLine(context, plot, yOf, lastPrice, "#FFFFFF", "LAST", [5, 3]);
      context.restore();

      this.drawAxes(context, plot, start, end, minPrice, maxPrice, step);
      this.drawLegend(context, plot, scale);
      timing.overlay = (typeof performance !== "undefined" ? performance.now() : Date.now()) - buildStarted - timing.aggregate - timing.raster;
      timing.total = (typeof performance !== "undefined" ? performance.now() : Date.now()) - buildStarted;
      this.lastBuildTiming = timing;
      this.lastFrame = latest;
      this.frameGeometry = { plot, start, end, minPrice, maxPrice, tick, multiplier, step, scale, raster, frames, gaps, xOf, yOf, rowHeight, empty: false };
    }

    drawPriceLine(context, plot, yOf, price, color, label, dash) {
      if (!Number.isFinite(Number(price))) return;
      const y = yOf(Number(price));
      if (y < plot.y || y > plot.y + plot.height) return;
      context.save();
      context.setLineDash(dash || []);
      context.strokeStyle = color;
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(plot.x, y + 0.5);
      context.lineTo(plot.x + plot.width, y + 0.5);
      context.stroke();
      context.setLineDash([]);
      context.fillStyle = color;
      context.font = `800 11px ${FONT}`;
      context.textAlign = "left";
      context.fillText(label, plot.x + 3, y - 3);
      context.restore();
    }

    drawBookGaps(context, gaps, plot, start, end) {
      for (const gap of gaps || []) {
        const left = plot.x + (Math.max(start, gap.start) - start) / (end - start) * plot.width;
        const rightTime = gap.end == null ? end : Math.min(end, gap.end);
        const right = plot.x + (rightTime - start) / (end - start) * plot.width;
        const width = Math.max(2, right - left);
        context.fillStyle = "rgba(98,108,128,.42)";
        context.fillRect(left, plot.y, width, plot.height);
        context.strokeStyle = "rgba(220,225,236,.5)";
        context.lineWidth = 1;
        for (let offset = -plot.height; offset < width; offset += 8) {
          context.beginPath();
          context.moveTo(left + offset, plot.y + plot.height);
          context.lineTo(left + offset + plot.height, plot.y);
          context.stroke();
        }
        if (width > 72) {
          context.fillStyle = "#F1F5FF";
          context.font = `900 12px ${FONT}`;
          context.textAlign = "left";
          context.fillText(gap.reason, left + 4, plot.y + 16);
        }
      }
    }

    drawTapeMarkers(context, plot, start, end) {
      context.save();
      context.setLineDash([5, 3]);
      context.strokeStyle = "#FF365F";
      context.fillStyle = "#FF8AA1";
      context.font = `900 11px ${FONT}`;
      for (const marker of this.tradeStore.markers) {
        if (marker.time < start || marker.time > end) continue;
        const x = plot.x + (marker.time - start) / (end - start) * plot.width;
        context.beginPath();
        context.moveTo(x, plot.y);
        context.lineTo(x, plot.y + 9);
        context.stroke();
        context.fillText(marker.reason, Math.min(x + 3, plot.x + plot.width - 145), plot.y + 12);
      }
      context.restore();
    }

    drawAxes(context, plot, start, end, minPrice, maxPrice, step) {
      context.strokeStyle = "#273654";
      context.fillStyle = "#F1F5FF";
      context.font = `800 14px ${FONT}`;
      context.lineWidth = 1;
      context.textAlign = "left";
      const digits = priceDigits(step);
      const priceTicks = Math.max(4, Math.min(9, Math.floor(plot.height / 48)));
      for (let index = 0; index <= priceTicks; index += 1) {
        const ratio = index / priceTicks;
        const y = plot.y + ratio * plot.height;
        const price = maxPrice - ratio * (maxPrice - minPrice);
        context.beginPath(); context.moveTo(plot.x, y + 0.5); context.lineTo(plot.x + plot.width, y + 0.5); context.stroke();
        context.fillText(price.toFixed(digits), plot.x + plot.width + 7, y + 5);
      }
      const timeTicks = Math.max(3, Math.min(7, Math.floor(plot.width / 125)));
      context.textAlign = "center";
      for (let index = 0; index <= timeTicks; index += 1) {
        const ratio = index / timeTicks;
        const x = plot.x + ratio * plot.width;
        const timestamp = start + ratio * (end - start);
        context.beginPath(); context.moveTo(x + 0.5, plot.y); context.lineTo(x + 0.5, plot.y + plot.height); context.stroke();
        context.fillText(jstClock(timestamp, "second"), x, plot.y + plot.height + 22);
      }
    }

    drawLegend(context, plot, scale) {
      const width = 190, x = plot.x + 6, y = 7;
      const gradient = context.createLinearGradient(x, 0, x + width, 0);
      for (const [offset, color] of [[0, "#04123A"], [.35, "#0853AB"], [.62, "#00D5EB"], [.84, "#FFDD36"], [1, "#FFFFD2"]]) gradient.addColorStop(offset, color);
      context.fillStyle = gradient;
      context.fillRect(x, y, width, 10);
      context.strokeStyle = "#526482";
      context.strokeRect(x, y, width, 10);
      context.fillStyle = "#F1F5FF";
      context.font = `800 12px ${FONT}`;
      context.textAlign = "left";
      context.fillText("0", x, y + 22);
      context.textAlign = "center";
      context.fillText(`Q50 ${scale.q50.toFixed(3)}`, x + width / 2, y + 22);
      context.textAlign = "right";
      context.fillText(`Q95+ ${scale.q95.toFixed(3)}`, x + width, y + 22);
    }

    drawInteraction(context) {
      const geometry = this.frameGeometry;
      const point = this.selection || this.hover;
      if (!geometry || geometry.empty || !point) return;
      const x = geometry.xOf(point.time);
      const y = geometry.yOf(point.price);
      if (x < geometry.plot.x || x > geometry.plot.x + geometry.plot.width || y < geometry.plot.y || y > geometry.plot.y + geometry.plot.height) return;
      context.save();
      context.setLineDash([4, 3]);
      context.strokeStyle = this.selection ? "#FFE35D" : "rgba(241,245,255,.72)";
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(x + 0.5, geometry.plot.y);
      context.lineTo(x + 0.5, geometry.plot.y + geometry.plot.height);
      context.moveTo(geometry.plot.x, y + 0.5);
      context.lineTo(geometry.plot.x + geometry.plot.width, y + 0.5);
      context.stroke();
      context.restore();
    }

    updateStatus() {
      if (!this.status) return;
      const frame = this.lastFrame;
      const geometry = this.frameGeometry;
      if (!frame || !geometry || geometry.empty) {
        this.status.textContent = this.connected ? "HEATMAP WARMING · SESSION START · SESSION ONLY" : "HEATMAP DISCONNECTED · SESSION ONLY";
        this.status.classList.toggle("warning", !this.connected);
        return;
      }
      const activeGap = this.bookStore.activeGap;
      const view = this.viewMs >= 900000 ? "15M" : this.viewMs >= 300000 ? "5M" : "1M";
      const step = this.stepMode === "AUTO" ? `AUTO→${geometry.multiplier}` : String(geometry.multiplier);
      const bookState = activeGap ? activeGap.reason : "BOOK SYNCED";
      const renderP95Value = p95(this.renderTimes);
      const renderP95 = renderP95Value.toFixed(2);
      const frameBudgetPassed = renderP95Value <= FRAME_BUDGET_MS;
      const frameBudgetLabel = frameBudgetPassed ? "[PASS]" : "[OVER]";
      this.status.textContent = `${bookState} · DEPTH ${frame.bidPrices.length}×${frame.askPrices.length} · SESSION ${jstClock(this.bookStore.sessionStart, "second")} · SESSION ONLY · ${view} · STEP ${step} · Q95 ${geometry.scale.q95.toFixed(3)} · BOOK ${this.bookStore.frames.length}/${this.bookStore.maxFrames} · TAPE ${this.tradeStore.trades.length}/${this.tradeStore.capacity} · RENDER P95 ${renderP95}ms ${frameBudgetLabel}`;
      this.status.style.color = frameBudgetPassed ? "#00cc00" : "#ff4444";
      this.status.classList.toggle("warning", Boolean(activeGap));
    }

    pointFromEvent(event) {
      const geometry = this.frameGeometry;
      if (!geometry || geometry.empty) return null;
      const rect = this.canvas.getBoundingClientRect();
      const x = event.clientX - rect.left, y = event.clientY - rect.top;
      const plot = geometry.plot;
      if (x < plot.x || x > plot.x + plot.width || y < plot.y || y > plot.y + plot.height) return null;
      const time = geometry.start + (x - plot.x) / plot.width * (geometry.end - geometry.start);
      const price = geometry.maxPrice - (y - plot.y) / plot.height * (geometry.maxPrice - geometry.minPrice);
      return { x, y, time, price };
    }

    bubbleAt(point) {
      let best = null, distance = Infinity;
      for (const bubble of this.lastBubbles) {
        const current = Math.hypot(point.x - bubble.x, point.y - bubble.y);
        if (current <= bubble.radius + 3 && current < distance) { best = bubble; distance = current; }
      }
      return best;
    }

    describePoint(point) {
      const geometry = this.frameGeometry;
      if (!geometry || !point) return null;
      const frames = geometry.frames;
      let frame = null;
      for (const candidate of frames) {
        const timestamp = Number(frameValue(candidate, "eventTime", "event_time"));
        if (timestamp <= point.time) frame = candidate; else break;
      }
      if (!frame) return null;
      const index = Math.floor(Math.round(point.price / geometry.tick) / geometry.multiplier) * geometry.multiplier;
      const cells = bucketBookFrame(frame, geometry.tick, geometry.multiplier);
      const cell = cells.find(item => item.index === index && (point.price <= Number(frameValue(frame, "bestBid", "best_bid")) ? item.side === "BID" : item.side === "ASK"));
      const bubble = this.bubbleAt(point);
      const streamId = String(frameValue(frame, "streamId", "book_stream_id") || "");
      const bestBid = Number(frameValue(frame, "bestBid", "best_bid"));
      const bestAsk = Number(frameValue(frame, "bestAsk", "best_ask"));
      const spread = Number(frameValue(frame, "spread", "spread"));
      const frameTime = Number(frameValue(frame, "eventTime", "event_time"));
      const sequence = Number(frameValue(frame, "sequence", "book_sequence"));
      const updateId = Number(frameValue(frame, "lastUpdateId", "last_update_id"));
      const age = Number(frameValue(frame, "ageMs", "age_ms"));
      const digits = priceDigits(geometry.step);
      const lines = [
        `JST ${jstClock(point.time, "millisecond")} · UTC ${new Date(point.time).toISOString()}`,
        `PRICE ${(index * geometry.tick).toFixed(digits)}–${((index + geometry.multiplier) * geometry.tick).toFixed(digits)} · ${cell ? cell.side : "NO LEVEL"}`,
        `RESTING QTY ${cell ? cell.quantity.toFixed(6) : "0"} · SOURCE LEVELS ${cell ? cell.level_count : 0}`,
        `BEST BID ${bestBid} · ASK ${bestAsk} · SPREAD ${spread}`,
        `BOOK ${streamId.slice(0, 8)} · SEQ ${sequence} · UPDATE ${updateId}`,
        `BOOK AGE ${Number.isFinite(age) ? Math.round(age) + "ms" : "—"} · SYNCED · FRAME ${jstClock(frameTime, "millisecond")}`,
      ];
      if (bubble) lines.push(`${bubble.side} · QTY ${bubble.quantity.toFixed(6)} · NOTIONAL ${bubble.notional.toFixed(2)} · TRADES ${bubble.count} · TAPE SEQ ${bubble.newest.sequence}`);
      return { lines, frame, cell, bubble, index };
    }

    showPoint(point, event) {
      const description = this.describePoint(point);
      if (!description) { this.hideTooltip(); return; }
      const text = description.lines.join("\n");
      if (this.tooltip) {
        this.tooltip.hidden = false;
        this.tooltip.textContent = text;
        const stage = this.canvas.getBoundingClientRect();
        const left = clamp(event.clientX - stage.left + 12, 4, Math.max(4, stage.width - 340));
        const top = clamp(event.clientY - stage.top + 12, 4, Math.max(4, stage.height - 175));
        this.tooltip.style.left = `${left}px`;
        this.tooltip.style.top = `${top}px`;
      }
      if (!this.selection && this.detail) this.detail.textContent = text.replace(/\n/g, " · ");
      return description;
    }
    hideTooltip() { if (this.tooltip) this.tooltip.hidden = true; }

    bindEvents() {
      if (!this.canvas || typeof this.canvas.addEventListener !== "function") return;
      this.canvas.addEventListener("mousemove", event => {
        if (this.drag) {
          const dx = event.clientX - this.drag.x, dy = event.clientY - this.drag.y;
          if (Math.abs(dx) >= Math.abs(dy)) {
            this.liveLock = false;
            this.timeOffsetMs = Math.max(0, this.drag.timeOffset + dx / Math.max(1, this.drag.plotWidth) * this.viewMs);
          } else {
            this.liveLock = false;
            this.pricePan = this.drag.pricePan + dy / Math.max(1, this.drag.plotHeight) * this.drag.priceSpan;
          }
          this.baseDirty = true;
          this.requestDraw(true);
          return;
        }
        const point = this.pointFromEvent(event);
        this.hover = point;
        if (point) this.showPoint(point, event); else this.hideTooltip();
        this.requestDraw(false);
      });
      this.canvas.addEventListener("mouseleave", () => { if (!this.drag) { this.hover = null; this.hideTooltip(); this.requestDraw(false); } });
      this.canvas.addEventListener("mousedown", event => {
        if (event.button !== 0 || !this.frameGeometry || this.frameGeometry.empty) return;
        this.drag = { x: event.clientX, y: event.clientY, timeOffset: this.timeOffsetMs, pricePan: this.pricePan, plotWidth: this.frameGeometry.plot.width, plotHeight: this.frameGeometry.plot.height, priceSpan: this.frameGeometry.maxPrice - this.frameGeometry.minPrice };
        this.canvas.setPointerCapture && this.canvas.setPointerCapture(event.pointerId || 1);
      });
      const stopDrag = () => { this.drag = null; };
      this.canvas.addEventListener("mouseup", stopDrag);
      this.canvas.addEventListener("pointercancel", stopDrag);
      this.canvas.addEventListener("wheel", event => {
        const point = this.pointFromEvent(event);
        if (!point || !this.frameGeometry) return;
        event.preventDefault();
        if (event.shiftKey) {
          const oldSpan = this.frameGeometry.maxPrice - this.frameGeometry.minPrice;
          const factor = event.deltaY < 0 ? 1.18 : 1 / 1.18;
          this.priceZoom = clamp(this.priceZoom * factor, 0.25, 8);
          const ratio = (point.y - this.frameGeometry.plot.y) / this.frameGeometry.plot.height;
          const newSpan = oldSpan / factor;
          this.pricePan += (0.5 - ratio) * (oldSpan - newSpan);
        } else {
          const oldView = this.viewMs;
          const newView = clamp(oldView * (event.deltaY < 0 ? 0.82 : 1.22), 10000, 900000);
          const ratio = (point.x - this.frameGeometry.plot.x) / this.frameGeometry.plot.width;
          const desiredEnd = point.time + newView * (1 - ratio);
          const liveEnd = this.connected ? Math.max(this.latestEventTime(), Date.now()) : this.latestEventTime();
          this.viewMs = newView;
          this.timeOffsetMs = Math.max(0, liveEnd - desiredEnd);
          this.liveLock = this.timeOffsetMs < 1;
        }
        this.baseDirty = true;
        this.requestDraw(true);
      }, { passive: false });
      this.canvas.addEventListener("dblclick", () => this.returnLive());
      this.canvas.addEventListener("click", event => {
        const point = this.pointFromEvent(event);
        if (!point) return;
        const description = this.describePoint(point);
        this.selection = { time: point.time, price: point.price, trade: description && description.bubble ? description.bubble.newest : null };
        if (this.detail && description) this.detail.textContent = description.lines.join(" · ");
        if (description && description.bubble) this.onTradeSelect(description.bubble.newest);
        this.requestDraw(false);
      });
      this.canvas.addEventListener("keydown", event => this.onKey(event));
    }

    onKey(event) {
      if (!this.frameGeometry || this.frameGeometry.empty) return;
      const geometry = this.frameGeometry;
      const current = this.selection || { time: geometry.end, price: (geometry.minPrice + geometry.maxPrice) / 2 };
      let handled = true;
      if (event.key === "ArrowLeft") current.time -= (geometry.end - geometry.start) / geometry.plot.width;
      else if (event.key === "ArrowRight") current.time += (geometry.end - geometry.start) / geometry.plot.width;
      else if (event.key === "ArrowUp") current.price += geometry.step;
      else if (event.key === "ArrowDown") current.price -= geometry.step;
      else if (event.key === "PageUp") current.price += geometry.step * 10;
      else if (event.key === "PageDown") current.price -= geometry.step * 10;
      else if (event.key === "Home") current.time = geometry.start;
      else if (event.key === "End") { this.returnLive(); return; }
      else if (event.key === "+" || event.key === "=") this.viewMs = clamp(this.viewMs * 0.82, 10000, 900000);
      else if (event.key === "-") this.viewMs = clamp(this.viewMs * 1.22, 10000, 900000);
      else if (event.key === "Escape") { this.selection = null; this.hover = null; this.hideTooltip(); if (this.detail) this.detail.textContent = "HOVER A HEAT CELL OR BUBBLE · CLICK TO PIN · ESC CLEAR"; }
      else handled = false;
      if (!handled) return;
      event.preventDefault();
      this.selection = event.key === "Escape" ? null : { time: current.time, price: current.price, trade: current.trade || null };
      this.baseDirty = event.key === "+" || event.key === "=" || event.key === "-";
      this.requestDraw(this.baseDirty);
    }

    metrics() {
      return {
        bookFrames: this.bookStore.frames.length,
        trades: this.tradeStore.trades.length,
        gaps: this.bookStore.gaps.length,
        estimatedBookBytes: this.bookStore.estimatedBytes(),
        ingestP95: p95(this.ingestTimes),
        renderP95: p95(this.renderTimes),
        renderMax: this.renderTimes.length ? Math.max(...this.renderTimes) : 0,
        build: this.lastBuildTiming || null,
      };
    }
    destroy() { if (this.resizeObserver) this.resizeObserver.disconnect(); this.visible = false; }
  }

  return {
    validateBookPayload,
    HeatmapBookStore,
    HeatmapTradeStore,
    inferBookTick,
    selectDisplayStep,
    bucketBookFrame,
    buildTimeColumns,
    durationWeightedCells,
    durationWeightedRaster,
    computeHeatScale,
    aggregateTradeBubbles,
    buildIntervals,
    heatColor,
    OrderBookHeatmapCanvas,
    jstClock,
    priceDigits,
    p95,
  };
});
