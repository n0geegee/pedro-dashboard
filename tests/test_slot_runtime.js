"use strict";

const assert = require("assert");
const { create, validateLayout, SLOT_IDS } = require("../app/static/slot-runtime.js");

function moduleDef(id, supportedSlots, dataDep, events, extra) {
  extra = extra || {};
  return Object.assign({
    id,
    contractVersion: 1,
    supportedSlots,
    dataDeps: dataDep ? [dataDep] : [],
    mount(ctx) {
      events.push(["mount", id, ctx.slotId, ctx.generation]);
      if (extra.onMount) extra.onMount(ctx);
      return { id };
    },
    update(ctx, input) {
      events.push(["update", id, ctx.slotId, input && input.value]);
      if (extra.onUpdate) extra.onUpdate(ctx, input);
    },
    unmount(ctx) {
      events.push(["unmount", id, ctx.slotId, ctx.generation]);
      if (extra.onUnmount) extra.onUnmount(ctx);
    }
  }, extra.definition || {});
}

function makeRegistry(events, overrides) {
  const registry = {
    legacy: moduleDef("legacy", SLOT_IDS.slice(), null, events),
    ul: moduleDef("ul", ["UL"], "ul", events),
    ur: moduleDef("ur", ["UR"], "ur", events),
    birdwatch: moduleDef("birdwatch", ["LL"], "ll_tbd", events),
    photos: moduleDef("photos", ["LR"], "media", events)
  };
  return Object.assign(registry, overrides || {});
}

function layout(overrides) {
  return {
    schema_version: 1,
    engine: "slots-v1",
    revision: "test-1",
    slots: Object.assign({
      UL: { module: "ul", enabled: true },
      UR: { module: "ur", enabled: true },
      LL: { module: "birdwatch", enabled: true },
      LR: { module: "photos", enabled: true }
    }, overrides || {})
  };
}

function hosts() {
  return { UL: {}, UR: {}, LL: {}, LR: {} };
}

function testValidLayoutAndValidation() {
  const events = [];
  const registry = makeRegistry(events);
  const normalized = validateLayout(layout(), registry);
  assert.deepStrictEqual(normalized.slots.LL, { module: "birdwatch", enabled: true });
  assert.deepStrictEqual(normalized.slots.LR, { module: "photos", enabled: true });
  assert.throws(
    () => validateLayout(layout({ LL: { module: "photos", enabled: true } }), registry),
    /does not support LL/
  );
  assert.throws(
    () => validateLayout(layout({ UR: { module: "missing", enabled: true } }), registry),
    /unknown module missing/
  );
  assert.throws(
    () => validateLayout(Object.assign({}, layout(), { schema_version: 2 }), registry),
    /schema_version/
  );
  assert.deepStrictEqual(
    validateLayout(layout({ LL: { module: "ignored", enabled: false } }), registry).slots.LL,
    { module: "legacy", enabled: false }
  );
}

function testLifecycleAndFutureLLReplacement() {
  const events = [];
  let oldGenerationIsCurrent;
  const oldBirdwatch = moduleDef("birdwatch", ["LL"], "ll_tbd", events, {
    onMount(ctx) {
      if (ctx.slotId === "LL") oldGenerationIsCurrent = ctx.isCurrent;
    }
  });
  const replacement = moduleDef("volleyball-grid", ["LL"], "volleyball", events);
  const registry = makeRegistry(events, { birdwatch: oldBirdwatch, "volleyball-grid": replacement });
  const runtime = create({
    layout: layout(),
    registry,
    hostResolver: slotId => hostsMap[slotId],
    reportError: (slot, id, err) => { throw err; }
  });
  const hostsMap = hosts();
  const state = {
    widgets: {
      ul: { value: "ul-1" },
      ur: { value: "ur-1" },
      ll_tbd: { value: "bird-1" },
      media: { value: "media-1" },
      volleyball: { value: "vb-1" }
    }
  };

  runtime.update(state);
  runtime.update(state);
  assert.strictEqual(events.filter(x => x[0] === "mount" && x[1] === "birdwatch").length, 1);
  assert.strictEqual(events.filter(x => x[0] === "update" && x[1] === "birdwatch").length, 2);

  runtime.setLayout(layout({
    LL: { module: "volleyball-grid", enabled: true }
  }));
  runtime.update(state);
  assert.strictEqual(runtime.getMounted("LL").moduleId, "volleyball-grid");
  assert.strictEqual(oldGenerationIsCurrent(), false);
  const llEvents = events.filter(x => x[2] === "LL").map(x => x[0] + ":" + x[1]);
  assert.deepStrictEqual(llEvents, [
    "mount:birdwatch", "update:birdwatch", "update:birdwatch",
    "unmount:birdwatch", "mount:volleyball-grid", "update:volleyball-grid"
  ]);
}

function testSiblingIsolationOnError() {
  const events = [];
  const errors = [];
  const bad = moduleDef("bad", ["UR"], "ur", events, {
    onUpdate() { throw new Error("boom"); }
  });
  const registry = makeRegistry(events, { bad });
  const runtime = create({
    layout: layout({ UR: { module: "bad", enabled: true } }),
    registry,
    hostResolver: slotId => isolationHosts[slotId],
    reportError: (slot, id, error) => errors.push([slot, id, error.message]),
    renderError: () => {}
  });
  const isolationHosts = hosts();
  runtime.update({ widgets: {
    ul: { value: "ul" }, ur: { value: "ur" },
    ll_tbd: { value: "ll" }, media: { value: "media" }
  }});
  assert.ok(events.some(x => x[0] === "update" && x[1] === "ul"));
  assert.ok(events.some(x => x[0] === "update" && x[1] === "birdwatch"));
  assert.deepStrictEqual(errors, [["UR", "bad", "boom"]]);
}

function testDisabledSlotUsesFallback() {
  const events = [];
  const registry = makeRegistry(events);
  const runtimeHosts = hosts();
  const runtime = create({
    layout: layout({ LL: { module: "future-module-not-yet-built", enabled: false } }),
    registry,
    hostResolver: slotId => runtimeHosts[slotId],
    reportError: (slot, id, error) => { throw error; }
  });
  runtime.update({ widgets: {} });
  assert.strictEqual(runtime.getMounted("LL").moduleId, "legacy");
  assert.ok(events.some(x => x[0] === "update" && x[1] === "legacy" && x[2] === "LL"));
}

testValidLayoutAndValidation();
testLifecycleAndFutureLLReplacement();
testSiblingIsolationOnError();
testDisabledSlotUsesFallback();
console.log("slot runtime contract tests: 4 passed");
