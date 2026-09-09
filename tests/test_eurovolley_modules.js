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
      { id: "m", gender: "M", status: "scheduled", warsaw_date: "2026-09-10", warsaw_time: "15:00", start_at: "2026-09-10T13:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Portugalia", code: "POR" }, phase: "Faza grupowa" },
      { id: "k", gender: "K", status: "scheduled", warsaw_date: "2026-09-12", warsaw_time: "15:00", start_at: "2026-09-12T13:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Serbia", code: "SRB" }, phase: "Mecz o 3. miejsce" },
      { id: "live", gender: "M", status: "live", warsaw_date: "2026-09-06", warsaw_time: "13:00", start_at: "2026-09-06T11:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Włochy", code: "ITA" }, phase: "Faza grupowa" },
      { id: "finished", gender: "M", status: "finished", score: "3:1", warsaw_date: "2026-09-05", warsaw_time: "15:00", start_at: "2026-09-05T13:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Czechy", code: "CZE" }, phase: "Faza grupowa" },
      { id: "malformed", gender: "K", status: "scheduled", warsaw_date: "2026-09-20", warsaw_time: "15:00", start_at: "not-a-timestamp", home: { name: "Polska", code: "POL" }, away: { name: "Belgia", code: "BEL" }, phase: "Faza grupowa" }
    ],
    days: [
      { date: "2026-09-10", matches: [{ id: "m", gender: "M", status: "scheduled", warsaw_date: "2026-09-10", warsaw_time: "15:00", start_at: "2026-09-10T13:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Portugalia", code: "POR" }, phase: "Faza grupowa" }] },
      { date: "2026-09-06", matches: [
        { id: "live", gender: "M", status: "live", warsaw_date: "2026-09-06", warsaw_time: "13:00", start_at: "2026-09-06T11:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Włochy", code: "ITA" }, phase: "Faza grupowa" },
        { id: "same-day", gender: "K", status: "scheduled", warsaw_date: "2026-09-06", warsaw_time: "14:30", start_at: "2026-09-06T12:30:00+00:00", home: { name: "Niemcy", code: "GER" }, away: { name: "Belgia", code: "BEL" }, phase: "Faza grupowa" }
      ] },
      { date: "2026-09-05", matches: [{ id: "finished", gender: "M", status: "finished", warsaw_date: "2026-09-05", warsaw_time: "15:00", start_at: "2026-09-05T13:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Czechy", code: "CZE" }, phase: "Faza grupowa" }] }
    ]
  }
};

const fixedNow = Date.parse("2026-09-06T12:00:00+00:00");
const poland = modules.normalizePoland(state, fixedNow);
assert.strictEqual(poland.status, "stale");
assert.strictEqual(poland.refreshStatus, "cached_after_probe_error");
assert.deepStrictEqual(Array.from(poland.rows, row => row.id), ["live", "m", "k"]);
assert.deepStrictEqual(Array.from(poland.rows, row => row.gender), ["M", "M", "K"]);
assert.strictEqual(poland.rows[0].status, "live");
assert.strictEqual(poland.rows[0].time, "13:00");
assert.deepStrictEqual(Array.from(poland.rows, row => row.date), ["2026-09-06", "2026-09-10", "2026-09-12"]);
assert.ok(Array.from(poland.rows).every(row => row.status === "live" || Date.parse(row.startAt) > fixedNow));
assert.ok(!Array.from(poland.rows).some(row => row.id === "finished" || row.id === "malformed"));

const daily = modules.normalizeDaily(state, fixedNow);
assert.strictEqual(daily.selectedDate, "2026-09-06");
assert.deepStrictEqual(Array.from(daily.days, day => day.date), ["2026-09-06"]);
assert.deepStrictEqual(Array.from(daily.days[0].matches, row => row.id), ["live", "same-day"]);
assert.ok(Array.from(daily.days[0].matches).every(row => row.date === daily.selectedDate));
assert.ok(Array.from(daily.days[0].matches).every(row => row.status === "live" || row.status === "scheduled"));
assert.ok(!Array.from(daily.days).some(day => Array.from(day.matches).some(row => row.id === "finished" || row.id === "m")));

const ticker = modules.normalizeTicker(state);
assert.strictEqual(ticker.status, "stale");
assert.strictEqual(ticker.rows.length, 5);
assert.ok(ticker.rows.some(row => row.id === "finished"));
assert.ok(ticker.rows.some(row => row.id === "live"));
assert.strictEqual(ticker.rows.find(row => row.id === "finished").score, "3:1");
assert.ok(!Array.from(poland.rows).some(row => row.id === "finished"));

const appSource = fs.readFileSync(require("path").join(__dirname, "../app/static/app.js"), "utf8");
const tickerSource = appSource.slice(appSource.indexOf("function renderTicker"), appSource.indexOf("// ---- slot runtime adapters"));
assert.ok(appSource.includes("modules.normalizeTicker"));
assert.ok(tickerSource.includes("Brak wyników EuroVolley"));
assert.ok(!tickerSource.includes("recent_results"));
assert.ok(source.includes('"euro-schedule__table"'));
assert.ok(source.includes('"euro-schedule__date"'));

console.log("EuroVolley module contract tests: 2 modules, normalization passed");
