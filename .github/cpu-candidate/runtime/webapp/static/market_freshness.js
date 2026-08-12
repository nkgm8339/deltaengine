(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.DeltaMarketFreshness = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const STATES = Object.freeze({
    CONNECTING: "CONNECTING",
    SYNCING: "SYNCING",
    LIVE: "LIVE",
    STALE: "STALE",
    RECONNECTING: "RECONNECTING",
    REPLAY: "REPLAY",
  });

  function monotonicNow() {
    if (typeof performance !== "undefined" && typeof performance.now === "function") {
      return performance.now();
    }
    return Date.now();
  }

  class MarketHeartbeatGuard {
    constructor(options) {
      const config = options || {};
      this.now = typeof config.now === "function" ? config.now : monotonicNow;
      this.wallNow = typeof config.wallNow === "function" ? config.wallNow : Date.now;
      this.maxTransportAgeMs = Number(config.maxTransportAgeMs ?? 2000);
      this.maxSourceAgeMs = Number(config.maxSourceAgeMs ?? 5000);
      this.futureToleranceMs = Number(config.futureToleranceMs ?? 5000);
      this.onStateChange = typeof config.onStateChange === "function" ? config.onStateChange : function () {};
      this.state = STATES.CONNECTING;
      this.reason = "SOCKET_CONNECTING";
      this.stateSince = this.now();
      this.mode = null;
      this.heartbeatIntervalMs = null;
      this.heartbeatTimeoutMs = null;
      this.lastHeartbeatAt = null;
      this.lastHeartbeatSequence = null;
      this.lastAcceptedAt = null;
      this.transportAgeMs = null;
      this.sourceAgeMs = null;
      this.totalAgeMs = null;
    }

    snapshot() {
      return {
        state: this.state,
        reason: this.reason,
        fresh: this.state === STATES.LIVE,
        mode: this.mode,
        stateSince: this.stateSince,
        heartbeatIntervalMs: this.heartbeatIntervalMs,
        heartbeatTimeoutMs: this.heartbeatTimeoutMs,
        lastHeartbeatAt: this.lastHeartbeatAt,
        lastHeartbeatSequence: this.lastHeartbeatSequence,
        heartbeatAgeMs: this.lastHeartbeatAt === null ? null : Math.max(0, this.now() - this.lastHeartbeatAt),
        lastAcceptedAt: this.lastAcceptedAt,
        transportAgeMs: this.transportAgeMs,
        sourceAgeMs: this.sourceAgeMs,
        totalAgeMs: this.totalAgeMs,
      };
    }

    _setState(state, reason) {
      const changed = this.state !== state || this.reason !== reason;
      this.state = state;
      this.reason = reason;
      if (changed) {
        this.stateSince = this.now();
        this.onStateChange(this.snapshot());
      }
    }

    _fail(reason) {
      this._setState(STATES.STALE, reason);
      return {accepted: false, reason, snapshot: this.snapshot()};
    }

    _reject(reason) {
      return {accepted: false, reason, snapshot: this.snapshot()};
    }

    socketConnecting() {
      this.mode = null;
      this.heartbeatIntervalMs = null;
      this.heartbeatTimeoutMs = null;
      this.lastHeartbeatAt = null;
      this.lastHeartbeatSequence = null;
      this.lastAcceptedAt = null;
      this._setState(STATES.CONNECTING, "SOCKET_CONNECTING");
    }

    socketOpen() {
      this.mode = null;
      this.heartbeatIntervalMs = null;
      this.heartbeatTimeoutMs = null;
      this.lastHeartbeatAt = null;
      this.lastHeartbeatSequence = null;
      this.lastAcceptedAt = null;
      this._setState(STATES.SYNCING, "WAITING_FOR_LIVE_HEARTBEAT");
    }

    socketClosed() {
      this.lastHeartbeatAt = null;
      this.lastHeartbeatSequence = null;
      this.lastAcceptedAt = null;
      this._setState(STATES.RECONNECTING, "SOCKET_CLOSED");
    }

    configureHello(candidate) {
      const hello = candidate || {};
      const mode = hello.mode;
      if (mode === "replay") {
        this.mode = "replay";
        this.heartbeatIntervalMs = null;
        this.heartbeatTimeoutMs = null;
        this.lastHeartbeatAt = null;
        this.lastHeartbeatSequence = null;
        this.lastAcceptedAt = null;
        this._setState(STATES.REPLAY, "REPLAY_MODE");
        return {accepted: true, reason: "REPLAY_MODE", snapshot: this.snapshot()};
      }
      const intervalMs = Number(hello.intervalMs);
      const timeoutMs = Number(hello.timeoutMs);
      if (
        mode !== "live"
        || !Number.isInteger(intervalMs)
        || intervalMs <= 0
        || !Number.isInteger(timeoutMs)
        || timeoutMs < intervalMs * 3
      ) {
        return this._fail("HEARTBEAT_CONFIG_INVALID");
      }
      this.mode = "live";
      this.heartbeatIntervalMs = intervalMs;
      this.heartbeatTimeoutMs = timeoutMs;
      this.lastHeartbeatAt = null;
      this.lastHeartbeatSequence = null;
      this.lastAcceptedAt = null;
      this._setState(STATES.SYNCING, "WAITING_FOR_LIVE_HEARTBEAT");
      return {accepted: true, reason: "LIVE_HEARTBEAT_CONFIGURED", snapshot: this.snapshot()};
    }

    acceptHeartbeat(candidate) {
      const heartbeat = candidate || {};
      if (this.mode === "replay") return this._reject("HEARTBEAT_MODE_MISMATCH");
      if (this.mode !== "live") return this._reject("HEARTBEAT_BEFORE_HELLO");
      if (heartbeat.mode !== "live") return this._reject("HEARTBEAT_MODE_MISMATCH");
      const sequence = Number(heartbeat.sequence);
      if (
        !Number.isInteger(sequence)
        || sequence <= 0
        || (this.lastHeartbeatSequence !== null && sequence <= this.lastHeartbeatSequence)
        || typeof heartbeat.upstreamFresh !== "boolean"
        || typeof heartbeat.pipelineAlive !== "boolean"
      ) {
        return this._fail("HEARTBEAT_METADATA_INVALID");
      }
      this.lastHeartbeatAt = this.now();
      this.lastHeartbeatSequence = sequence;
      if (!heartbeat.pipelineAlive) return this._fail("PIPELINE_NOT_ALIVE");
      if (!heartbeat.upstreamFresh) return this._fail("UPSTREAM_NOT_FRESH");
      if (this.state === STATES.LIVE) {
        this._setState(STATES.LIVE, "FRESH_HEARTBEAT");
      } else {
        this._setState(STATES.SYNCING, "WAITING_FOR_FRESH_TICK");
      }
      return {accepted: true, reason: "FRESH_HEARTBEAT", snapshot: this.snapshot()};
    }

    acceptTick(candidate) {
      if (this.mode !== "live") return this._reject("LIVE_TICK_MODE_MISMATCH");
      if (this.state !== STATES.LIVE && !(this.state === STATES.SYNCING && this.reason === "WAITING_FOR_FRESH_TICK")) {
        return this._reject("WAITING_FOR_FRESH_HEARTBEAT");
      }
      if (this.lastHeartbeatAt === null || this.now() - this.lastHeartbeatAt > this.heartbeatTimeoutMs) {
        return this._fail("HEARTBEAT_TIMEOUT");
      }
      const tick = candidate || {};
      const now = this.wallNow();
      const publishedTime = tick.publishedTime;
      const rawSourceAge = tick.sourceAgeMs;
      const publishedAt = typeof publishedTime === "string" && publishedTime.trim() !== ""
        ? Date.parse(publishedTime)
        : NaN;
      const sourceAge = rawSourceAge === null || rawSourceAge === "" || typeof rawSourceAge === "boolean"
        ? NaN
        : Number(rawSourceAge);
      if (!Number.isFinite(publishedAt) || !Number.isFinite(sourceAge) || sourceAge < 0) {
        return this._fail("TICK_FRESHNESS_METADATA_INVALID");
      }
      const transportAge = now - publishedAt;
      if (transportAge < -this.futureToleranceMs) return this._fail("TICK_PUBLISHED_IN_FUTURE");
      if (transportAge > this.maxTransportAgeMs) return this._fail("TICK_TRANSPORT_STALE");
      if (sourceAge > this.maxSourceAgeMs) return this._fail("TICK_SOURCE_STALE");

      this.lastAcceptedAt = now;
      this.transportAgeMs = Math.max(0, Math.round(transportAge));
      this.sourceAgeMs = Math.round(sourceAge);
      this.totalAgeMs = this.transportAgeMs + this.sourceAgeMs;
      this._setState(STATES.LIVE, "FRESH_TICK");
      return {accepted: true, reason: "FRESH_TICK", snapshot: this.snapshot()};
    }

    check() {
      if (this.mode === "replay" || this.state === STATES.REPLAY) {
        return {accepted: false, reason: this.reason, snapshot: this.snapshot()};
      }
      const now = this.now();
      if (
        this.mode === "live"
        && this.heartbeatTimeoutMs !== null
        && (
          (this.lastHeartbeatAt === null && now - this.stateSince > this.heartbeatTimeoutMs)
          || (this.lastHeartbeatAt !== null && now - this.lastHeartbeatAt > this.heartbeatTimeoutMs)
        )
      ) {
        return this._fail("HEARTBEAT_TIMEOUT");
      }
      return {accepted: this.state === STATES.LIVE, reason: this.reason, snapshot: this.snapshot()};
    }

    isFresh() {
      return this.state === STATES.LIVE;
    }
  }

  class SpotEventFreshnessGuard {
    constructor(options) {
      const config = options || {};
      this.now = typeof config.now === "function" ? config.now : Date.now;
      this.staleAfterMs = Number(config.staleAfterMs ?? 5000);
      this.syncTimeoutMs = Number(config.syncTimeoutMs ?? 8000);
      this.maxTransportAgeMs = Number(config.maxTransportAgeMs ?? 3000);
      this.maxSourceAgeMs = Number(config.maxSourceAgeMs ?? 5000);
      this.futureToleranceMs = Number(config.futureToleranceMs ?? 5000);
      this.onStateChange = typeof config.onStateChange === "function" ? config.onStateChange : function () {};
      this.state = STATES.CONNECTING;
      this.reason = "SOCKET_CONNECTING";
      this.stateSince = this.now();
      this.lastAcceptedAt = null;
      this.transportAgeMs = null;
      this.sourceAgeMs = null;
      this.totalAgeMs = null;
    }

    snapshot() {
      return {
        state: this.state,
        reason: this.reason,
        fresh: this.state === STATES.LIVE,
        stateSince: this.stateSince,
        lastAcceptedAt: this.lastAcceptedAt,
        transportAgeMs: this.transportAgeMs,
        sourceAgeMs: this.sourceAgeMs,
        totalAgeMs: this.totalAgeMs,
      };
    }

    _setState(state, reason) {
      const changed = this.state !== state || this.reason !== reason;
      this.state = state;
      this.reason = reason;
      if (changed) {
        this.stateSince = this.now();
        this.onStateChange(this.snapshot());
      }
    }

    _fail(reason) {
      this._setState(STATES.STALE, reason);
      return {accepted: false, reason, snapshot: this.snapshot()};
    }

    socketConnecting() {
      this._setState(STATES.CONNECTING, "SOCKET_CONNECTING");
    }

    socketOpen() {
      this.lastAcceptedAt = null;
      this._setState(STATES.SYNCING, "WAITING_FOR_FRESH_EVENT");
    }

    socketClosed() {
      this.lastAcceptedAt = null;
      this._setState(STATES.RECONNECTING, "SOCKET_CLOSED");
    }

    acceptTick(candidate) {
      const tick = candidate || {};
      const now = this.now();
      const publishedTime = tick.publishedTime;
      const rawSourceAge = tick.sourceAgeMs;
      const publishedAt = typeof publishedTime === "string" && publishedTime.trim() !== ""
        ? Date.parse(publishedTime)
        : NaN;
      const sourceAge = rawSourceAge === null || rawSourceAge === "" || typeof rawSourceAge === "boolean"
        ? NaN
        : Number(rawSourceAge);
      if (!Number.isFinite(publishedAt) || !Number.isFinite(sourceAge) || sourceAge < 0) {
        return this._fail("EVENT_FRESHNESS_METADATA_INVALID");
      }
      const transportAge = now - publishedAt;
      if (transportAge < -this.futureToleranceMs) return this._fail("EVENT_PUBLISHED_IN_FUTURE");
      if (transportAge > this.maxTransportAgeMs) return this._fail("EVENT_TRANSPORT_STALE");
      if (sourceAge > this.maxSourceAgeMs) return this._fail("EVENT_SOURCE_STALE");

      this.lastAcceptedAt = now;
      this.transportAgeMs = Math.max(0, Math.round(transportAge));
      this.sourceAgeMs = Math.round(sourceAge);
      this.totalAgeMs = this.transportAgeMs + this.sourceAgeMs;
      this._setState(STATES.LIVE, "FRESH_EVENT");
      return {accepted: true, reason: "FRESH_EVENT", snapshot: this.snapshot()};
    }

    check() {
      const now = this.now();
      if (this.state === STATES.LIVE && this.lastAcceptedAt !== null && now - this.lastAcceptedAt > this.staleAfterMs) {
        return this._fail("EVENT_TIMEOUT");
      }
      if (this.state === STATES.SYNCING && now - this.stateSince > this.syncTimeoutMs) {
        return this._fail("EVENT_SYNC_TIMEOUT");
      }
      return {accepted: this.state === STATES.LIVE, reason: this.reason, snapshot: this.snapshot()};
    }

    isFresh() {
      return this.state === STATES.LIVE;
    }
  }

  return {
    MarketHeartbeatGuard,
    SpotEventFreshnessGuard,
    MarketFreshnessGuard: SpotEventFreshnessGuard,
    STATES,
  };
});
