(function (global) {
  "use strict";

  const RECORD_KINDS = new Set([
    "EVENT_CREATED", "ZONE_CREATED", "ZONE_INTERACTION", "ZONE_EVENT_LINK",
    "RESULT_SNAPSHOT", "CANDLE_OBSERVATION", "USER_ASSESSMENT",
  ]);
  const STATUS_VALUES = new Set([
    "DISABLED", "STARTING", "MANUAL_READY", "AUTOMATIC_READY",
    "INSUFFICIENT_HISTORY", "CALIBRATION_UNAVAILABLE",
    "CALIBRATION_ACTIVATION_FAILED", "DEGRADED_STORAGE",
    "DEGRADED_POINTER_CACHE", "DEGRADED_SOURCE_GAP", "ERROR",
  ]);
  const ASSESSMENTS = [
    "UNASSESSED", "EFFORT_REWARDED", "EFFORT_NOT_REWARDED",
    "OPPOSING_ABSORPTION_OBSERVED", "REPEATED_DEFENSE_OBSERVED",
    "BREAK_ACCEPTED_OBSERVED", "BATTLE_UNRESOLVED",
    "CONTROL_UP_OBSERVED", "CONTROL_DOWN_OBSERVED",
  ];
  const ID_FIELDS = {
    EVENT_CREATED: "event_id", ZONE_CREATED: "zone_id",
    ZONE_INTERACTION: "interaction_id", ZONE_EVENT_LINK: "link_id",
    RESULT_SNAPSHOT: "snapshot_id", CANDLE_OBSERVATION: "candle_observation_id",
    USER_ASSESSMENT: "assessment_id",
  };
  const HEX64 = /^[0-9a-f]{64}$/;
  const DECIMAL = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/;
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const AWARE_TIME = /(Z|[+-][0-9]{2}:[0-9]{2})$/;
  const INTEGER_FIELDS = new Set([
    "sequence", "first_sequence", "last_sequence", "accepted_count", "dropped_count",
    "schema_version", "zone_schema_version", "source_trade_id", "first_trade_id",
    "last_trade_id", "trade_id", "snapshot_trade_id", "effective_from_trade_id",
    "fill_ordinal", "ordinal", "ordinal_for_zone", "horizon_seconds",
  ]);
  const NON_DECIMAL_FIELDS = new Set([
    "marker_price_mode", "price_level_count", "price_path_index_size", "quantity_unit",
  ]);
  const FIELD_KIND_CACHE = new Map();
  const HISTORY_PREFIXES = {
    event_id: "bt2_", zone_id: "btz2_", interaction_id: "bti2_", link_id: "btl2_",
    snapshot_id: "btsnap2_", candle_observation_id: "btcobs2_", assessment_id: "btassess2_",
  };

  function ownKeys(value, expected) {
    const actual = Object.keys(value).sort();
    const wanted = expected.slice().sort();
    return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
  }
  function isObject(value) { return value !== null && typeof value === "object" && !Array.isArray(value); }
  function isIntegerField(name) {
    const key = String(name).toLowerCase();
    return INTEGER_FIELDS.has(key) || key.endsWith("_count") || key.endsWith("_ms") || key.endsWith("_milliseconds");
  }
  function isDecimalField(name) {
    const key = String(name).toLowerCase();
    return !NON_DECIMAL_FIELDS.has(key) && [
      "price", "quantity", "notional", "vwap", "_bps", "_ticks", "threshold",
    ].some(token => key.includes(token));
  }
  function isHex64(value) {
    if (typeof value !== "string" || value.length !== 64) return false;
    for (let index = 0; index < 64; index += 1) {
      const code = value.charCodeAt(index);
      if (!((code >= 48 && code <= 57) || (code >= 97 && code <= 102))) return false;
    }
    return true;
  }
  function validateWireScalar(value, fieldName) {
    if (value === null) return;
    let kind = FIELD_KIND_CACHE.get(fieldName);
    if (kind === undefined) { kind = isDecimalField(fieldName) ? 1 : isIntegerField(fieldName) ? 2 : 0; FIELD_KIND_CACHE.set(fieldName, kind); }
    if (kind === 1 && (typeof value !== "string" || !DECIMAL.test(value))) throw new Error(`${fieldName} must be a Decimal JSON string`);
    if (kind === 2 && (!Number.isInteger(value) || typeof value === "boolean")) throw new Error(`${fieldName} must be a JSON integer`);
    if (typeof value === "number" && !Number.isFinite(value)) throw new Error(`${fieldName} must be finite`);
  }
  function validateWireTypes(value, fieldName) {
    if (Array.isArray(value)) { value.forEach(item => validateWireTypes(item, fieldName)); return; }
    if (isObject(value)) {
      for (const [key, item] of Object.entries(value)) {
        if (Array.isArray(item) || isObject(item)) validateWireTypes(item, key);
        else validateWireScalar(item, key);
      }
      return;
    }
    validateWireScalar(value, fieldName);
  }
  function wireSchema(row) {
    return Object.keys(row).map(key => [key, isDecimalField(key) ? 1 : isIntegerField(key) ? 2 : 0]);
  }
  function validateWithWireSchema(row, schema) {
    const keys = Object.keys(row);
    if (keys.length !== schema.length || schema.some(([key]) => !Object.prototype.hasOwnProperty.call(row, key))) {
      validateWireTypes(row, "");
      return wireSchema(row);
    }
    for (const [key, kind] of schema) {
      const value = row[key];
      if (Array.isArray(value) || isObject(value)) { validateWireTypes(value, key); continue; }
      if (value === null) continue;
      if (kind === 1 && (typeof value !== "string" || !DECIMAL.test(value))) throw new Error(`${key} must be a Decimal JSON string`);
      if (kind === 2 && (!Number.isInteger(value) || typeof value === "boolean")) throw new Error(`${key} must be a JSON integer`);
      if (typeof value === "number" && !Number.isFinite(value)) throw new Error(`${key} must be finite`);
    }
    return schema;
  }
  function parseTime(value, fieldName) {
    if (typeof value !== "string" || !AWARE_TIME.test(value)) {
      throw new Error(`${fieldName} must be timezone-aware ISO8601`);
    }
    const parsed = Date.parse(value);
    if (!Number.isFinite(parsed)) throw new Error(`${fieldName} is invalid`);
    return parsed;
  }
  function num(value) {
    if (value === null || value === undefined || value === "") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  function dash(value) { return value === null || value === undefined || value === "" ? "—" : String(value); }
  function shortId(value) { const text = dash(value); return text === "—" ? text : `${text.slice(0, 12)}…${text.slice(-6)}`; }
  function escapeHtml(value) {
    return dash(value).replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  }
  function sourceKey(row, timeField, idField) { return [parseTime(row[timeField], timeField), String(row[idField])]; }
  function compareKey(left, right) { return left[0] - right[0] || left[1].localeCompare(right[1]); }
  function p95(values) {
    if (!values.length) return null;
    const sorted = values.slice().sort((a, b) => a - b);
    return sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.95) - 1)];
  }

  function projectContextBars(rawBars, defaultTimeframe) {
    const nullableNumber = value => value === null || value === undefined || value === ""
      ? null
      : (Number.isFinite(Number(value)) ? Number(value) : null);
    return (rawBars || []).map(raw => {
      const candidate = raw.time ?? raw.t;
      const time = candidate !== null && candidate !== undefined && candidate !== "" && Number.isFinite(Number(candidate))
        ? Number(candidate)
        : Date.parse(raw.bar_time);
      return {
        time,
        bar_time: Number.isFinite(time) ? new Date(time).toISOString() : null,
        timeframe: String(raw.timeframe || defaultTimeframe || "1m"),
        cvd: nullableNumber(raw.cvd),
        delta: nullableNumber(raw.delta),
        volume: nullableNumber(raw.volume),
      };
    }).filter(bar => Number.isFinite(bar.time));
  }

  function selectContextForZone({ zone, bars, flowHistory, windowSec, symbol, timeframeSeconds }) {
    const empty = { sourceId: null, sourceTime: null, flowSourceId: null, flowSourceTime: null, cvd: null, delta: null, volume: null, flowResponse: null, absorption: null, imbalance: null };
    const selectedTime = Date.parse(zone && zone.zone_source_start);
    if (!Number.isFinite(selectedTime)) return empty;
    const duration = typeof timeframeSeconds === "function" ? timeframeSeconds : (() => 60);
    const bar = (bars || []).find(item => selectedTime >= item.time && selectedTime < item.time + duration(item.timeframe) * 1000) || null;
    if (!bar) return empty;
    const resolvedSymbol = String((zone && zone.symbol) || symbol || "—"), sourceTime = bar.bar_time;
    const sourceId = `${resolvedSymbol}|${bar.timeframe}|${sourceTime}`;
    let flowFact = null;
    for (let index = (flowHistory || []).length - 1; index >= 0; index -= 1) {
      const item = flowHistory[index];
      if (item.time > selectedTime) continue;
      if (item.time < bar.time) break;
      const row = item.rows.find(candidate => candidate.window_sec === windowSec);
      if (row) { flowFact = { item, row }; break; }
    }
    const flowSourceTime = flowFact ? new Date(flowFact.item.time).toISOString() : null;
    return {
      sourceId, sourceTime,
      flowSourceId: flowFact ? `${resolvedSymbol}|${flowFact.row.window_sec}s|${flowSourceTime}` : null,
      flowSourceTime,
      cvd: bar.cvd, delta: bar.delta, volume: bar.volume,
      flowResponse: flowFact ? flowFact.row.state : null,
      // Latest-only module state is deliberately not projected into history.
      absorption: null, imbalance: null,
    };
  }

  class BigTradeRecordValidator {
    static validateUpdate(message) {
      if (!isObject(message) || !ownKeys(message, ["v", "type", "time", "symbol", "payload"])) throw new Error("invalid BIG_TRADES_UPDATE envelope");
      if (message.v !== 1 || message.type !== "BIG_TRADES_UPDATE" || typeof message.symbol !== "string" || !message.symbol) throw new Error("invalid BIG_TRADES_UPDATE identity");
      parseTime(message.time, "time");
      const payload = message.payload;
      if (!isObject(payload) || !ownKeys(payload, ["batch_time", "stream_id", "first_sequence", "last_sequence", "accepted_count", "dropped_count", "records"])) throw new Error("invalid BIG_TRADES_UPDATE payload");
      parseTime(payload.batch_time, "batch_time");
      if (typeof payload.stream_id !== "string" || !UUID.test(payload.stream_id)) throw new Error("stream_id must be UUID");
      if (!Number.isInteger(payload.first_sequence) || payload.first_sequence < 1 || !Number.isInteger(payload.last_sequence) || payload.last_sequence < payload.first_sequence || !Number.isInteger(payload.dropped_count) || payload.dropped_count < 0) throw new Error("invalid sequence/count values");
      if (!Array.isArray(payload.records) || !payload.records.length || payload.accepted_count !== payload.records.length) throw new Error("invalid records count");
      payload.records.forEach((record, index) => {
        if (!isObject(record) || !ownKeys(record, ["kind", "sequence", "source_event_time", "source_trade_id", "record_id", "content_hash", "data"])) throw new Error("invalid record fields");
        if (!RECORD_KINDS.has(record.kind)) throw new Error("unknown record kind");
        if (record.sequence !== payload.first_sequence + index) throw new Error("record sequence gap inside batch");
        parseTime(record.source_event_time, "source_event_time");
        if (record.source_trade_id !== null && (!Number.isInteger(record.source_trade_id) || typeof record.source_trade_id === "boolean" || record.source_trade_id < 0)) throw new Error("invalid source_trade_id");
        if (typeof record.record_id !== "string" || !record.record_id || !isHex64(record.content_hash)) throw new Error("invalid record identity");
        if (!isObject(record.data) || record.data[ID_FIELDS[record.kind]] !== record.record_id || record.data.content_hash !== record.content_hash) throw new Error("record data identity mismatch");
      });
      if (payload.last_sequence !== payload.first_sequence + payload.records.length - 1) throw new Error("invalid last_sequence");
      validateWireTypes(message, "");
      return message;
    }
    static validateStatus(message) {
      if (!isObject(message) || !ownKeys(message, ["v", "type", "time", "symbol", "payload"]) || message.type !== "BIG_TRADES_STATUS" || message.v !== 1 || typeof message.symbol !== "string" || !message.symbol || !isObject(message.payload) || !ownKeys(message.payload, ["status", "reason", "counters"]) || !isObject(message.payload.counters) || (message.payload.reason !== null && typeof message.payload.reason !== "string")) throw new Error("invalid BIG_TRADES_STATUS");
      if (!STATUS_VALUES.has(message.payload.status)) throw new Error("unknown BIG_TRADES_STATUS");
      parseTime(message.time, "time");
      validateWireTypes(message, "");
      return message;
    }
    static validateHistoryRow(row, idField, timeField) {
      const prefix = HISTORY_PREFIXES[idField], identifier = isObject(row) ? row[idField] : null;
      if (!prefix || typeof identifier !== "string" || !identifier.startsWith(prefix) || !isHex64(identifier.slice(prefix.length)) || !isHex64(row.content_hash)) throw new Error(`invalid ${idField} history row`);
      if (timeField) parseTime(row[timeField], timeField);
      validateWireTypes(row, "");
      return row;
    }
    static validateHistoryRows(rows, idField, timeField) {
      const prefix = HISTORY_PREFIXES[idField];
      if (!prefix) throw new Error(`invalid ${idField} history schema`);
      let schema = null;
      for (const row of rows || []) {
        const identifier = isObject(row) ? row[idField] : null;
        if (typeof identifier !== "string" || !identifier.startsWith(prefix) || !isHex64(identifier.slice(prefix.length)) || !isHex64(row.content_hash)) throw new Error(`invalid ${idField} history row`);
        if (timeField) parseTime(row[timeField], timeField);
        schema = validateWithWireSchema(row, schema || wireSchema(row));
      }
      return rows;
    }
  }

  class BigTradeEventStore {
    constructor(capacity = 5000) { this.capacity = capacity; this.events = new Map(); this.collisions = 0; this.revision = 0; }
    ingest(row) {
      BigTradeRecordValidator.validateHistoryRow(row, "event_id", "last_time");
      const prior = this.events.get(row.event_id);
      if (prior && prior.content_hash !== row.content_hash) { this.collisions += 1; throw new Error(`event content collision ${row.event_id}`); }
      if (!prior) { this.events.set(row.event_id, Object.freeze(row)); this.revision += 1; }
      this.prune(); return !prior;
    }
    merge(rows) {
      let added = 0;
      const batch = rows || [];
      BigTradeRecordValidator.validateHistoryRows(batch, "event_id", "last_time");
      for (const row of batch) {
        const prior = this.events.get(row.event_id);
        if (prior && prior.content_hash !== row.content_hash) { this.collisions += 1; throw new Error(`event content collision ${row.event_id}`); }
        if (!prior) { this.events.set(row.event_id, Object.freeze(row)); this.revision += 1; added += 1; }
      }
      this.prune();
      return added;
    }
    prune() { while (this.events.size > this.capacity) this.events.delete(this.sorted()[0].event_id); }
    get(id) { return this.events.get(id) || null; }
    sorted() { return Array.from(this.events.values()).sort((a, b) => compareKey(sourceKey(a, "last_time", "event_id"), sourceKey(b, "last_time", "event_id"))); }
    stats() { return { events: this.events.size, capacity: this.capacity, collisions: this.collisions }; }
  }

  class ReactionZoneStore {
    constructor(zoneCapacity = 5000, interactionCapacity = 20000) {
      this.zoneCapacity = zoneCapacity; this.interactionCapacity = interactionCapacity;
      this.zones = new Map(); this.interactions = new Map(); this.links = new Map();
      this.snapshots = new Map(); this.candles = new Map(); this.assessments = new Map();
      this.details = new Map(); this.runtimeState = new Map(); this.selectedZoneId = null; this.collisions = 0; this.revision = 0; this._sortedZonesCache = null;
    }
    insert(map, id, row) {
      const prior = map.get(id);
      if (prior && prior.content_hash !== row.content_hash) { this.collisions += 1; throw new Error(`content collision ${id}`); }
      if (!prior) { map.set(id, Object.freeze(row)); this.revision += 1; }
      return !prior;
    }
    ingestZone(row) {
      BigTradeRecordValidator.validateHistoryRow(row, "zone_id", "zone_source_start");
      const added = this.insert(this.zones, row.zone_id, row);
      if (added) this._sortedZonesCache = null;
      if (!this.runtimeState.has(row.zone_id)) this.runtimeState.set(row.zone_id, { lifecycle: row.lifecycle || "ACTIVE", relation: row.current_relation || null, sourceEnd: row.zone_source_end || null, gaps: (row.gap_segments || []).slice() });
      this.pruneZones(); return added;
    }
    ingestInteraction(row) {
      BigTradeRecordValidator.validateHistoryRow(row, "interaction_id", "source_event_time");
      const added = this.insert(this.interactions, row.interaction_id, row);
      if (added) {
        const state = this.runtimeState.get(row.zone_id) || { lifecycle: "ACTIVE", relation: null, sourceEnd: null, gaps: [] };
        if (row.current_relation) state.relation = row.current_relation;
        if (row.interaction_type === "SOURCE_GAP_STARTED") { state.lifecycle = "ACTIVE_WITH_GAP"; state.gaps.push({ gap_epoch_id: row.gap_epoch_id, start_time: row.source_event_time, end_time: null }); }
        if (row.interaction_type === "SOURCE_GAP_ENDED") { state.lifecycle = "ACTIVE_WITH_GAP"; const gap = [...state.gaps].reverse().find(item => item.gap_epoch_id === row.gap_epoch_id && !item.end_time); if (gap) gap.end_time = row.source_event_time; }
        if (row.interaction_type === "ZONE_SESSION_CLOSED") { state.lifecycle = "SESSION_CLOSED"; state.sourceEnd = row.source_event_time; }
        this.runtimeState.set(row.zone_id, state);
      }
      this.pruneInteractions(); return added;
    }
    mergeInteractions(rows) {
      let added = 0;
      const batch = rows || [];
      BigTradeRecordValidator.validateHistoryRows(batch, "interaction_id", "source_event_time");
      for (const row of batch) {
        const inserted = this.insert(this.interactions, row.interaction_id, row);
        if (!inserted) continue;
        added += 1;
        const state = this.runtimeState.get(row.zone_id) || { lifecycle: "ACTIVE", relation: null, sourceEnd: null, gaps: [] };
        if (row.current_relation) state.relation = row.current_relation;
        if (row.interaction_type === "SOURCE_GAP_STARTED") { state.lifecycle = "ACTIVE_WITH_GAP"; state.gaps.push({ gap_epoch_id: row.gap_epoch_id, start_time: row.source_event_time, end_time: null }); }
        if (row.interaction_type === "SOURCE_GAP_ENDED") { state.lifecycle = "ACTIVE_WITH_GAP"; const gap = [...state.gaps].reverse().find(item => item.gap_epoch_id === row.gap_epoch_id && !item.end_time); if (gap) gap.end_time = row.source_event_time; }
        if (row.interaction_type === "ZONE_SESSION_CLOSED") { state.lifecycle = "SESSION_CLOSED"; state.sourceEnd = row.source_event_time; }
        this.runtimeState.set(row.zone_id, state);
      }
      this.pruneInteractions();
      return added;
    }
    ingestLink(row) { BigTradeRecordValidator.validateHistoryRow(row, "link_id", "linked_time"); return this.insert(this.links, row.link_id, row); }
    ingestSnapshot(row) { BigTradeRecordValidator.validateHistoryRow(row, "snapshot_id", "target_time"); return this.insert(this.snapshots, row.snapshot_id, row); }
    ingestCandle(row) { BigTradeRecordValidator.validateHistoryRow(row, "candle_observation_id", "candle_id"); return this.insert(this.candles, row.candle_observation_id, row); }
    ingestAssessment(row) { BigTradeRecordValidator.validateHistoryRow(row, "assessment_id", "assessed_at_utc"); return this.insert(this.assessments, row.assessment_id, row); }
    ingestRecord(record) {
      const row = record.data;
      if (record.kind === "ZONE_CREATED") return this.ingestZone(row);
      if (record.kind === "ZONE_INTERACTION") return this.ingestInteraction(row);
      if (record.kind === "ZONE_EVENT_LINK") return this.ingestLink(row);
      if (record.kind === "RESULT_SNAPSHOT") return this.ingestSnapshot(row);
      if (record.kind === "CANDLE_OBSERVATION") return this.ingestCandle(row);
      if (record.kind === "USER_ASSESSMENT") return this.ingestAssessment(row);
      return false;
    }
    mergeDetail(body) {
      if (!body || !body.zone) return;
      this.ingestZone(body.zone);
      this.mergeInteractions(body.interactions || []);
      (body.linked_event_summary || []).forEach(row => this.ingestLink(row));
      (body.horizon_snapshots || []).forEach(row => this.ingestSnapshot(row));
      (body.candle_observations || []).forEach(row => this.ingestCandle(row));
      (body.user_assessment_history || []).forEach(row => this.ingestAssessment(row));
      if (body.latest_user_assessment) this.ingestAssessment(body.latest_user_assessment);
      this.details.set(body.zone.zone_id, body);
    }
    pruneZones() { while (this.zones.size > this.zoneCapacity) { const oldest = this.sortedZones()[0]; this.zones.delete(oldest.zone_id); this.runtimeState.delete(oldest.zone_id); this._sortedZonesCache = null; } }
    pruneInteractions() { while (this.interactions.size > this.interactionCapacity) { const oldest = Array.from(this.interactions.values()).sort((a, b) => compareKey(sourceKey(a, "source_event_time", "interaction_id"), sourceKey(b, "source_event_time", "interaction_id")))[0]; this.interactions.delete(oldest.interaction_id); } }
    sortedZones() { if (!this._sortedZonesCache) this._sortedZonesCache = Array.from(this.zones.values()).sort((a, b) => compareKey(sourceKey(a, "zone_source_start", "zone_id"), sourceKey(b, "zone_source_start", "zone_id"))); return this._sortedZonesCache; }
    visible({ side = "BOTH", state = "ACTIVE" } = {}) { return this.sortedZones().filter(zone => { const runtime = this.runtimeState.get(zone.zone_id) || {}; return (side === "BOTH" || zone.origin_side === side) && (state === "ALL" || runtime.lifecycle !== "SESSION_CLOSED"); }); }
    select(zoneId) { this.selectedZoneId = zoneId && this.zones.has(zoneId) ? zoneId : null; return this.selectedZoneId; }
    selected() { return this.selectedZoneId ? this.zones.get(this.selectedZoneId) || null : null; }
    state(zoneId) { return this.runtimeState.get(zoneId) || { lifecycle: "ACTIVE", relation: null, sourceEnd: null, gaps: [] }; }
    linksFor(zoneId) { return Array.from(this.links.values()).filter(row => row.zone_id === zoneId).sort((a, b) => a.ordinal_for_zone - b.ordinal_for_zone); }
    snapshotsFor(zoneId) { return Array.from(this.snapshots.values()).filter(row => row.zone_id === zoneId).sort((a, b) => a.horizon_seconds - b.horizon_seconds); }
    candlesFor(zoneId) { return Array.from(this.candles.values()).filter(row => row.zone_id === zoneId).sort((a, b) => Date.parse(a.candle_id) - Date.parse(b.candle_id)); }
    interactionsFor(zoneId) { return Array.from(this.interactions.values()).filter(row => row.zone_id === zoneId).sort((a, b) => a.ordinal - b.ordinal); }
    assessmentsFor(zoneId) { return Array.from(this.assessments.values()).filter(row => row.zone_id === zoneId).sort((a, b) => Date.parse(a.assessed_at_utc) - Date.parse(b.assessed_at_utc) || a.assessment_id.localeCompare(b.assessment_id)); }
    stats() { return { zones: this.zones.size, zoneCapacity: this.zoneCapacity, interactions: this.interactions.size, interactionCapacity: this.interactionCapacity, collisions: this.collisions }; }
  }

  class ReactionZoneProjection {
    constructor({ left = 42, right = 58, top = 20, bottom = 28, minZonePixels = 3 } = {}) { Object.assign(this, { left, right, top, bottom, minZonePixels }); }
    scales(width, height, zones, events, timeWindowMs, timeOffsetMs, candles = []) {
      const times = [];
      const prices = [];
      zones.forEach(zone => { times.push(Date.parse(zone.zone_source_start)); prices.push(num(zone.zone_low), num(zone.zone_high)); const event = events.get(zone.origin_event_id); if (event) { times.push(Date.parse(event.marker_time)); prices.push(num(event.marker_price)); } });
      candles.forEach(candle => {
        const candleTime = Date.parse(candle.bar_time || candle.time || candle.timestamp);
        if (Number.isFinite(candleTime)) times.push(candleTime);
        prices.push(num(candle.low ?? candle.l), num(candle.high ?? candle.h));
      });
      const validTimes = times.filter(Number.isFinite); const validPrices = prices.filter(Number.isFinite);
      const latest = validTimes.length ? Math.max(...validTimes) : Date.now();
      const maxTime = latest - timeOffsetMs; const minTime = maxTime - timeWindowMs;
      let minPrice = validPrices.length ? Math.min(...validPrices) : 0; let maxPrice = validPrices.length ? Math.max(...validPrices) : 1;
      const pad = Math.max((maxPrice - minPrice) * 0.12, Math.abs(maxPrice) * 0.0001, 1e-8); minPrice -= pad; maxPrice += pad;
      const innerW = Math.max(1, width - this.left - this.right), innerH = Math.max(1, height - this.top - this.bottom);
      return { minTime, maxTime, minPrice, maxPrice, x: time => this.left + (time - minTime) / Math.max(1, maxTime - minTime) * innerW, y: price => this.top + (maxPrice - price) / Math.max(1e-12, maxPrice - minPrice) * innerH };
    }
    zoneRect(zone, state, scale, latestTime) {
      const exactLow = num(zone.zone_low), exactHigh = num(zone.zone_high);
      const yLow = scale.y(exactLow), yHigh = scale.y(exactHigh); const exactHeight = Math.abs(yLow - yHigh);
      const visualHeight = Math.max(this.minZonePixels, exactHeight); const center = (yLow + yHigh) / 2;
      const endTime = state.sourceEnd ? Date.parse(state.sourceEnd) : latestTime;
      return { x: scale.x(Date.parse(zone.zone_source_start)), y: center - visualHeight / 2, width: Math.max(1, scale.x(endTime) - scale.x(Date.parse(zone.zone_source_start))), height: visualHeight, exactLow, exactHigh, exactHeight, visualHeight };
    }
  }

  class BigTradesContinuity {
    constructor(onGap) { this.onGap = onGap; this.streamId = null; this.lastSequence = 0; this.recovering = false; this.gapCount = 0; this.dropped = 0; }
    accept(payload) {
      const restart = this.streamId !== null && payload.stream_id !== this.streamId;
      const expected = this.lastSequence + 1; const sequenceGap = !restart && this.streamId !== null && payload.first_sequence !== expected;
      const dropped = payload.dropped_count > 0;
      if (restart || sequenceGap || dropped) { this.recovering = true; this.gapCount += 1; this.dropped += payload.dropped_count; if (this.onGap) this.onGap({ restart, sequenceGap, dropped: payload.dropped_count, expected, received: payload.first_sequence }); }
      this.streamId = payload.stream_id; this.lastSequence = payload.last_sequence;
      return { restart, sequenceGap, dropped, recovering: this.recovering };
    }
    seed(marker) { if (!marker || !marker.stream_id) return; if (!this.streamId) { this.streamId = marker.stream_id; this.lastSequence = marker.last_admitted_sequence; } }
    recovered(marker) {
      if (!marker || marker.stream_id !== this.streamId) return false;
      this.lastSequence = Math.max(this.lastSequence, marker.last_admitted_sequence);
      this.dropped = Math.max(this.dropped, marker.dropped_count || 0);
      this.recovering = false; return true;
    }
    label() { return this.recovering ? `GAP RECOVERING · ${this.gapCount}` : `STREAM ${this.streamId ? this.streamId.slice(0, 8) : "—"} · SEQ ${this.lastSequence} · DROP ${this.dropped}`; }
  }

  class BigTradesCanvas {
    constructor({ canvas, tooltip, eventStore, zoneStore, candlesProvider, onSelect, onNeedOlder, onViewport }) {
      this.canvas = canvas; this.tooltip = tooltip; this.eventStore = eventStore; this.zoneStore = zoneStore;
      this.onSelect = onSelect; this.onNeedOlder = onNeedOlder; this.onViewport = onViewport;
      this.candlesProvider = candlesProvider || (() => []);
      this.projection = new ReactionZoneProjection(); this.active = false; this.zonesOn = true; this._lastRenderSignature = null;
      this.side = "BOTH"; this.stateFilter = "ACTIVE"; this.liveLock = true; this.timeWindowMs = 15 * 60 * 1000; this.timeOffsetMs = 0;
      this.hitZones = []; this.hitBadges = []; this.drag = null; this.crosshair = null; this.drawTimes = []; this._handlers = null;
      this.resizeObserver = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => this.draw(true)) : null;
      if (this.resizeObserver) this.resizeObserver.observe(canvas);
    }
    setActive(active) { if (this.active === active) return; this.active = active; active ? this.attach() : this.detach(); if (active) { this.canvas.focus({ preventScroll: true }); this.draw(true); } }
    attach() {
      this._handlers = {
        move: event => this.pointerMove(event), leave: () => { this.tooltip.hidden = true; this.crosshair = null; this.draw(); }, click: event => this.click(event),
        down: event => { this.drag = { x: event.clientX, offset: this.timeOffsetMs }; this.liveLock = false; this.canvas.setPointerCapture?.(event.pointerId); },
        up: event => { this.drag = null; this.canvas.releasePointerCapture?.(event.pointerId); },
        wheel: event => this.wheel(event), key: event => this.key(event), context: event => event.preventDefault(),
      };
      this.canvas.addEventListener("pointermove", this._handlers.move); this.canvas.addEventListener("pointerleave", this._handlers.leave);
      this.canvas.addEventListener("click", this._handlers.click); this.canvas.addEventListener("pointerdown", this._handlers.down);
      this.canvas.addEventListener("pointerup", this._handlers.up); this.canvas.addEventListener("wheel", this._handlers.wheel, { passive: false });
      this.canvas.addEventListener("keydown", this._handlers.key); this.canvas.addEventListener("contextmenu", this._handlers.context);
    }
    detach() { if (!this._handlers) return; const h = this._handlers; this.canvas.removeEventListener("pointermove", h.move); this.canvas.removeEventListener("pointerleave", h.leave); this.canvas.removeEventListener("click", h.click); this.canvas.removeEventListener("pointerdown", h.down); this.canvas.removeEventListener("pointerup", h.up); this.canvas.removeEventListener("wheel", h.wheel); this.canvas.removeEventListener("keydown", h.key); this.canvas.removeEventListener("contextmenu", h.context); this._handlers = null; this.drag = null; this.tooltip.hidden = true; }
    setFilters({ side, state, zonesOn }) { this.side = side; this.stateFilter = state; this.zonesOn = zonesOn; this.draw(true); }
    lockLive() { this.liveLock = true; this.timeOffsetMs = 0; this.draw(true); }
    point(event) { const rect = this.canvas.getBoundingClientRect(); return { x: event.clientX - rect.left, y: event.clientY - rect.top, rect }; }
    pointerMove(event) {
      const point = this.point(event);
      this.crosshair = point;
      if (this.drag) { this.timeOffsetMs = Math.max(0, this.drag.offset + (this.drag.x - event.clientX) / Math.max(1, point.rect.width) * this.timeWindowMs); if (this.timeOffsetMs > this.timeWindowMs * 0.8 && this.onNeedOlder) this.onNeedOlder(); this.draw(); return; }
      const hit = [...this.hitBadges, ...this.hitZones].reverse().find(item => point.x >= item.x && point.x <= item.x + item.width && point.y >= item.y && point.y <= item.y + item.height);
      if (!hit) { this.tooltip.hidden = true; return; }
      const zone = this.zoneStore.zones.get(hit.zoneId), eventRow = zone ? this.eventStore.get(zone.origin_event_id) : null, state = zone ? this.zoneStore.state(zone.zone_id) : {};
      this.tooltip.textContent = `${zone?.origin_side || "—"} ${eventRow?.aggregate_quantity || "—"}\nRANGE ${zone?.zone_low || "—"} – ${zone?.zone_high || "—"}\n${state.relation || "AWAITING RESULT"}`;
      this.tooltip.style.left = `${Math.min(point.rect.width - 260, Math.max(4, point.x + 10))}px`; this.tooltip.style.top = `${Math.max(4, point.y - 48)}px`; this.tooltip.hidden = false;
      this.draw();
    }
    click(event) { const point = this.point(event); const badge = this.hitBadges.find(item => point.x >= item.x && point.x <= item.x + item.width && point.y >= item.y && point.y <= item.y + item.height); if (badge) { const target = this.zoneStore.sortedZones().find(zone => zone.origin_event_id === badge.eventId); if (target) this.select(target.zone_id); return; } const hit = this.hitZones.find(item => point.x >= item.x && point.x <= item.x + item.width && point.y >= item.y && point.y <= item.y + item.height); this.select(hit ? hit.zoneId : null); }
    select(zoneId) { this.zoneStore.select(zoneId); if (this.onSelect) this.onSelect(zoneId); this.draw(true); }
    key(event) {
      if (event.key === "Escape") { event.preventDefault(); this.select(null); return; }
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); const zones = this.zoneStore.visible({ side: this.side, state: this.stateFilter }); if (!zones.length) return; const current = zones.findIndex(zone => zone.zone_id === this.zoneStore.selectedZoneId); const delta = event.key === "ArrowLeft" ? -1 : 1; this.select(zones[Math.max(0, Math.min(zones.length - 1, (current < 0 ? zones.length - 1 : current) + delta))].zone_id); }
      if (event.key.toLowerCase() === "l") this.lockLive();
    }
    wheel(event) { event.preventDefault(); this.liveLock = false; const factor = event.deltaY > 0 ? 1.2 : 0.82; this.timeWindowMs = Math.max(60_000, Math.min(24 * 3600_000, this.timeWindowMs * factor)); if (this.onViewport) this.onViewport(this); this.draw(true); }
    draw(force) {
      if (!this.active && !force) return; const started = performance.now(); const rect = this.canvas.getBoundingClientRect(); const dpr = Math.max(1, global.devicePixelRatio || 1); const width = Math.max(1, Math.round(rect.width)), height = Math.max(1, Math.round(rect.height));
      const renderSignature = `${width}|${height}|${dpr}|${this.eventStore.revision}|${this.zoneStore.revision}|${this.zoneStore.selectedZoneId || ""}|${this.side}|${this.stateFilter}|${this.zonesOn}|${this.timeWindowMs}|${this.timeOffsetMs}`;
      if (!force && !this.crosshair && renderSignature === this._lastRenderSignature) { this.recordDraw(started); return; }
      this._lastRenderSignature = renderSignature;
      if (this.canvas.width !== Math.round(width * dpr) || this.canvas.height !== Math.round(height * dpr)) { this.canvas.width = Math.round(width * dpr); this.canvas.height = Math.round(height * dpr); }
      const ctx = this.canvas.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, width, height); ctx.fillStyle = "#060C16"; ctx.fillRect(0, 0, width, height);
      ctx.strokeStyle = "#17243B"; ctx.lineWidth = 1; for (let x = 42; x < width - 40; x += 84) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke(); } for (let y = 20; y < height - 20; y += 48) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }
      const visibleZones = this.zoneStore.visible({ side: this.side, state: this.stateFilter }); const zones = visibleZones.slice().sort((left, right) => Number(this.zoneStore.state(left.zone_id).lifecycle !== "SESSION_CLOSED") - Number(this.zoneStore.state(right.zone_id).lifecycle !== "SESSION_CLOSED")); const events = this.eventStore.events; const candles = (this.candlesProvider() || []).slice(-500); this.hitZones = []; this.hitBadges = [];
      if (!zones.length) { ctx.fillStyle = "#6E7B96"; ctx.font = "800 12px ui-monospace,monospace"; ctx.fillText("BIG TRADES · NO COMMITTED DATA", 52, 52); this.recordDraw(started); return; }
      const scale = this.projection.scales(width, height, zones, events, this.timeWindowMs, this.liveLock ? 0 : this.timeOffsetMs, candles); const latestTime = scale.maxTime;
      const candleWidth = Math.max(2, Math.min(10, (width - this.projection.left - this.projection.right) / Math.max(20, this.timeWindowMs / 60000) * 0.62));
      candles.forEach(candle => {
        const at = Date.parse(candle.bar_time || candle.time || candle.timestamp), open = num(candle.open ?? candle.o), high = num(candle.high ?? candle.h), low = num(candle.low ?? candle.l), close = num(candle.close ?? candle.c);
        if (![at, open, high, low, close].every(Number.isFinite) || at < scale.minTime || at > scale.maxTime) return;
        const x = scale.x(at), yOpen = scale.y(open), yHigh = scale.y(high), yLow = scale.y(low), yClose = scale.y(close), up = close >= open;
        ctx.strokeStyle = up ? "#237D5A" : "#853342"; ctx.fillStyle = up ? "#123C30" : "#421D26"; ctx.beginPath(); ctx.moveTo(x, yHigh); ctx.lineTo(x, yLow); ctx.stroke(); ctx.fillRect(x - candleWidth / 2, Math.min(yOpen, yClose), candleWidth, Math.max(1, Math.abs(yOpen - yClose)));
      });
      ctx.font = "800 9px ui-monospace,monospace";
      const zoneFillPath = new Path2D(), zonePaths = { BUY:new Path2D(), SELL:new Path2D() }, exactPaths = { BUY:new Path2D(), SELL:new Path2D() }, markerPaths = { BUY:new Path2D(), SELL:new Path2D() }, renderItems = [];
      const dense = zones.length > 500, labelStride = Math.max(1, Math.ceil(zones.length / 100));
      zones.forEach((zone, zoneIndex) => {
        const eventRow = events.get(zone.origin_event_id); const state = this.zoneStore.state(zone.zone_id); const box = this.projection.zoneRect(zone, state, scale, latestTime); if (box.x + box.width < 0 || box.x > width) return;
        const color = zone.origin_side === "BUY" ? "#19C979" : "#FF4058", side = color === "#19C979" ? "BUY" : "SELL";
        if (this.zonesOn) { zoneFillPath.rect(box.x, box.y, box.width, box.height); zonePaths[side].rect(box.x, box.y, box.width, box.height); exactPaths[side].moveTo(box.x, scale.y(box.exactHigh)); exactPaths[side].lineTo(box.x, scale.y(box.exactLow)); }
        const markerTime = eventRow ? Date.parse(eventRow.marker_time) : Date.parse(zone.zone_source_start), markerPrice = eventRow ? num(eventRow.marker_price) : num(zone.zone_anchor); const mx = scale.x(markerTime), my = scale.y(markerPrice), selected = zone.zone_id === this.zoneStore.selectedZoneId, drawLabel = zoneIndex % labelStride === 0;
        if (dense && !selected) markerPaths[side].rect(mx - 1, my - 1, 2, 2); else { markerPaths[side].moveTo(mx + (selected ? 8 : 6), my); markerPaths[side].arc(mx, my, selected ? 8 : 6, 0, Math.PI * 2); }
        if (drawLabel || selected || state.gaps.length || this.zoneStore.links.size) renderItems.push({ zone, eventRow, state, box, mx, my, drawLabel });
        this.hitZones.push({ ...box, zoneId: zone.zone_id });
      });
      if (this.zonesOn) { if (!dense) { ctx.fillStyle = "rgba(130,145,170,.10)"; ctx.fill(zoneFillPath); } for (const side of ["BUY", "SELL"]) { ctx.strokeStyle = side === "BUY" ? "#19C979" : "#FF4058"; if (!dense) ctx.stroke(zonePaths[side]); ctx.stroke(exactPaths[side]); } }
      for (const side of ["BUY", "SELL"]) { ctx.fillStyle = side === "BUY" ? "#19C979" : "#FF4058"; ctx.fill(markerPaths[side]); }
      renderItems.forEach(({ zone, eventRow, state, box, mx, my, drawLabel }) => {
        if (this.zonesOn && state.gaps.length) state.gaps.forEach(gap => { const gx1 = scale.x(Date.parse(gap.start_time)), gx2 = scale.x(gap.end_time ? Date.parse(gap.end_time) : latestTime); ctx.save(); ctx.beginPath(); ctx.rect(Math.max(box.x, gx1), box.y, Math.max(1, Math.min(box.x + box.width, gx2) - Math.max(box.x, gx1)), box.height); ctx.clip(); ctx.strokeStyle = "#F4C542"; for (let x = gx1 - box.height; x < gx2 + box.height; x += 6) { ctx.beginPath(); ctx.moveTo(x, box.y + box.height); ctx.lineTo(x + box.height, box.y); ctx.stroke(); } ctx.restore(); });
        if (drawLabel) { ctx.fillStyle = "#F1F5FF"; ctx.fillText(`${zone.origin_side} ${eventRow ? eventRow.aggregate_quantity : "—"}`, mx + 9, my - 7); ctx.fillStyle = state.relation === "ABOVE" ? "#19C979" : state.relation === "BELOW" ? "#FF4058" : "#F4C542"; ctx.fillText(state.relation || "AWAITING RESULT", mx + 9, my + 6); }
        if (zone.zone_id === this.zoneStore.selectedZoneId) { ctx.strokeStyle = "#F4C542"; ctx.lineWidth = 2; ctx.strokeRect(box.x - 2, box.y - 2, box.width + 4, box.height + 4); ctx.lineWidth = 1; }
        if (this.zoneStore.links.size) this.zoneStore.linksFor(zone.zone_id).forEach(link => { const lx = scale.x(Date.parse(link.linked_time)), ly = scale.y((num(link.linked_low) + num(link.linked_high)) / 2); ctx.fillStyle = "#8B63E6"; ctx.fillRect(lx - 8, ly - 8, 16, 16); ctx.fillStyle = "#fff"; ctx.fillText(String(link.ordinal_for_zone), lx - 3, ly + 3); this.hitBadges.push({ x: lx - 8, y: ly - 8, width: 16, height: 16, zoneId: zone.zone_id, eventId: link.linked_event_id }); });
      });
      if (this.crosshair) { ctx.save(); ctx.setLineDash([3, 4]); ctx.strokeStyle = "rgba(201,211,234,.42)"; ctx.beginPath(); ctx.moveTo(this.crosshair.x, 0); ctx.lineTo(this.crosshair.x, height); ctx.moveTo(0, this.crosshair.y); ctx.lineTo(width, this.crosshair.y); ctx.stroke(); ctx.restore(); }
      ctx.fillStyle = "#7F8EAD"; ctx.fillText(new Date(scale.minTime).toISOString().slice(11, 16), 42, height - 8); ctx.fillText(new Date(scale.maxTime).toISOString().slice(11, 16), width - 88, height - 8); this.recordDraw(started);
    }
    recordDraw(started) { this.drawTimes.push(performance.now() - started); if (this.drawTimes.length > 300) this.drawTimes.shift(); if (this.onViewport) this.onViewport(this); }
    stats() { return { renderP95Ms: p95(this.drawTimes), windowMs: Math.round(this.timeWindowMs), liveLock: this.liveLock, dpr: global.devicePixelRatio || 1 }; }
  }

  class BigTradesSettingsController {
    constructor(elements, fetcher, onChange, onStatus) { this.elements = elements; this.fetcher = fetcher; this.onChange = onChange; this.onStatus = onStatus; this.calibrationId = null; this.bind(); }
    bind() { this.elements.mode.addEventListener("change", () => this.syncDisabled()); this.elements.apply.addEventListener("click", () => this.apply()); [this.elements.side, this.elements.zones, this.elements.state].forEach(element => element.addEventListener("change", () => this.emit())); this.syncDisabled(); }
    syncDisabled() { const manual = this.elements.mode.value === "MANUAL"; this.elements.min.disabled = !manual; this.elements.max.disabled = !manual; this.elements.intensity.disabled = manual; this.emit(); }
    emit() { if (this.onChange) this.onChange({ side: this.elements.side.value, state: this.elements.state.value, zonesOn: this.elements.zones.value === "ON" }); }
    async load() { try { const response = await this.fetcher("/api/big-trades/settings"); if (!response.ok) throw new Error(`SETTINGS HTTP ${response.status}`); const body = await response.json(); const source = body.pending?.settings || body.active; if (source) { this.elements.mode.value = source.filter_mode; this.elements.min.value = source.manual_min_quantity; this.elements.max.value = source.manual_max_quantity; this.elements.intensity.value = source.automatic_intensity; this.elements.side.value = source.side_filter; this.elements.mark.value = source.marker_price_mode; this.calibrationId = source.calibration_id; this.elements.cal.textContent = shortId(source.calibration_id); } this.syncDisabled(); } catch (error) { if (this.onStatus) this.onStatus(String(error.message || error), true); } }
    body() { const decimal = value => { const text = value.trim(); if (!DECIMAL.test(text) || Number(text) < 0) throw new Error("MIN/MAX must be non-negative Decimal text"); return text; }; return { filter_mode: this.elements.mode.value, manual_min_quantity: decimal(this.elements.min.value), manual_max_quantity: decimal(this.elements.max.value), automatic_intensity: this.elements.intensity.value, side_filter: this.elements.side.value, marker_price_mode: this.elements.mark.value, calibration_id: this.elements.mode.value === "AUTOMATIC" ? this.calibrationId : null }; }
    async apply() { this.elements.apply.disabled = true; try { const response = await this.fetcher("/api/big-trades/settings", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(this.body()) }); const result = await response.json(); if (!response.ok) throw new Error(result.reason || `SETTINGS HTTP ${response.status}`); if (this.onStatus) this.onStatus(`SETTINGS ${result.status} · ${shortId(result.request?.request_id)}`, false); } catch (error) { if (this.onStatus) this.onStatus(String(error.message || error), true); } finally { this.elements.apply.disabled = false; this.syncDisabled(); } }
  }

  class BigTradesAssessmentController {
    constructor({ select, note, save, history, fetcher, getZoneId, getSourceTime, getSupersedesId, onSaved, onStatus }) { Object.assign(this, { select, note, save, history, fetcher, getZoneId, getSourceTime, getSupersedesId, onSaved, onStatus }); ASSESSMENTS.forEach(value => { const option = document.createElement("option"); option.value = value; option.textContent = value; select.appendChild(option); }); save.addEventListener("click", () => this.submit()); }
    render(rows) { this.history.textContent = rows && rows.length ? rows.map(row => `${row.assessed_at_utc} · ${row.assessment}${row.user_note ? ` · ${row.user_note}` : ""}`).join("\n") : "—"; }
    async submit() { const zoneId = this.getZoneId(), sourceTime = this.getSourceTime(); if (!zoneId || !sourceTime) return; if (this.note.value.length > 2000) { this.onStatus("ASSESSMENT NOTE > 2000", true); return; } this.save.disabled = true; try { const response = await this.fetcher(`/api/big-trades/zones/${encodeURIComponent(zoneId)}/assessments`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ assessment: this.select.value, assessed_against_source_time: sourceTime, user_note: this.note.value || null, supersedes_assessment_id: this.getSupersedesId() }) }); const body = await response.json(); if (!response.ok) throw new Error(body.reason || `ASSESSMENT HTTP ${response.status}`); this.note.value = ""; if (this.onSaved) this.onSaved(body.assessment); } catch (error) { this.onStatus(String(error.message || error), true); } finally { this.save.disabled = false; } }
  }

  class BigTradesContextLink {
    constructor(provider) { this.provider = provider || (() => ({})); }
    read(zone) { const value = this.provider(zone) || {}; return { sourceId: value.sourceId ?? null, sourceTime: value.sourceTime ?? null, flowSourceId: value.flowSourceId ?? null, flowSourceTime: value.flowSourceTime ?? null, cvd: value.cvd ?? null, delta: value.delta ?? null, volume: value.volume ?? null, flowResponse: value.flowResponse ?? null, absorption: value.absorption ?? null, imbalance: value.imbalance ?? null }; }
  }

  class BigTradesUI {
    constructor(options) {
      this.options = options; this.fetcher = options.fetcher || global.fetch.bind(global); this.eventStore = new BigTradeEventStore(5000); this.zoneStore = new ReactionZoneStore(5000, 20000); this.contextLink = new BigTradesContextLink(options.contextProvider); this.hydrated = false; this.hydrating = false; this.eventCursor = null; this.zoneCursor = null; this.active = false; this.status = "DISABLED";
      this.continuity = new BigTradesContinuity(info => { this.setStatus(`GAP RECOVERING · EXPECT ${info.expected} GOT ${info.received} · DROP ${info.dropped}`, true); this.recover(); });
      this.canvas = new BigTradesCanvas({ canvas: options.canvas, tooltip: options.tooltip, eventStore: this.eventStore, zoneStore: this.zoneStore, candlesProvider: options.candlesProvider, onSelect: zoneId => this.selectZone(zoneId), onNeedOlder: () => this.loadOlder(), onViewport: chart => this.updateCanvasStatus(chart) });
      this.settings = new BigTradesSettingsController(options.controls, this.fetcher, filters => this.canvas.setFilters(filters), (text, warning) => this.setStatus(text, warning));
      this.assessment = new BigTradesAssessmentController({ select: options.assessmentSelect, note: options.assessmentNote, save: options.assessmentSave, history: options.assessmentHistory, fetcher: this.fetcher, getZoneId: () => this.zoneStore.selectedZoneId, getSourceTime: () => this.assessmentSourceTime(), getSupersedesId: () => { const rows = this.zoneStore.assessmentsFor(this.zoneStore.selectedZoneId); return rows.length ? rows[rows.length - 1].assessment_id : null; }, onSaved: row => { this.zoneStore.ingestAssessment(row); this.renderDetail(); }, onStatus: (text, warning) => this.setStatus(text, warning) });
    }
    assessmentSourceTime() { const zone = this.zoneStore.selected(); if (!zone) return null; const detail = this.zoneStore.details.get(zone.zone_id); const candidates = [zone.zone_source_end, zone.zone_source_start, this.eventStore.get(zone.origin_event_id)?.last_time, detail?.latest_checkpoint?.source_bucket_time, ...this.zoneStore.interactionsFor(zone.zone_id).map(row => row.source_event_time), ...this.zoneStore.snapshotsFor(zone.zone_id).flatMap(row => [row.target_time, row.snapshot_trade_time]), ...this.zoneStore.candlesFor(zone.zone_id).map(row => row.candle_id)]; return candidates.filter(value => value && Number.isFinite(Date.parse(value))).sort((left, right) => Date.parse(left) - Date.parse(right)).at(-1) || null; }
    setActive(active) { this.active = active; this.canvas.setActive(active); if (active && !this.hydrated) { this.hydrate(); this.settings.load(); } if (active) this.renderDetail(); }
    ingestStatus(message) { try { BigTradeRecordValidator.validateStatus(message); this.status = message.payload.status; this.options.serverStatus.textContent = `${message.payload.status}${message.payload.reason ? ` · ${message.payload.reason}` : ""}`; this.options.serverStatus.classList.toggle("warning", !["MANUAL_READY", "AUTOMATIC_READY"].includes(this.status)); } catch (error) { this.setStatus(`INVALID STATUS · ${error.message}`, true); } }
    ingestUpdate(message) { let validated; try { validated = BigTradeRecordValidator.validateUpdate(message); this.assertCompatible(validated.payload.records); } catch (error) { this.setStatus(`INVALID BIG TRADES PAYLOAD · ${error.message}`, true); return false; } const result = this.continuity.accept(validated.payload); try { validated.payload.records.forEach(record => { if (record.kind === "EVENT_CREATED") this.eventStore.ingest(record.data); else this.zoneStore.ingestRecord(record); }); } catch (error) { this.continuity.recovering = true; this.continuity.gapCount += 1; this.setStatus(`BIG TRADES CONTENT COLLISION · ${error.message}`, true); this.recover(); return false; } if (result.recovering) this.recover(); else this.setStatus(this.continuity.label(), false); this.canvas.draw(); this.renderDetail(); return true; }
    assertCompatible(records) { const seen = new Map(); records.forEach(record => { const key = `${record.kind}:${record.record_id}`, priorBatch = seen.get(key); if (priorBatch && priorBatch !== record.content_hash) throw new Error(`batch content collision ${record.record_id}`); seen.set(key, record.content_hash); const map = record.kind === "EVENT_CREATED" ? this.eventStore.events : record.kind === "ZONE_CREATED" ? this.zoneStore.zones : record.kind === "ZONE_INTERACTION" ? this.zoneStore.interactions : record.kind === "ZONE_EVENT_LINK" ? this.zoneStore.links : record.kind === "RESULT_SNAPSHOT" ? this.zoneStore.snapshots : record.kind === "CANDLE_OBSERVATION" ? this.zoneStore.candles : this.zoneStore.assessments; const prior = map.get(record.record_id); if (prior && prior.content_hash !== record.content_hash) throw new Error(`existing content collision ${record.record_id}`); }); }
    async hydrate(recovery = false) { if (this.hydrating) return false; this.hydrating = true; try { const response = await this.fetcher("/api/history/big-trades/snapshot?event_limit=500&zone_limit=500"); const body = await response.json(); if (!response.ok) throw new Error(body.reason || `HISTORY HTTP ${response.status}`); this.eventStore.merge(body.events); (body.zones || []).forEach(zone => this.zoneStore.ingestZone(zone)); this.eventCursor = body.event_cursor; this.zoneCursor = body.zone_cursor; this.continuity.seed(body.continuation); this.hydrated = true; if (!recovery || this.continuity.recovered(body.continuation)) this.setStatus(this.continuity.label(), false); this.canvas.draw(true); return true; } catch (error) { this.setStatus(`${recovery ? "GAP RECOVERY FAILED" : "HISTORY UNAVAILABLE"} · ${error.message}`, true); return false; } finally { this.hydrating = false; } }
    async recover() { return this.hydrate(true); }
    async loadOlder() { if (!this.zoneCursor || this.hydrating) return; this.hydrating = true; try { const query = new URLSearchParams({ limit: "500", before_source_time: this.zoneCursor.before_source_time, before_id: this.zoneCursor.before_id }); const response = await this.fetcher(`/api/history/big-trades/zones?${query}`); const body = await response.json(); if (!response.ok) throw new Error(body.reason || `HISTORY HTTP ${response.status}`); (body.zones || []).forEach(zone => this.zoneStore.ingestZone(zone)); this.zoneCursor = body.next_cursor; this.canvas.draw(true); } catch (error) { this.setStatus(`OLDER HISTORY FAILED · ${error.message}`, true); } finally { this.hydrating = false; } }
    async selectZone(zoneId) { this.zoneStore.select(zoneId); this.renderDetail(); if (!zoneId) return; try { const response = await this.fetcher(`/api/history/big-trades/zones/${encodeURIComponent(zoneId)}`); const body = await response.json(); if (!response.ok) throw new Error(body.reason || `DETAIL HTTP ${response.status}`); this.zoneStore.mergeDetail(body); this.eventStore.ingest(body.origin_event); this.renderDetail(); this.canvas.draw(true); } catch (error) { this.setStatus(`ZONE DETAIL FAILED · ${error.message}`, true); } }
    section(title, rows, className = "bt-detail-section") { return `<section class="${className}"><h3>${escapeHtml(title)}</h3>${rows.map(([key, value]) => `<div class="bt-detail-row"><span>${escapeHtml(key)}</span><b>${escapeHtml(value)}</b></div>`).join("")}</section>`; }
    renderDetail() {
      const zone = this.zoneStore.selected(), detail = zone ? this.zoneStore.details.get(zone.zone_id) : null, eventRow = detail?.origin_event || (zone ? this.eventStore.get(zone.origin_event_id) : null), state = zone ? this.zoneStore.state(zone.zone_id) : {}, snapshots = detail?.horizon_snapshots || (zone ? this.zoneStore.snapshotsFor(zone.zone_id) : []), links = detail?.linked_event_summary || (zone ? this.zoneStore.linksFor(zone.zone_id) : []), interactions = zone ? this.zoneStore.interactionsFor(zone.zone_id) : [], candles = detail?.candle_observations || (zone ? this.zoneStore.candlesFor(zone.zone_id) : []), assessments = zone ? this.zoneStore.assessmentsFor(zone.zone_id) : [], context = this.contextLink.read(zone);
      const no = "—"; const firstExit = detail?.first_exit; const excursions = detail?.excursions || {}; const counts = detail?.interaction_counts || {}; const latestCandle = candles.length ? candles[candles.length - 1] : null; const latestAssessment = assessments.length ? assessments[assessments.length - 1] : detail?.latest_user_assessment;
      const interactionTimeline = interactions.length ? interactions.map(item => `${String(item.source_event_time).slice(11, 23)} ${item.interaction_type}${item.current_relation ? ` · ${item.current_relation}` : ""}`).join(" · ") : no;
      this.options.assessmentSelect.disabled = !zone; this.options.assessmentNote.disabled = !zone; this.options.assessmentSave.disabled = !zone;
      this.options.detail.innerHTML = `<div class="bt-selected-title">SELECTED REACTION ZONE</div>` +
        this.section("EFFORT", [["SIDE", eventRow?.side || no], ["AGGREGATE QTY", eventRow?.aggregate_quantity || no], ["FILLS", eventRow?.fill_count ?? no], ["DURATION", eventRow ? `${eventRow.duration_ms} ms` : no], ["EXECUTION RANGE", zone ? `${zone.zone_low} – ${zone.zone_high}` : no], ["VWAP", eventRow?.vwap || no], ["THRESHOLD", eventRow?.threshold_used || no]]) +
        this.section("RESULT", [["CURRENT", state.relation || zone?.current_relation || no], ["FIRST EXIT", firstExit ? `${firstExit.direction || firstExit.interaction_type} · ${firstExit.time_to_exit_ms ?? no} ms` : no], ["MAX ABOVE", excursions.max_above_ticks ? `${excursions.max_above_ticks} ticks` : no], ["MAX BELOW", excursions.max_below_ticks ? `${excursions.max_below_ticks} ticks` : no], ["1s..600s", snapshots.length ? snapshots.map(item => `${item.horizon_seconds}s ${item.relation || item.validity}`).join(" · ") : no]]) +
        this.section("REPEATED AREA ACTIVITY", [["LINKED EVENTS", links.length], ["LINKED BUY / SELL", links.length ? links.map(item => `${item.linked_side} ${item.linked_quantity}`).join(" · ") : no], ["TOUCHES", (counts.TOUCH_FROM_ABOVE || 0) + (counts.TOUCH_FROM_BELOW || 0)], ["REENTRIES", (counts.REENTER_FROM_ABOVE || 0) + (counts.REENTER_FROM_BELOW || 0)], ["CROSSES", (counts.CROSS_UP || 0) + (counts.CROSS_DOWN || 0)], ["INSIDE BUY / SELL", detail?.latest_checkpoint ? `${detail.latest_checkpoint.inside_buy_quantity} / ${detail.latest_checkpoint.inside_sell_quantity}` : no], ["TIMELINE", interactionTimeline]]) +
        this.section("CANDLE RESULT", [["CLOSE", latestCandle ? (latestCandle.closed_above ? "CLOSE ABOVE" : latestCandle.closed_below ? "CLOSE BELOW" : "CLOSED INSIDE") : no], ["UPPER WICK RETURN", latestCandle ? String(latestCandle.upper_wick_return) : no], ["LOWER WICK RETURN", latestCandle ? String(latestCandle.lower_wick_return) : no], ["LAST CANDLE ID", latestCandle?.candle_id || no]]) +
        this.section("CONTEXT", [["SOURCE ID", context.sourceId ?? no], ["SOURCE TIME", context.sourceTime ?? no], ["CVD", context.cvd ?? no], ["DELTA", context.delta ?? no], ["VOLUME", context.volume ?? no], ["FLOW RESPONSE", context.flowResponse ?? no], ["FLOW SOURCE ID", context.flowSourceId ?? no], ["FLOW SOURCE TIME", context.flowSourceTime ?? no], ["ABSORPTION", context.absorption ?? no], ["IMBALANCE", context.imbalance ?? no]]) +
        this.section("SYSTEM FACTS", [["LIFECYCLE", state.lifecycle || zone?.lifecycle || no], ["RELATION", state.relation || no], ["INTERACTIONS", interactions.length], ["SOURCE GAPS", state.gaps?.length || 0]], "bt-detail-section bt-system-facts") +
        this.section("USER ASSESSMENT", [["LATEST", latestAssessment?.assessment || "UNASSESSED"], ["NOTE", latestAssessment?.user_note || no], ["HISTORY", assessments.length]], "bt-detail-section bt-user-assessment") +
        this.section("LINEAGE", [["EVENT", shortId(eventRow?.event_id)], ["ZONE", shortId(zone?.zone_id)], ["SETTINGS", shortId(zone?.settings_id)], ["CALIBRATION", shortId(zone?.calibration_id)], ["ACTIVATION", shortId(zone?.activation_id)], ["LOGIC", zone?.logic_version || no]]);
      this.assessment.render(assessments); this.renderObservation({ zone, eventRow, state, snapshots, links, context, firstExit, excursions });
    }
    renderObservation(data) { const { zone, eventRow, state, snapshots, links, context, firstExit, excursions } = data; const horizon = snapshots.length ? snapshots.map(item => `<div class="bt-ob-row"><span>${item.horizon_seconds}s</span><b>${escapeHtml(item.relation || item.validity)}</b></div>`).join("") : `<div class="bt-ob-row"><span>1s..600s</span><b>—</b></div>`; this.options.observation.innerHTML = `<header><b>BIG TRADES OBSERVATION</b><span>SYSTEM FACTS · NO TRADE SIGNALS</span></header><section><h3>SELECTED EFFORT</h3><strong class="${eventRow?.side === "BUY" ? "buy" : "sell"}">${escapeHtml(eventRow ? `${eventRow.side} ${eventRow.aggregate_quantity}` : "—")}</strong></section><section><h3>PRICE RESULT</h3><div class="bt-ob-row"><span>FIRST EXIT</span><b>${escapeHtml(firstExit?.direction || firstExit?.interaction_type || "—")}</b></div><div class="bt-ob-row"><span>CURRENT</span><b>${escapeHtml(state.relation || "—")}</b></div><div class="bt-ob-row"><span>MAX ABOVE / BELOW</span><b>${escapeHtml(`${excursions.max_above_ticks || "—"} / ${excursions.max_below_ticks || "—"}`)}</b></div><div class="bt-ob-row"><span>LINKED</span><b>${links.length}</b></div></section><section><h3>HORIZON FACTS</h3>${horizon}</section><section><h3>READ-ONLY CONTEXT</h3><div class="bt-ob-row"><span>CVD</span><b>${escapeHtml(context.cvd ?? "—")}</b></div><div class="bt-ob-row"><span>DELTA</span><b>${escapeHtml(context.delta ?? "—")}</b></div><div class="bt-ob-row"><span>FLOW RESPONSE</span><b>${escapeHtml(context.flowResponse ?? "—")}</b></div></section><div class="bt-ob-notice">This panel shows executed effort and subsequent price facts. It does not label absorption, buyer victory, seller victory, entry, or exit.</div>`; }
    updateCanvasStatus(chart) { const stats = chart.stats(), stores = { ...this.eventStore.stats(), ...this.zoneStore.stats() }; this.options.canvasStatus.textContent = `${chart.liveLock ? "LIVE LOCK" : "HISTORY"} · EVENTS ${stores.events}/${stores.capacity} · ZONES ${stores.zones}/${stores.zoneCapacity} · INTERACTIONS ${stores.interactions}/${stores.interactionCapacity} · DPR ${stats.dpr} · RENDER P95 ${stats.renderP95Ms === null ? "—" : stats.renderP95Ms.toFixed(2) + "ms"}`; }
    setStatus(text, warning) { this.options.streamStatus.textContent = text; this.options.streamStatus.classList.toggle("warning", !!warning); }
    stats() { return { status: this.status, continuity: { streamId: this.continuity.streamId, lastSequence: this.continuity.lastSequence, recovering: this.continuity.recovering, gapCount: this.continuity.gapCount }, events: this.eventStore.stats(), zones: this.zoneStore.stats(), canvas: this.canvas.stats() }; }
  }

  global.DeltaBigTradesV2 = {
    BigTradeRecordValidator, BigTradeEventStore, ReactionZoneStore,
    ReactionZoneProjection, BigTradesContinuity, BigTradesCanvas,
    BigTradesSettingsController, BigTradesAssessmentController,
    BigTradesContextLink, BigTradesUI, projectContextBars, selectContextForZone, ASSESSMENTS,
  };
})(typeof window !== "undefined" ? window : globalThis);
