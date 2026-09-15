#!/usr/bin/env node
"use strict";

const assert = require("assert");
const rotation = require("../app/static/display-rotation.js");

const control = {
  enabled: true,
  dashboardMs: 60 * 1000,
  slideshowMs: 300 * 1000,
  cycleStartedAtMs: 0,
};

function check(now, mode, nextAtMs) {
  const result = rotation.plan(control, now);
  assert.strictEqual(result.mode, mode, `mode at ${now}`);
  assert.strictEqual(result.nextAtMs, nextAtMs, `nextAtMs at ${now}`);
}

check(0, "dashboard", 60_000);
check(59_999, "dashboard", 60_000);
check(60_000, "slideshow", 360_000);
check(359_999, "slideshow", 360_000);
check(360_000, "dashboard", 420_000);
check(420_000 + 1, "slideshow", 720_000);

const disabled = rotation.plan({ ...control, enabled: false }, 1234);
assert.deepStrictEqual(disabled, {
  mode: "dashboard",
  nextAtMs: 61_234,
  reason: "disabled",
});

const future = rotation.plan(control, -1);
assert.strictEqual(future.mode, "dashboard");
assert.strictEqual(future.reason, "not_started");

console.log("display rotation contract tests: 8 passed");
