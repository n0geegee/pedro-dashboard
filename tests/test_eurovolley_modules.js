"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(require("path").join(__dirname, "../app/static/eurovolley-schedule-modules.js"), "utf8");
const sandbox = { console, globalThis: {} };
vm.runInNewContext(source, sandbox, { filename: "eurovolley-schedule-modules.js" });
const modules = sandbox.globalThis.PedroEuroScheduleModules;
assert.ok(modules);

assert.strictEqual(modules.polandEuroSchedule.id, "poland-euro-schedule");
assert.strictEqual(modules.polandEuroSchedule.contractVersion, 1);
assert.deepStrictEqual(Array.from(modules.polandEuroSchedule.supportedSlots), ["UL"]);
assert.deepStrictEqual(Array.from(modules.polandEuroSchedule.dataDeps), ["eurovolley"]);
assert.strictEqual(modules.euroDailySchedule.id, "euro-daily-schedule");
assert.deepStrictEqual(Array.from(modules.euroDailySchedule.supportedSlots), ["LL"]);
assert.deepStrictEqual(Array.from(modules.euroDailySchedule.dataDeps), ["eurovolley"]);

const state = {
  status: "stale",
  updated_at: "2026-09-06T12:00:00+00:00",
  data: {
    selected_date: "2026-09-06",
    timezone: "Europe/Warsaw",
    freshness: { refresh_status: "cached_after_probe_error" },
    poland_matches: [
      { id: "m", gender: "M", warsaw_date: "2026-09-10", warsaw_time: "15:00", home: { name: "Polska", code: "POL" }, away: { name: "Portugalia", code: "POR" }, phase: "Faza grupowa" },
      { id: "k", gender: "K", warsaw_date: "2026-09-06", warsaw_time: "15:00", home: { name: "Polska", code: "POL" }, away: { name: "Serbia", code: "SRB" }, phase: "Mecz o 3. miejsce" }
    ],
    days: [
      { date: "2026-09-10", matches: [{ id: "m", gender: "M", warsaw_date: "2026-09-10", warsaw_time: "15:00", home: { name: "Polska", code: "POL" }, away: { name: "Portugalia", code: "POR" }, phase: "Faza grupowa" }] },
      { date: "2026-09-06", matches: [{ id: "k", gender: "K", warsaw_date: "2026-09-06", warsaw_time: "15:00", home: { name: "Polska", code: "POL" }, away: { name: "Serbia", code: "SRB" }, phase: "Mecz o 3. miejsce" }] }
    ]
  }
};

const poland = modules.normalizePoland(state);
assert.strictEqual(poland.status, "stale");
assert.strictEqual(poland.refreshStatus, "cached_after_probe_error");
assert.deepStrictEqual(Array.from(poland.rows, row => row.gender), ["K", "M"]);
assert.strictEqual(poland.rows[0].time, "15:00");

const daily = modules.normalizeDaily(state);
assert.deepStrictEqual(Array.from(daily.days, day => day.date), ["2026-09-10", "2026-09-06"]);
assert.strictEqual(daily.days[0].matches[0].gender, "M");
assert.strictEqual(daily.days[1].matches[0].gender, "K");

console.log("EuroVolley module contract tests: 2 modules, normalization passed");
