/* Pedro Dashboard — pure fullscreen-rotation phase planner. */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PedroDisplayRotation = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEFAULT_DASHBOARD_MS = 60 * 1000;
  var DEFAULT_SLIDESHOW_MS = 300 * 1000;

  function positiveNumber(value, fallback) {
    var n = Number(value);
    return isFinite(n) && n > 0 ? n : fallback;
  }

  function plan(control, nowMs) {
    var now = Number(nowMs);
    if (!isFinite(now)) now = Date.now();
    var dashboardMs = positiveNumber(control && control.dashboardMs, DEFAULT_DASHBOARD_MS);
    var slideshowMs = positiveNumber(control && control.slideshowMs, DEFAULT_SLIDESHOW_MS);
    if (!control || control.enabled !== true) {
      return { mode: "dashboard", nextAtMs: now + dashboardMs, reason: "disabled" };
    }

    var cycleStartedAtMs = Number(control.cycleStartedAtMs);
    if (!isFinite(cycleStartedAtMs) || now < cycleStartedAtMs) {
      return { mode: "dashboard", nextAtMs: now + dashboardMs, reason: "not_started" };
    }

    var cycleMs = dashboardMs + slideshowMs;
    var phase = (now - cycleStartedAtMs) % cycleMs;
    var inDashboard = phase < dashboardMs;
    var remaining = inDashboard ? dashboardMs - phase : cycleMs - phase;
    return {
      mode: inDashboard ? "dashboard" : "slideshow",
      nextAtMs: now + Math.max(1, remaining),
      reason: "cycle"
    };
  }

  return {
    DEFAULT_DASHBOARD_MS: DEFAULT_DASHBOARD_MS,
    DEFAULT_SLIDESHOW_MS: DEFAULT_SLIDESHOW_MS,
    plan: plan
  };
}));
