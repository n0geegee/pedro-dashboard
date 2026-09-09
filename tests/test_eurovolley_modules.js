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
    current_competition_id: "eurovolley-2026-men",
    timezone: "Europe/Warsaw",
    freshness: { refresh_status: "cached_after_probe_error" },
    poland_matches: [
      { id: "m", gender: "M", competition_id: "eurovolley-2026-men", status: "scheduled", warsaw_date: "2026-09-10", warsaw_time: "15:00", start_at: "2026-09-10T13:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Portugalia", code: "POR" }, phase: "Faza grupowa" },
      { id: "k", gender: "K", competition_id: "eurovolley-2026-women", status: "scheduled", warsaw_date: "2026-09-12", warsaw_time: "15:00", start_at: "2026-09-12T13:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Serbia", code: "SRB" }, phase: "Mecz o 3. miejsce" },
      { id: "live", gender: "M", competition_id: "eurovolley-2026-men", status: "live", warsaw_date: "2026-09-06", warsaw_time: "13:00", start_at: "2026-09-06T11:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Włochy", code: "ITA" }, phase: "Faza grupowa" },
      { id: "finished", gender: "K", competition_id: "eurovolley-2026-women", status: "finished", score: "3:1", warsaw_date: "2026-09-05", warsaw_time: "15:00", start_at: "2026-09-05T13:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Czechy", code: "CZE" }, phase: "Faza grupowa" },
      { id: "finished-men", gender: "M", competition_id: "eurovolley-2026-men", status: "finished", score: "3:2", warsaw_date: "2026-09-04", warsaw_time: "15:00", start_at: "2026-09-04T13:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Bułgaria", code: "BUL" }, phase: "Faza grupowa" },
      { id: "malformed", gender: "K", competition_id: "eurovolley-2026-women", status: "scheduled", warsaw_date: "2026-09-20", warsaw_time: "15:00", start_at: "not-a-timestamp", home: { name: "Polska", code: "POL" }, away: { name: "Belgia", code: "BEL" }, phase: "Faza grupowa" }
    ],
    days: [
      { date: "2026-09-10", matches: [{ id: "m", gender: "M", status: "scheduled", warsaw_date: "2026-09-10", warsaw_time: "15:00", start_at: "2026-09-10T13:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Portugalia", code: "POR" }, phase: "Faza grupowa" }] },
      { date: "2026-09-06", matches: [
        { id: "finished-today", gender: "M", status: "finished", score: "3:0", warsaw_date: "2026-09-06", warsaw_time: "10:00", start_at: "2026-09-06T08:00:00+00:00", home: { name: "Bułgaria", code: "BUL" }, away: { name: "Dania", code: "DEN" }, phase: "Faza grupowa" },
        { id: "live", gender: "M", status: "live", warsaw_date: "2026-09-06", warsaw_time: "13:00", start_at: "2026-09-06T11:00:00+00:00", home: { name: "Polska", code: "POL" }, away: { name: "Włochy", code: "ITA" }, phase: "Faza grupowa" },
        { id: "same-day", gender: "K", status: "scheduled", warsaw_date: "2026-09-06", warsaw_time: "14:30", start_at: "2026-09-06T12:30:00+00:00", home: { name: "Niemcy", code: "GER" }, away: { name: "Belgia", code: "BEL" }, phase: "Faza grupowa" },
        { id: "same-time", gender: "M", status: "scheduled", warsaw_date: "2026-09-06", warsaw_time: "14:30", start_at: "2026-09-06T12:30:00+00:00", home: { name: "Francja", code: "FRA" }, away: { name: "Szwajcaria", code: "SUI" }, phase: "Faza grupowa" }
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
assert.deepStrictEqual(Array.from(daily.days[0].matches, row => row.id), ["finished-today", "live", "same-day", "same-time"]);
assert.ok(Array.from(daily.days[0].matches).every(row => row.date === daily.selectedDate));
assert.ok(daily.days[0].matches.some(row => row.id === "finished-today"));
assert.strictEqual(daily.days[0].matches.filter(row => row.time === "14:30").length, 2);
assert.ok(!Array.from(daily.days).some(day => Array.from(day.matches).some(row => row.id === "m")));

const ticker = modules.normalizeTicker(state);
assert.strictEqual(ticker.status, "stale");
assert.strictEqual(ticker.rows.length, 3);
assert.ok(ticker.rows.some(row => row.id === "finished-men"));
assert.ok(ticker.rows.some(row => row.id === "live"));
assert.strictEqual(ticker.rows.find(row => row.id === "finished-men").score, "3:2");
assert.ok(!ticker.rows.some(row => row.id === "finished"));
assert.ok(!ticker.rows.some(row => row.gender === "K"));
assert.ok(!Array.from(poland.rows).some(row => row.id === "finished"));

const fallbackState = {
  status: "ok",
  data: {
    selected_date: state.data.selected_date,
    current_competition_id: state.data.current_competition_id,
    matches: [
      state.data.poland_matches.find(row => row.id === "finished-men"),
      { id: "non-poland", gender: "M", competition_id: "eurovolley-2026-men", status: "finished", score: "3:0", warsaw_date: "2026-09-04", warsaw_time: "15:00", start_at: "2026-09-04T13:00:00+00:00", home: { name: "Bułgaria", code: "BUL" }, away: { name: "Serbia", code: "SRB" }, phase: "Faza grupowa" }
    ]
  }
};
assert.deepStrictEqual(
  Array.from(modules.normalizeTicker(fallbackState).rows, row => row.id),
  ["finished-men"]
);

const appSource = fs.readFileSync(require("path").join(__dirname, "../app/static/app.js"), "utf8");
const tickerSource = appSource.slice(appSource.indexOf("function renderTicker"), appSource.indexOf("// ---- slot runtime adapters"));
assert.ok(appSource.includes("modules.normalizeTicker"));
assert.ok(tickerSource.includes("slice(0, 4)"));
assert.ok(tickerSource.includes("track.innerHTML = items.length"));
assert.ok(appSource.includes("function tickerDate"));
assert.ok(appSource.includes("m.date || m.warsaw_date"));
assert.ok(!tickerSource.includes("Brak wyników EuroVolley"));
assert.ok(!tickerSource.includes("recent_results"));
const formatterSandbox = { teamName: team => team.name };
const formatterStart = appSource.indexOf("function tickerDate");
const formatterEnd = appSource.indexOf("function euroVolleyTickerRows");
vm.runInNewContext(appSource.slice(formatterStart, formatterEnd), formatterSandbox);
assert.strictEqual(
  formatterSandbox.resultTickerText({
    home: { name: "Polska" },
    away: { name: "Włochy" },
    score: "3:1",
    date: "2026-09-04",
    _group: "M"
  }),
  "Polska 3:1 Włochy (M · 04.09)"
);
assert.ok(source.includes('"euro-schedule__table"'));
assert.ok(source.includes('"euro-schedule__date"'));

console.log("EuroVolley module contract tests: 2 modules, normalization passed");
