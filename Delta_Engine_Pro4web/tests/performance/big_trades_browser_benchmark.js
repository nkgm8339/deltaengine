"use strict";

const fs = require("fs");
const vm = require("vm");
const { performance } = require("perf_hooks");

globalThis.performance = performance;
const source = fs.readFileSync(process.argv[2], "utf8");
vm.runInThisContext(source, { filename: process.argv[2] });

const { BigTradeEventStore, ReactionZoneStore } = globalThis.DeltaBigTradesV2;
const base = Date.parse("2026-08-12T00:00:00.000Z");
const hex = value => Number(value).toString(16).padStart(64, "0").slice(-64);
const iso = value => new Date(base + value).toISOString();

const events = Array.from({ length: 5000 }, (_, index) => ({
  event_id: `bt2_${hex(index + 1)}`,
  last_time: iso(index),
  marker_time: iso(index),
  marker_price: "100",
  aggregate_quantity: "10",
  fill_count: 1,
  side: index % 2 ? "SELL" : "BUY",
  content_hash: hex(index + 100000),
}));
const interactions = Array.from({ length: 20000 }, (_, index) => ({
  interaction_id: `bti2_${hex(index + 1)}`,
  zone_id: `btz2_${hex((index % 5000) + 1)}`,
  source_event_time: iso(index + 5000),
  ordinal: Math.floor(index / 5000) + 1,
  interaction_type: "RELATION_INSIDE",
  current_relation: "INSIDE",
  content_hash: hex(index + 200000),
}));

function mergeOnce() {
  const eventStore = new BigTradeEventStore(5000);
  const zoneStore = new ReactionZoneStore(5000, 20000);
  const started = performance.now();
  eventStore.merge(events);
  const eventsDone = performance.now();
  zoneStore.mergeInteractions(interactions);
  const finished = performance.now();
  return { eventStore, zoneStore, eventMs: eventsDone - started, interactionMs: finished - eventsDone, elapsedMs: finished - started };
}

// Report steady-state V8 performance after schema/Map hot paths are compiled.
for (let iteration = 0; iteration < 3; iteration += 1) mergeOnce();
const { eventStore, zoneStore, eventMs, interactionMs, elapsedMs } = mergeOnce();

process.stdout.write(JSON.stringify({
  elapsed_ms: elapsedMs,
  event_merge_ms: eventMs,
  interaction_merge_ms: interactionMs,
  warmup_iterations: 3,
  events: eventStore.stats(),
  zones: zoneStore.stats(),
}));
