/* Pedro Dashboard — HERMES three-zone media dashboard
 * Vanilla JS, no build. Polls /api/state every few seconds; renders each
 * card from its widget data. Robust to missing/malformed JSON.
 */
(function () {
  "use strict";

  // REFRESH_MS is aligned with photos-rotator.sh (slide_seconds, default
  // 5s) so the kiosk loop picks up exactly one new image per poll. With
  // the previous 6s cadence, every 5-6 cycles the loop would skip an
  // image because the rotator had already advanced by two slots between
  // two polls. 5s keeps the kiosk in lockstep with the rotator.
  var REFRESH_MS = 3000;
  var STATE_URL = "/api/state";
  var HEALTH_URL = "/api/health";

  // Replaceable center/right slots. The JSON file is the active assignment;
  // this copy keeps the kiosk usable if a static asset is temporarily stale
  // or unavailable during a restart.
  var SLOT_LAYOUT_URL = "/static/slot-layout.json";
  var SLOT_LAYOUT_FALLBACK = {
    schema_version: 1,
    engine: "slots-v1",
    revision: "fallback-eurovolley-1",
    slots: {
      UL: { module: "poland-euro-schedule", enabled: true },
      UR: { module: "polsat-status", enabled: true },
      LL: { module: "euro-daily-schedule", enabled: true },
      LR: { module: "photos", enabled: true }
    }
  };
  var slotRuntime = null;
  var slotRuntimePromise = null;

  // Passive room-display rotation: show the dashboard briefly, then let the
  // LR Google Photos slideshow take over the whole kiosk screen for a longer
  // calm-view window. The Chrome window is already in kiosk mode, so this is a
  // full-viewport dashboard overlay rather than a browser Fullscreen API call.
  var ROTATION_DEFAULT_DASHBOARD_MS = 60 * 1000;
  var ROTATION_DEFAULT_SLIDESHOW_MS = 300 * 1000;
  var rotationDashboardMs = readDurationParam("dashboardSeconds", ROTATION_DEFAULT_DASHBOARD_MS);
  var rotationSlideshowMs = readDurationParam("slideshowSeconds", ROTATION_DEFAULT_SLIDESHOW_MS);
  var rotationEnabled = readRotationEnabled();
  var rotationState = {
    mode: "dashboard",
    switchAt: Date.now() + rotationDashboardMs
  };

  // ---- helpers ----------------------------------------------------------

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function setText(el, txt) { if (el) el.textContent = (txt == null) ? "" : String(txt); }

  function queryParam(name) {
    try { return new URLSearchParams(window.location.search || "").get(name); }
    catch (e) { return null; }
  }

  function readDurationParam(name, fallbackMs) {
    var raw = queryParam(name);
    if (raw == null || raw === "") return fallbackMs;
    var n = Number(raw);
    if (!isFinite(n) || n <= 0) return fallbackMs;
    // Hard cap at 24h so a typo cannot park the room screen forever.
    return Math.min(Math.round(n * 1000), 24 * 60 * 60 * 1000);
  }

  function readRotationEnabled() {
    var raw = (queryParam("rotation") || queryParam("slideshowRotation") || "off").toLowerCase();
    return !(raw === "0" || raw === "off" || raw === "false" || raw === "dashboard");
  }
  function el(tag, attrs, html) {
    var n = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "class") n.className = attrs[k];
        else if (k === "text") n.textContent = attrs[k];
        else if (k.indexOf("on") === 0 && typeof attrs[k] === "function") n.addEventListener(k.substring(2), attrs[k]);
        else n.setAttribute(k, attrs[k]);
      });
    }
    if (html != null) n.innerHTML = html;
    return n;
  }
  function clear(node) { while (node && node.firstChild) node.removeChild(node.firstChild); }

  // Hermes Oracle skin list. "oracle" is the dark-fantasy/sci-fi theme
  // added 2026-06-16; the other names are the v1.1 seasonal skins.
  // Use Object.create(null) so prototype keys (e.g. "constructor",
  // "toString") cannot accidentally pass the allow-list check via
  // ?skin=constructor.
  var ALLOWED_SKINS = Object.create(null);
  ALLOWED_SKINS.default = true;
  ALLOWED_SKINS.winter = true;
  ALLOWED_SKINS.spring = true;
  ALLOWED_SKINS.summer = true;
  ALLOWED_SKINS.autumn = true;
  ALLOWED_SKINS.oracle = true;

  function isAllowedSkin(name) {
    return Object.prototype.hasOwnProperty.call(ALLOWED_SKINS, name);
  }

  function applySkin(widget) {
    var data = (widget && widget.data) || {};
    var skin = data.skin || data.season || "default";
    if (!isAllowedSkin(skin)) skin = "default";
    document.body.setAttribute("data-skin", skin);
    document.body.setAttribute("data-skin-mode", data.mode || "auto");
    document.body.setAttribute("data-skin-label", data.label || skin);
  }

  // ?skin=oracle|summer|... override (URL-param wins over state for
  // quick previews). URL param persists in localStorage ONLY for the
  // current browser session (sessionStorage), so a kiosk restart or a
  // set-skin.py change is not silently masked on the next reload.
  // Explicit "auto" or "default" in the URL clears the override.
  function applyUrlSkinOverride() {
    try {
      var params = new URLSearchParams(window.location.search || "");
      var qs = params.get("skin");
      if (qs && isAllowedSkin(qs)) {
        try { window.sessionStorage.setItem("pedro.skin.override", qs); } catch (e) {}
        document.body.setAttribute("data-skin", qs);
        return qs;
      }
      if (qs && (qs === "auto" || qs === "default" || qs === "clear")) {
        try { window.sessionStorage.removeItem("pedro.skin.override"); } catch (e) {}
        return null;
      }
      var saved = null;
      try { saved = window.sessionStorage.getItem("pedro.skin.override"); } catch (e) { saved = null; }
      if (saved && isAllowedSkin(saved)) {
        document.body.setAttribute("data-skin", saved);
        return saved;
      }
    } catch (e) {}
    return null;
  }

  function emptyMsg(node, msg) {
    clear(node);
    var p = el("p", { class: "muted" });
    p.textContent = msg || "Brak danych.";
    node.appendChild(p);
  }

  function publicErrorText(err) {
    if (!err) return "nieznany";
    if (typeof err === "string") return err;
    if (typeof err === "object") return err.message_public || err.message || err.code || JSON.stringify(err);
    return String(err);
  }

  function errorMsg(node, err) {
    clear(node);
    var p = el("p", { class: "muted" });
    p.style.color = "var(--red)";
    p.textContent = "Błąd: " + publicErrorText(err);
    node.appendChild(p);
  }

  // ---- weather ----------------------------------------------------------

  function wxIconSVG(condition) {
    var c = (condition || "").toLowerCase();
    if (c.indexOf("burz") >= 0) {
      return '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        + '<defs><linearGradient id="wg1" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#dfe7f2"/><stop offset="1" stop-color="#8a96a8"/></linearGradient></defs>'
        + '<ellipse cx="34" cy="36" rx="18" ry="11" fill="url(#wg1)"/>'
        + '<ellipse cx="24" cy="32" rx="14" ry="10" fill="#cdd5e0"/>'
        + '<path d="M30 42 L26 50 L32 50 L28 58 L40 46 L34 46 L38 42 Z" fill="#facc15" stroke="#a07a00" stroke-width="0.5"/>'
        + '</svg>';
    }
    if (c.indexOf("deszcz") >= 0 || c.indexOf("opad") >= 0 || c.indexOf("rain") >= 0) {
      return '<svg viewBox="0 0 64 64" aria-hidden="true">'
        + '<ellipse cx="34" cy="28" rx="18" ry="11" fill="#dfe7f2"/>'
        + '<ellipse cx="24" cy="24" rx="14" ry="10" fill="#cdd5e0"/>'
        + '<g stroke="#5aa7ff" stroke-width="2" stroke-linecap="round"><line x1="22" y1="44" x2="18" y2="52"/><line x1="32" y1="44" x2="28" y2="52"/><line x1="42" y1="44" x2="38" y2="52"/></g>'
        + '</svg>';
    }
    if (c.indexOf("słoń") >= 0 || c.indexOf("bezchmurn") >= 0 || c.indexOf("sun") >= 0 || c.indexOf("clear") >= 0) {
      return '<svg viewBox="0 0 64 64" aria-hidden="true">'
        + '<circle cx="32" cy="32" r="11" fill="#ffd34d"/>'
        + '<g stroke="#ffd34d" stroke-width="2.4" stroke-linecap="round">'
        + '<line x1="32" y1="6" x2="32" y2="14"/>'
        + '<line x1="32" y1="50" x2="32" y2="58"/>'
        + '<line x1="6" y1="32" x2="14" y2="32"/>'
        + '<line x1="50" y1="32" x2="58" y2="32"/>'
        + '<line x1="13" y1="13" x2="18" y2="18"/>'
        + '<line x1="46" y1="46" x2="51" y2="51"/>'
        + '<line x1="13" y1="51" x2="18" y2="46"/>'
        + '<line x1="46" y1="18" x2="51" y2="13"/>'
        + '</g></svg>';
    }
    // default: partly cloudy (cloud + sun)
    return '<svg viewBox="0 0 64 64" aria-hidden="true">'
      + '<circle cx="40" cy="20" r="8" fill="#ffd34d"/>'
      + '<g stroke="#ffd34d" stroke-width="1.6" stroke-linecap="round">'
      + '<line x1="40" y1="6" x2="40" y2="10"/>'
      + '<line x1="40" y1="30" x2="40" y2="34"/>'
      + '<line x1="26" y1="20" x2="30" y2="20"/>'
      + '<line x1="50" y1="20" x2="54" y2="20"/>'
      + '</g>'
      + '<ellipse cx="28" cy="40" rx="18" ry="11" fill="#e6ecf3"/>'
      + '<ellipse cx="20" cy="36" rx="12" ry="9" fill="#d2dae3"/>'
      + '</svg>';
  }
  function wxHourIcon(cond) {
    var c = (cond || "").toLowerCase();
    if (c.indexOf("burz") >= 0) return "⛈";
    if (c.indexOf("deszcz") >= 0 || c.indexOf("opad") >= 0) return "🌧";
    if (c.indexOf("słoń") >= 0 || c.indexOf("bezchmurn") >= 0) return "☀";
    if (c.indexOf("pochmurn") >= 0 || c.indexOf("cloud") >= 0) return "☁";
    return "⛅";
  }

  function renderWeather(node, widget) {
    if (!widget || widget.status === "empty") return emptyMsg(node, "Brak danych pogodowych.");
    if (widget.status === "error")   return errorMsg(node, widget.error);
    var d = (widget.data) || {};
    var now = d.current || {};
    var city = d.city || "--";
    var cond = now.condition || "Częściowe zachmurzenie";
    var temp = (now.temp_c != null) ? Math.round(now.temp_c) + "°C" : "--°";
    var feels = now.feels_like_c != null ? ("Odczuwalna " + Math.round(now.feels_like_c) + "°C") : "Odczuwalna --";
    var wind = now.wind_kmh != null ? (now.wind_kmh >= 0 ? "+" : "") + Math.round(now.wind_kmh) + " km/h" : "--";
    var hum  = now.humidity_pct != null ? Math.round(now.humidity_pct) + "%" : "--";
    var prec = now.precip_pct != null ? Math.round(now.precip_pct) + "%" : "--";

    var hours = Array.isArray(d.hourly) ? d.hourly.slice(0, 5) : [];

    var html = "";
    html += '<div class="weather">';
    html +=   '<div class="weather__city">' + esc(city) + '</div>';
    html +=   '<div class="weather__row">';
    html +=     '<div>';
    html +=       '<div class="weather__temp">' + esc(temp) + '</div>';
    html +=       '<div class="weather__cond">' + esc(cond) + '</div>';
    html +=       '<div class="weather__feels">' + esc(feels) + '</div>';
    html +=     '</div>';
    html +=     '<div class="weather__icon">' + wxIconSVG(cond) + '</div>';
    html +=   '</div>';
    html +=   '<div class="weather__metrics">';
    html +=     '<div class="weather__metric"><span class="weather__metric-label">Wiatr</span><span class="weather__metric-value">' + esc(wind) + '</span></div>';
    html +=     '<div class="weather__metric"><span class="weather__metric-label">Wilgotność</span><span class="weather__metric-value">' + esc(hum) + '</span></div>';
    html +=     '<div class="weather__metric"><span class="weather__metric-label">Opady</span><span class="weather__metric-value">' + esc(prec) + '</span></div>';
    html +=   '</div>';
    if (hours.length) {
      html += '<div class="weather__hours">';
      for (var i = 0; i < hours.length; i++) {
        var h = hours[i] || {};
        var t = h.hour || "--:--";
        if (typeof t === "string" && t.length >= 5) t = t.substring(0, 5);
        var cnd = h.condition || "";
        var dd  = h.temp_c != null ? Math.round(h.temp_c) + "°" : "--";
        html += '<div class="weather__hour"><span class="weather__hour-t">' + esc(t) + '</span><span class="weather__hour-i">' + esc(wxHourIcon(cnd)) + '</span><span class="weather__hour-d">' + esc(dd) + '</span></div>';
      }
      html += '</div>';
    }
    html += '</div>';

    node.innerHTML = html;
  }

  // ---- route ------------------------------------------------------------

  function renderRoute(node, widget) {
    if (!widget || widget.status === "empty") return emptyMsg(node, "Brak danych trasy.");
    if (widget.status === "error")   return errorMsg(node, widget.error);
    var d = (widget.data) || {};
    var start = d.start_label || "Dom";
    var end   = d.end_label   || "Praca";
    var win   = d.time_window || "--";
    var dur   = d.duration_min != null ? d.duration_min + " min" : "-- min";
    var note  = d.note || "Najszybsza trasa";
    var via   = d.via || "A4";

    var html = "";
    html += '<div class="route">';
    html +=   '<div class="route__time">';
    html +=     '<span class="route__time-window">' + esc(win) + '</span>';
    html +=     '<span class="route__time-dur">' + esc(dur) + '</span>';
    html +=   '</div>';
    html +=   '<div class="route__note">' + esc(note) + ' przez ' + esc(via) + '</div>';
    html +=   '<div class="route__map">';
    html +=     '<span class="route__map-label start">' + esc(start) + '</span>';
    html +=     '<span class="route__map-label end">'   + esc(end)   + '</span>';
    html +=     '<span class="route__map-label city">'  + esc(d.city || "Kraków") + '</span>';
    html +=     '<svg viewBox="0 0 400 220" preserveAspectRatio="none" aria-hidden="true">';
    html +=       '<path d="M40 180 C 80 60, 140 200, 200 110 S 320 60, 360 40" fill="none" stroke="#4ea1ff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>';
    html +=       '<path d="M40 180 C 80 60, 140 200, 200 110 S 320 60, 360 40 L 360 46 C 320 66, 200 116, 140 206, 80 66, 40 186 Z" fill="rgba(78,161,255,0.18)"/>';
    html +=       '<circle cx="40" cy="180" r="6" class="route__map-home"/>';
    html +=       '<circle cx="40" cy="180" r="3" fill="#fff"/>';
    html +=       '<circle cx="360" cy="40" r="6" class="route__map-pin"/>';
    html +=     '</svg>';
    html +=   '</div>';
    html += '</div>';

    node.innerHTML = html;
  }

  // ---- calendar ---------------------------------------------------------

  function renderCalendar(node, widget) {
    if (!widget || widget.status === "empty") return emptyMsg(node, "Brak wydarzeń na dziś.");
    if (widget.status === "error")   return errorMsg(node, widget.error);
    var d = (widget.data) || {};
    var date = d.date_human || "--";
    var events = Array.isArray(d.events) ? d.events : [];
    // Passive-screen rule: render the visible agenda only. No overflow hints on
    // the glanceable home display.

    var html = "";
    html += '<div class="calendar">';
    html +=   '<div class="calendar__date">' + esc(date) + '</div>';
    if (!events.length) {
      html += '<p class="muted">Brak wydarzeń w kalendarzu.</p>';
    } else {
      html += '<ul class="calendar__list">';
      for (var i = 0; i < events.length; i++) {
        var e = events[i] || {};
        var color = e.color || "var(--blue)";
        var t = e.time || "--:--";
        var title = e.title || "(bez tytułu)";
        html += '<li class="calendar__item">';
        html +=   '<span class="calendar__time">' + esc(t) + '</span>';
        html +=   '<span class="calendar__title"><span class="calendar__dot" style="background:' + escAttr(color) + '"></span>' + esc(title) + '</span>';
        html += '</li>';
      }
      html += '</ul>';
    }
    html += '</div>';

    node.innerHTML = html;
  }

  // ---- alerts -----------------------------------------------------------

  function renderAlerts(node, widget) {
    if (!widget || widget.status === "empty") return emptyMsg(node, "Brak alertów.");
    if (widget.status === "error")   return errorMsg(node, widget.error);
    var d = (widget.data) || {};
    var items = Array.isArray(d.alerts) ? d.alerts : [];
    var total = d.total || items.length;

    if (!items.length) return emptyMsg(node, "Brak alertów.");

    var html = "";
    html += '<div class="alerts">';
    html +=   '<div class="alerts__list">';
    for (var i = 0; i < items.length; i++) {
      var a = items[i] || {};
      var kind = (a.kind || "info").toLowerCase();
      var cls = "blue";
      if (kind === "promka" || kind === "promo" || kind === "ok")      cls = "green";
      else if (kind === "info")                                         cls = "blue";
      else if (kind === "warning" || kind === "warn")                   cls = "orange";
      else if (kind === "error" || kind === "critical")                 cls = "red";
      var letter = a.icon_letter || (kind.charAt(0).toUpperCase() || "i");
      var title = a.title || "(brak tytułu)";
      var sub = a.detail || "";
      var tm  = a.ago || a.time_ago || "";
      html += '<div class="alert-card">';
      html +=   '<span class="alert-card__icon alert-card__icon--' + escAttr(cls) + '">' + esc(letter) + '</span>';
      html +=   '<div>';
      html +=     '<div class="alert-card__head"><span class="alert-card__kind alert-card__kind--' + escAttr(cls) + '">' + esc((a.kind || "info").toUpperCase()) + '</span></div>';
      html +=     '<div class="alert-card__title">' + esc(title) + '</div>';
      if (sub) html += '<div class="alert-card__sub">' + esc(sub) + '</div>';
      html +=   '</div>';
      html +=   '<span class="alert-card__time">' + esc(tm) + '</span>';
      html += '</div>';
    }
    html +=   '</div>';
    html += '</div>';

    node.innerHTML = html;
  }

  // ---- volleyball -------------------------------------------------------

  function flagFor(code) {
    if (!code) return "flag--pl";
    var c = String(code).toLowerCase();
    return "flag--"+c;
  }
  function teamName(t) {
    if (!t) return "";
    if (typeof t === "string") return t;
    return t.name || t.short || "";
  }
  function teamFlag(t) {
    if (!t) return "pl";
    if (typeof t === "string") return "pl";
    return t.flag || t.code || "pl";
  }

  // ---- volleyball time helpers ------------------------------------------
  // Probe stores start_at as ISO with timezone (e.g. 2026-06-18T17:00:00+07:00
  // for VNL Bangkok). The dashboard lives in Warsaw (Europe/Warsaw,
  // CEST = UTC+2 in June). We always render times in PL time so a viewer
  // reading "17:00" doesn't assume it's Polish 17:00. The probe's source
  // city is appended in small print when it differs from "Bangkok"/"Osaka"
  // would be too noisy; instead we always show PL time + a tiny
  // "Bangkok 17:00" hint only when the source tz offset is not +02:00.
  var PL_TZ_OFFSET_MIN = 120; // Warsaw is UTC+2 (CEST) in summer
  var KIOSK_NOW = null;       // injected from server /api/health if present

  function parseStartAt(m) {
    // Returns a Date parsed from m.start_at (ISO with offset) or null.
    if (!m || !m.start_at) return null;
    var s = String(m.start_at);
    var d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  }

  function tzOffsetMinFromIso(iso) {
    // Extracts the offset in minutes from an ISO string like
    // "2026-06-18T17:00:00+07:00". Returns null if not parseable.
    var m = String(iso || "").match(/([+-])(\d{2}):(\d{2})$/);
    if (!m) return null;
    var sign = m[1] === "-" ? -1 : 1;
    return sign * (parseInt(m[2], 10) * 60 + parseInt(m[3], 10));
  }

  function formatTimeWarsaw(d) {
    // Renders HH:MM in Europe/Warsaw regardless of the source timezone.
    // Uses Intl.DateTimeFormat so DST is handled correctly (CEST/CET).
    try {
      return new Intl.DateTimeFormat("pl-PL", {
        hour: "2-digit", minute: "2-digit", timeZone: "Europe/Warsaw", hour12: false
      }).format(d);
    } catch (e) {
      // Fallback: assume d is already UTC and add Warsaw offset.
      var t = d.getUTCHours() * 60 + d.getUTCMinutes() + PL_TZ_OFFSET_MIN;
      t = ((t % 1440) + 1440) % 1440;
      var hh = Math.floor(t / 60), mm = t % 60;
      return (hh < 10 ? "0" : "") + hh + ":" + (mm < 10 ? "0" : "") + mm;
    }
  }

  function formatDateWarsaw(d) {
    // Renders "DD.MM" in Europe/Warsaw. The source probe's `date_human`
    // is the venue's local calendar day (e.g. 17.07 for a 2026-07-18T03:00
    // PL match played in Hoffman Estates USA), so we MUST re-derive the
    // date from `start_at` in PL tz or the user sees "kilka godzin między
    // meczami" because two same-USA-weekend matches collapse into adjacent
    // rows. (Fix 2026-07-10.)
    try {
      return new Intl.DateTimeFormat("pl-PL", {
        day: "2-digit", month: "2-digit", timeZone: "Europe/Warsaw"
      }).format(d);
    } catch (e) {
      // Fallback: assume d is already UTC and add Warsaw offset.
      var t = d.getTime() + PL_TZ_OFFSET_MIN * 60000;
      var dt = new Date(t);
      var dd = String(dt.getUTCDate()).padStart(2, "0");
      var mm = String(dt.getUTCMonth() + 1).padStart(2, "0");
      return dd + "." + mm;
    }
  }

  function weekdayWarsaw(d) {
    // Short Polish weekday name ("Śr", "So", "Nd") in Europe/Warsaw.
    try {
      var s = new Intl.DateTimeFormat("pl-PL", {
        weekday: "short", timeZone: "Europe/Warsaw"
      }).format(d);
      // Intl returns "śr." with a trailing dot and Polish lowercase chars;
      // normalize to 2-letter Title Case for compact display.
      s = s.replace(/\.$/, "").trim();
      if (s.length >= 2) return s.charAt(0).toUpperCase() + s.charAt(1).toLowerCase();
      return s.toUpperCase();
    } catch (e) {
      return "";
    }
  }

  function startAtMs(m) {
    // Numeric epoch ms from `start_at` for sorting. Returns +Infinity
    // when missing so unparseable rows sort to the end instead of the
    // beginning (the old code used a string-compare on "DD.MM.YYYY HH:MM"
    // which sorted "03:00" before "19:00" lexicographically, which is
    // wrong for cross-day PL times). (Fix 2026-07-10.)
    var d = parseStartAt(m);
    return d ? d.getTime() : Number.POSITIVE_INFINITY;
  }

  function formatTimeSource(d) {
    // Renders HH:MM in the *source* timezone from the ISO string.
    // We accept both "+HH:MM" and "Z"; Z → source time == UTC, which we
    // mostly use as a fallback when no explicit offset is known.
    var off = tzOffsetMinFromIso(arguments[1]);
    if (off == null) {
      // Fallback: if it's "Z", source = UTC.
      if (typeof arguments[1] === "string" && /Z$/.test(arguments[1])) off = 0;
      else return "";
    }
    var srcMin = d.getUTCHours() * 60 + d.getUTCMinutes() + off;
    srcMin = ((srcMin % 1440) + 1440) % 1440;
    var hh = Math.floor(srcMin / 60), mm = srcMin % 60;
    return (hh < 10 ? "0" : "") + hh + ":" + (mm < 10 ? "0" : "") + mm;
  }

  // matchStatus(m, now):
  //   LIVE  → now ∈ [start - 15 min, start + 3 h]
  //   NEXT  → start > now, within 24 h → "za 4h 30m" or "za 25 min"
  //   TODAY → start is today but > 24 h away (rare) → just date+time
  //   LATER → otherwise
  // We deliberately count a match LIVE 15 min before start so users don't
  // see "za 0 min" flicker at the moment kick-off is reached.
  function matchStatus(m, nowMs) {
    var d = parseStartAt(m);
    if (!d) return { status: "LATER", minutesToStart: null };
    var ms = d.getTime() - nowMs;
    var minutesToStart = Math.round(ms / 60000);
    if (minutesToStart <= 15 && minutesToStart >= -180) return { status: "LIVE", minutesToStart: minutesToStart };
    if (minutesToStart > 15 && minutesToStart <= 24 * 60) return { status: "NEXT", minutesToStart: minutesToStart };
    if (minutesToStart > 24 * 60 && minutesToStart <= 7 * 24 * 60) return { status: "WEEK", minutesToStart: minutesToStart };
    return { status: "LATER", minutesToStart: minutesToStart };
  }

  function minutesToHuman(min) {
    if (min == null) return "";
    if (min <= 0) return "teraz";
    if (min < 60) return "za " + min + " min";
    var h = Math.floor(min / 60);
    var m2 = min % 60;
    if (m2 === 0) return "za " + h + "h";
    return "za " + h + "h " + m2 + "min";
  }

  function nowMs() {
    // If the server injected a clock (e.g. /api/health.now), use it so
    // kiosk and dashboard agree even if the kiosk browser clock is off.
    return Date.now();
  }

  function renderVB(node, widget) {
    if (!widget || widget.status === "empty") return emptyMsg(node, "Brak danych o meczach.");
    if (widget.status === "error")   return errorMsg(node, widget.error);
    var d = (widget.data) || {};
    var men  = Array.isArray(d.men)  ? d.men  : [];
    var women = Array.isArray(d.women) ? d.women : [];
    var combined = [];
    men.forEach(function (m) { var x = Object.assign({}, m); x._group = "M"; combined.push(x); });
    women.forEach(function (m) { var x = Object.assign({}, m); x._group = "K"; combined.push(x); });
    combined.sort(function (a, b) {
      // Sort by `start_at` epoch (PL instant) instead of the probe's
      // `date + time` (venue-local) which misorders matches across the
      // date line (e.g. PL Sat 03:00 + PL Sat 23:00 + PL Mon 03:00 vs
      // USA Fri 20:00 + USA Sat 16:00 + USA Sun 20:00). (Fix 2026-07-10.)
      return startAtMs(a) - startAtMs(b);
    });
    combined = combined.slice(0, 6);

    var now = nowMs();
    var html = "";
    html += '<div class="vb">';
    html +=   '<div class="vb__tabs" aria-hidden="true">';
    html +=     '<span class="vb__tab vb__tab--active">Najbliższe mecze</span>';
    html +=     '<span class="vb__tab">czas PL</span>';
    html +=   '</div>';
    if (!combined.length) {
      html += '<p class="muted">Brak nadchodzących meczów.</p>';
    } else {
      html += '<div class="vb__list">';
      for (var i = 0; i < combined.length; i++) {
        var m = combined[i] || {};
        var home = m.home || { name: "Polska", flag: "pl" };
        var away = m.away || { name: "--", flag: "pl" };
        // Derive PL date from `start_at` rather than trusting probe's
        // `date_human` (which is the venue's local calendar day). For
        // VNL 2026 Hoffman Estates (UTC-5) the probe says "17.07" for a
        // match whose PL start is 2026-07-18T03:00 — so showing the probe
        // date confuses users into thinking two consecutive USA-weekend
        // matches are hours apart when they're actually a day+ apart
        // in Warsaw. (Fix 2026-07-10.)
        var sd = parseStartAt(m);
        var st = matchStatus(m, now);
        var plTime = sd ? formatTimeWarsaw(sd) : "";
        var plDate = sd ? formatDateWarsaw(sd) : (m.date_human || m.date || "--");
        var plDow = sd ? weekdayWarsaw(sd) : "";
        var date = plDow ? (plDow + " " + plDate) : plDate;
        var tm   = m.time || "";
        var comp = m.competition || "";
        var loc  = m.location || "";

        var badge = "";
        if (st.status === "LIVE") {
          badge = '<span class="vb__badge vb__badge--live">● LIVE</span>';
        } else if (st.status === "NEXT") {
          badge = '<span class="vb__badge vb__badge--next">' + esc(minutesToHuman(st.minutesToStart)) + '</span>';
        }

        var whenHtml = '<strong>' + esc(date) + '</strong>';
        // Inline span for PL time + group letter + badge so the row stays
        // on 2 visual lines max: "18.06.2026" then "12:00 PL · K [LIVE]".
        // Only LOCAL (Warsaw) time — source-time removed per user 2026-06-19.
        whenHtml += '<span class="vb__when-sub">';
        if (plTime) whenHtml += esc(plTime) + ' PL';
        else if (tm) whenHtml += esc(tm);
        if (m._group) whenHtml += ' · ' + esc(m._group);
        if (badge) whenHtml += ' ' + badge;
        whenHtml += '</span>';

        html += '<div class="vb__row">';
        html +=   '<div class="vb__when">' + whenHtml + '</div>';
        html +=   '<div class="vb__match">';
        html +=     '<span class="vb__team"><span class="flag ' + escAttr(flagFor(teamFlag(home))) + '"></span><span class="vb__team-name">' + esc(teamName(home)) + '</span></span>';
        html +=     '<span class="vb__vs">vs</span>';
        html +=     '<span class="vb__team"><span class="flag ' + escAttr(flagFor(teamFlag(away))) + '"></span><span class="vb__team-name">' + esc(teamName(away)) + '</span></span>';
        html +=   '</div>';
        html +=   '<div class="vb__meta"><strong>' + esc(comp) + '</strong>' + esc(loc) + '</div>';
        html += '</div>';
      }
      html += '</div>';
    }
    html += '</div>';
    node.innerHTML = html;
  }

  // ---- LL TBD -----------------------------------------------------------

  // LL card is the chronological live birdwatch panel (kind="birdwatch").
  // The old TBD placeholder renderer stays as a fallback for the legacy
  // mock payload (no ``data.kind``) so we never strand the card during
  // the mock -> live transition.
  function renderBirdwatch(node, widget) {
    if (widget && widget.status === "error") return errorMsg(node, widget.error);
    var d = (widget && widget.data) || {};
    var title = d.title || "PTAKI ZA OKNEM";
    var subtitle = d.subtitle || "Nasłuch tarasu";
    var station = d.station || "taras";
    var audio = d.audio || {};
    var detections = Array.isArray(d.detections) ? d.detections : [];
    var emptyMsg = d.empty_message || "Cisza albo brak pewnego rozpoznania w ostatnich minutach.";

    var audioBadge = "";
    if (audio.status === "ok") {
      audioBadge = '<div class="birdwatch__audio birdwatch__audio--ok">'
        + '<span class="birdwatch__audio-dot"></span>'
        + esc(audio.device ? ("nasłuch: " + audio.device) : "nasłuch: aktywny")
        + "</div>";
    } else if (audio.status === "missing") {
      audioBadge = '<div class="birdwatch__audio birdwatch__audio--missing">'
        + '<span class="birdwatch__audio-dot"></span>'
        + esc(audio.message || "Brak mikrofonu — podłącz Zoom H4n")
        + "</div>";
    } else if (audio.status === "unknown") {
      audioBadge = '<div class="birdwatch__audio birdwatch__audio--unknown">'
        + '<span class="birdwatch__audio-dot"></span>'
        + esc(audio.message || "Status mikrofonu: nieznany")
        + "</div>";
    }

    var listHtml = "";
    if (!detections.length) {
      listHtml = '<div class="birdwatch__empty">'
        + '<span class="birdwatch__empty-icon" aria-hidden="true">·</span> '
        + esc(emptyMsg)
        + "</div>";
    } else {
      listHtml = '<ul class="birdwatch__list">';
      for (var i = 0; i < detections.length; i++) {
        var det = detections[i] || {};
        var time = det.time_label || "--:--";
        var speciesPl = det.species_pl || det.species_en || det.scientific || "nieznany ptak";
        var sci = det.scientific || "";
        var conf = det.confidence_label || "";
        var fresh = det.fresh ? " birdwatch__row--fresh" : "";
        var lowConf = det.confidence && det.confidence < 0.75
          ? " birdwatch__row--low" : "";
        // station badge: omit when it equals the default ("taras")
        var stationBadge = "";
        if (det.station && det.station !== station) {
          stationBadge = '<span class="birdwatch__station">' + esc(det.station) + "</span>";
        }
        var sourceBadge = "";
        if (det.source && det.source !== "birdnet" && det.source !== "birdwatch") {
          sourceBadge = '<span class="birdwatch__source">' + esc(det.source) + "</span>";
        }
        listHtml += '<li class="birdwatch__row' + fresh + lowConf + '">';
        listHtml +=   '<span class="birdwatch__time">' + esc(time) + "</span>";
        listHtml +=   '<span class="birdwatch__species">';
        listHtml +=     '<span class="birdwatch__species-pl">' + esc(speciesPl) + "</span>";
        if (sci) {
          listHtml +=   '<span class="birdwatch__species-sci">' + esc(sci) + "</span>";
        }
        listHtml +=   "</span>";
        listHtml +=   '<span class="birdwatch__meta">';
        if (conf) listHtml += '<span class="birdwatch__conf">' + esc(conf) + "</span>";
        listHtml +=     stationBadge + sourceBadge;
        listHtml +=   "</span>";
        listHtml += "</li>";
      }
      listHtml += "</ul>";
    }

    var html = "";
    html += '<div class="birdwatch">';
    html +=   '<div class="birdwatch__head">';
    html +=     '<div class="birdwatch__title">' + esc(title) + "</div>";
    html +=     '<div class="birdwatch__subtitle">' + esc(subtitle) + "</div>";
    html +=   "</div>";
    if (audioBadge) html += audioBadge;
    html +=   listHtml;
    html += "</div>";
    node.innerHTML = html;
  }

  function renderTBD(node, widget) {
    if (widget && widget.status === "error") return errorMsg(node, widget.error);
    var d = (widget && widget.data) || {};
    // New: Birdwatch LL card dispatches before the legacy placeholder.
    if (d && d.kind === "birdwatch") return renderBirdwatch(node, widget);
    var title = d.title || "Miejsce na Twoje pomysły";
    var sub   = d.subtitle || "Powiedz Hermesowi, co chcesz tu zobaczyć.";
    var icon  = d.icon || "idea";
    var iconSvg = (icon === "stack")
      ? '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3 6.6 3.7L12 11.7 5.4 8 12 4.3Zm-7 5.2 6 3.3v6.7l-6-3.3V9.5Zm14 0v6.7l-6 3.3v-6.7l6-3.3Z"/></svg>'
      : '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M4 7h16M4 12h16M4 17h10"/></svg>';
    var html = "";
    html += '<div class="tbd">';
    html +=   '<div class="tbd__drop">';
    html +=     '<div class="tbd__icon">' + iconSvg + '</div>';
    html +=     '<div class="tbd__title">' + esc(title) + '</div>';
    html +=     '<div class="tbd__sub">'   + esc(sub)   + '</div>';
    html +=   '</div>';
    html += '</div>';
    node.innerHTML = html;
  }

  // ---- video (UR) -------------------------------------------------------

  function renderVideo(node, widget) {
    if (!widget || widget.status === "empty") return emptyMsg(node, "Brak transmisji.");
    if (widget.status === "error")   return errorMsg(node, widget.error);
    var root = (widget.data) || {};
    var d = root.transmission || root;
    var running = !!d.live;
    var channel = d.channel || "Polsat Sport 1";
    var title = d.title || "Polsat Sport przez Polsat Box Go";
    var status = d.status_label || (running ? "OKNO OTWARTE" : "GOTOWE DO LOGOWANIA");
    var mode = d.mode || "external_chrome_profile";

    var html = "";
    html += '<div class="video video--polsatgo">';
    html +=   '<div class="video__stage video__stage--polsatgo">';
    html +=     '<div class="video__crowd"></div>';
    html +=     '<div class="polsatgo-panel">';
    html +=       '<div class="polsatgo-logo">POLSAT <span>BOX GO</span></div>';
    html +=       '<div class="polsatgo-channel">' + esc(channel) + '</div>';
    html +=       '<div class="polsatgo-title">' + esc(title) + '</div>';
    html +=       '<div class="polsatgo-status ' + (running ? 'is-live' : 'is-ready') + '">' + esc(status) + '</div>';
    html +=       '<div class="polsatgo-note">Normalna strona Polsat Box Go w osobnym trwałym profilu Chrome. Bez wyciągania streamu.</div>';
    html +=     '</div>';
    html +=     '<div class="video__polsat">POLSAT<span class="video__polsat-sport">SPORT</span></div>';
    if (running) html += '<div class="video__live">OKNO</div>';
    html +=   '</div>';
    html +=   '<div class="video__bar">';
    html +=     '<span class="video__bar-live ' + (running ? '' : 'is-muted') + '">' + (running ? 'WEB PLAYER' : 'LOGIN RĘCZNY') + '</span>';
    html +=     '<div class="video__bar-text">' + esc(mode) + '</div>';
    html +=   '</div>';
    html += '</div>';

    node.innerHTML = html;
  }

  // ---- slideshow (LR) ---------------------------------------------------

  function renderSlideshow(node, widget) {
    if (!widget || widget.status === "empty") return emptyMsg(node, "Brak zdjęć.");
    if (widget.status === "error")   return errorMsg(node, widget.error);
    var d = getSlideshowData(widget);
    var total = d.total || 42;
    var current = Math.max(1, Math.min(total, d.current || 10));

    var imageUrl = d.imageUrl || "";
    var album = d.album || "pedro slideshow";
    var photoClass = slideshowPhotoClass(d.orientation);

    var html = "";
    html += '<div class="slideshow" data-slideshow-current="' + current + '" data-slideshow-total="' + total + '">';
    if (imageUrl) {
      // Two stacked photo layers so we can crossfade between slides without
      // a black gap when the new WebP is still decoding. Only the inactive
      // layer's background-image changes per render; the active layer keeps
      // painting the previous photo until the new one is decoded.
      html += '<div class="slideshow__stage" data-current-url="' + escAttr(imageUrl) + '">';
      html +=   '<div class="slideshow__layer slideshow__photo slideshow__photo--image is-active" data-layer="a"></div>';
      html +=   '<div class="slideshow__layer slideshow__photo slideshow__photo--image" data-layer="b"></div>';
      html += '</div>';
    } else {
      html +=   '<div class="slideshow__photo">';
      html +=     '<div class="slideshow__skyline"></div>';
      html +=     '<div class="slideshow__lake"></div>';
      html +=     '<div class="slideshow__trees"></div>';
      html +=   '</div>';
    }
    html +=   '<div class="slideshow__caption">' + esc(album) + '</div>';
    html +=   '<div class="slideshow__counter">' + current + ' / ' + total + '</div>';
    html += '</div>';

    node.innerHTML = html;
    if (imageUrl) {
      var stageEl = node.querySelector(".slideshow__stage");
      if (stageEl) {
        var layers = stageEl.querySelectorAll(".slideshow__layer");
        for (var i = 0; i < layers.length; i++) {
          layers[i].className = "slideshow__layer slideshow__photo " + photoClass;
        }
        // First render: paint the current photo on layer A, leave B empty,
        // and start a soft preload of the same URL so Chrome warms its
        // decoder. Subsequent renders detect that the URL changed via
        // data-current-url and call applySlideshowPhoto for a true crossfade.
        var prevUrl = stageEl.getAttribute("data-current-url") || "";
        // Track whether we have EVER painted a photo into this stage. The
        // boolean is independent of which URL was last painted so that a first
        // render with prevUrl="" doesn't skip the paint, and a render with the
        // same URL as the last one still triggers a preload + initial paint.
        var everPainted = stageEl.getAttribute("data-ever-painted") === "1";
        if (!everPainted) {
          // First paint: just place the image on layer A, no transition.
          setSlideshowLayerBackground(layers[0], imageUrl);
          layers[0].classList.add("is-active");
          layers[1].classList.remove("is-active");
          stageEl.setAttribute("data-current-url", imageUrl);
          stageEl.setAttribute("data-ever-painted", "1");
          var warmImg = new Image();
          warmImg.decoding = "async";
          warmImg.src = imageUrl;
        } else if (prevUrl !== imageUrl) {
          applySlideshowPhoto(stageEl, imageUrl, d.orientation);
        } else {
          // Same URL, just refresh labels. Active layer already painted.
          layers[0].classList.add("is-active");
          layers[1].classList.remove("is-active");
        }
        }
        }
  }

  function setSlideshowLayerBackground(layerEl, url) {
    if (!layerEl) return;
    if (layerEl.style.backgroundImage === "url(\"" + url + "\")") return;
    layerEl.style.backgroundImage = "url(\"" + url + "\")";
  }

  function applySlideshowPhoto(stageEl, nextUrl, orientation) {
    if (!stageEl || !nextUrl) return;
    var photoClass = slideshowPhotoClass(orientation);
    var layers = stageEl.querySelectorAll(".slideshow__layer");
    var inactive = null;
    var active = null;
    for (var i = 0; i < layers.length; i++) {
      if (layers[i].classList.contains("is-active")) active = layers[i];
      else inactive = layers[i];
    }
    if (!active) active = layers[0];
    if (!inactive) inactive = layers[layers.length - 1];
    inactive.className = "slideshow__layer slideshow__photo " + photoClass;
    setSlideshowLayerBackground(inactive, nextUrl);
    var nextImg = new Image();
    nextImg.decoding = "async";
    var flip = function () {
      requestAnimationFrame(function () {
        inactive.classList.add("is-active");
        active.classList.remove("is-active");
      });
      stageEl.setAttribute("data-current-url", nextUrl);
    };
    nextImg.onload = function () {
      if (typeof nextImg.decode === "function") {
        nextImg.decode().then(flip).catch(flip);
      } else {
        flip();
      }
    };
    nextImg.onerror = flip;
    nextImg.src = nextUrl;
  }

  function getSlideshowData(widget) {
    var root = (widget && widget.data) || {};
    var d = root.slideshow || root;
    return {
      total: d.total || 0,
      current: d.current || 0,
      imageUrl: d.image_url || d.imageUrl || "",
      album: d.album || "pedro slideshow",
      orientation: d.image_orientation || d.orientation || ""
    };
  }

  function slideshowPhotoClass(orientation) {
    // Build a class suffix so the CSS can pick cover vs contain per orientation.
    // Landscape keeps cover behaviour. Portrait/square use a black letterbox so
    // the whole photo stays visible during the full-screen rotation too.
    var photoClass = "slideshow__photo slideshow__photo--image";
    if (orientation === "portrait") {
      photoClass += " slideshow__photo--portrait";
    } else if (orientation === "square") {
      photoClass += " slideshow__photo--square";
    }
    return photoClass;
  }

  function setDisplayMode(mode) {
    if (mode !== "slideshow") mode = "dashboard";
    rotationState.mode = mode;
    document.body.setAttribute("data-display-mode", mode);
    var overlay = document.getElementById("fullscreen-slideshow");
    if (overlay) overlay.setAttribute("aria-hidden", mode === "slideshow" ? "false" : "true");
  }

  // Commute-window guard: between 06:40 inclusive and 07:40 exclusive
  // Europe/Warsaw the room screen must stay on the dashboard so the
  // morning routine (calendar, news, bus/train info) is reachable.
  // Outside the window this returns false and the regular dashboard /
  // fullscreen slideshow rotation is used unchanged. The guard is
  // intentionally derived from a Warsaw-clock probe (not the kiosk's
  // local time) so an iMac timezone drift or a CET/CEST change cannot
  // silently break the window.
  function isCommuteDashboardWindowWarsaw(nowMs) {
    var ref = (typeof nowMs === "number" && isFinite(nowMs)) ? new Date(nowMs) : new Date();
    var hh = NaN, mm = NaN;
    try {
      var parts = new Intl.DateTimeFormat("en-GB", {
        hour: "2-digit", minute: "2-digit", hour12: false,
        timeZone: "Europe/Warsaw"
      }).formatToParts(ref);
      for (var i = 0; i < parts.length; i++) {
        if (parts[i].type === "hour") hh = parseInt(parts[i].value, 10);
        else if (parts[i].type === "minute") mm = parseInt(parts[i].value, 10);
      }
    } catch (e) {
      // Fallback: assume ref is UTC and add Warsaw offset (CEST +120 min).
      var t = ref.getUTCHours() * 60 + ref.getUTCMinutes() + 120;
      t = ((t % 1440) + 1440) % 1440;
      hh = Math.floor(t / 60);
      mm = t % 60;
    }
    if (!isFinite(hh) || !isFinite(mm)) return false;
    // Window: [06:40, 07:40) — start inclusive, end exclusive.
    var mins = hh * 60 + mm;
    return mins >= 6 * 60 + 40 && mins < 7 * 60 + 40;
  }

  function renderFullscreenSlideshow(widget) {
    var overlay = document.getElementById("fullscreen-slideshow");
    if (!overlay) return;
    var d = getSlideshowData(widget);
    var total = d.total || 0;
    var current = total ? Math.max(1, Math.min(total, d.current || 1)) : 0;
    var imageUrl = d.imageUrl || "";
    var album = d.album || "pedro slideshow";
    var photoClass = "fullscreen-slideshow__photo";
    if (d.orientation === "portrait") photoClass += " fullscreen-slideshow__photo--portrait";
    else if (d.orientation === "square") photoClass += " fullscreen-slideshow__photo--square";

    if (!imageUrl) {
      overlay.innerHTML = '<div class="fullscreen-slideshow__empty">Brak zdjęć do pełnego ekranu</div>';
      return;
    }

    // Two stacked photos so we can crossfade instead of cutting black. The
    // first render installs both layers in the "stage is current" state;
    // later renders detect a URL change via data-current-url and call
    // applyFullscreenPhoto for a true crossfade. The active layer keeps
    // painting the previous photo until the new WebP finishes decoding.
    var html = "";
    html += '<div class="fullscreen-slideshow__stage" data-current-url="' + escAttr(imageUrl) + '">';
    html +=   '<div class="fullscreen-slideshow__layer fullscreen-slideshow__photo is-active" data-layer="a"></div>';
    html +=   '<div class="fullscreen-slideshow__layer fullscreen-slideshow__photo" data-layer="b"></div>';
    html +=   '<div class="fullscreen-slideshow__shade"></div>';
    html +=   '<div class="fullscreen-slideshow__label">SLIDESHOW</div>';
    html +=   '<div class="fullscreen-slideshow__meta">';
    html +=     '<span>' + esc(album) + '</span>';
    if (total) html += '<span>' + current + ' / ' + total + '</span>';
    html +=   '</div>';
    html += '</div>';
    overlay.innerHTML = html;
    var stageEl = overlay.querySelector(".fullscreen-slideshow__stage");
    if (stageEl) {
      var layers = stageEl.querySelectorAll(".fullscreen-slideshow__layer");
      for (var i = 0; i < layers.length; i++) {
        layers[i].className = "fullscreen-slideshow__layer fullscreen-slideshow__photo " + photoClass;
      }
      var prevUrl = stageEl.getAttribute("data-prev-url") || "";
      var everPainted = stageEl.getAttribute("data-ever-painted") === "1";
      if (!everPainted) {
        // First paint: just place the image on layer A, no transition.
        setLayerBackground(layers[0], imageUrl);
        layers[0].classList.add("is-active");
        layers[1].classList.remove("is-active");
        stageEl.setAttribute("data-current-url", imageUrl);
        stageEl.setAttribute("data-ever-painted", "1");
      } else if (prevUrl !== imageUrl) {
        applyFullscreenPhoto(stageEl, imageUrl, d.orientation);
      } else {
        layers[0].classList.add("is-active");
        layers[1].classList.remove("is-active");
      }
      // Remember this URL for the next render's diff.
      stageEl.setAttribute("data-prev-url", imageUrl);
    }
    // Preload + warm up the next image so the swap is instant.
    preloadNextImage(d);
  }

  function setLayerBackground(layerEl, url) {
    if (!layerEl) return;
    if (layerEl.style.backgroundImage === "url(\"" + url + "\")") return;
    layerEl.style.backgroundImage = "url(\"" + url + "\")";
  }

  // Returns the next layer (the one without .is-active). If only one layer
  // exists we fall back to the same element so the swap still works on the
  // embedded card.
  function pickInactiveLayer(stageEl) {
    if (!stageEl) return null;
    var layers = stageEl.querySelectorAll(".fullscreen-slideshow__layer");
    for (var i = 0; i < layers.length; i++) {
      if (!layers[i].classList.contains("is-active")) return layers[i];
    }
    return layers[0] || null;
  }

  // Push the next photo URL into the inactive layer, decode it, then flip
  // the .is-active class so CSS crossfades. Decoding before the swap is the
  // actual anti-black-gap fix — without it, Chrome would paint the new layer
  // before the JPEG/WebP finished decoding, producing a visible flash.
  function applyFullscreenPhoto(stageEl, nextUrl, orientation) {
    if (!stageEl || !nextUrl) return;
    var photoClass = "fullscreen-slideshow__photo";
    if (orientation === "portrait") photoClass += " fullscreen-slideshow__photo--portrait";
    else if (orientation === "square") photoClass += " fullscreen-slideshow__photo--square";
    var inactive = pickInactiveLayer(stageEl);
    var active = stageEl.querySelector(".fullscreen-slideshow__layer.is-active") || stageEl.querySelectorAll(".fullscreen-slideshow__layer")[0];
    if (!inactive || !active) return;
    inactive.className = "fullscreen-slideshow__layer fullscreen-slideshow__photo " + photoClass;
    setLayerBackground(inactive, nextUrl);
    var nextImg = new Image();
    nextImg.decoding = "async";
    var flip = function () {
      // Force a single rAF so the browser registers the new background-image
      // before we toggle opacity — otherwise the crossfade can be skipped on
      // fast hardware.
      requestAnimationFrame(function () {
        inactive.classList.add("is-active");
        active.classList.remove("is-active");
      });
      stageEl.setAttribute("data-current-url", nextUrl);
    };
    nextImg.onload = function () {
      if (typeof nextImg.decode === "function") {
        nextImg.decode().then(flip).catch(flip);
      } else {
        flip();
      }
    };
    nextImg.onerror = flip; // show whatever decoded so we never strand black
    nextImg.src = nextUrl;
  }

  // Kick off a background preload for the image the rotator will most likely
  // serve next (current+1, modulo total). This gives Chrome a head start so
  // the actual crossfade in applyFullscreenPhoto is instant. We don't await
  // — it's pure opportunistic warming of the HTTP/disk cache.
  function preloadNextImage(d) {
    if (!d || !d.total || !d.imageUrl) return;
    var nextIdx = (d.current || 1) % d.total + 1;
    // The probe embeds the next image URL only in the manifest, which the
    // kiosk does not have. So instead we walk the slide list via the API —
    // but we don't want every slide to do that. Cheaper: just preload the
    // current image again, which reuses the cached bitmap. Chromium's image
    // cache keys by URL, so the second <img src> request is free.
    var img = new Image();
    img.decoding = "async";
    img.src = d.imageUrl;
  }

  function updateDisplayRotation(widget) {
    if (!rotationEnabled) {
      setDisplayMode("dashboard");
      return;
    }
    var d = getSlideshowData(widget);
    if (!d.imageUrl) {
      // No photo = do not hide the useful dashboard behind an empty overlay.
      rotationState.switchAt = Date.now() + 30000;
      setDisplayMode("dashboard");
      return;
    }

    var now = Date.now();
    // Morning commute window: force dashboard-only and never activate the
    // fullscreen slideshow overlay. The embedded slideshow card on the
    // dashboard remains untouched. Keep pushing switchAt forward so the
    // very first tick after 07:40 resumes the normal cycle cleanly
    // instead of trying to immediately honour a stale switchAt.
    if (isCommuteDashboardWindowWarsaw(now)) {
      rotationState.switchAt = now + rotationDashboardMs;
      setDisplayMode("dashboard");
      document.body.setAttribute("data-display-rotation-next", String(rotationState.switchAt));
      return;
    }

    if (now >= rotationState.switchAt) {
      if (rotationState.mode === "dashboard") {
        setDisplayMode("slideshow");
        rotationState.switchAt = now + rotationSlideshowMs;
      } else {
        setDisplayMode("dashboard");
        rotationState.switchAt = now + rotationDashboardMs;
      }
    } else {
      setDisplayMode(rotationState.mode);
    }
    document.body.setAttribute("data-display-rotation-next", String(rotationState.switchAt));
  }

  // ---- escape utilities -------------------------------------------------

  function esc(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }
  function escAttr(s) {
    return esc(s).replace(/"/g, "&quot;");
  }


  // Ticker text formats. Kept dead-simple on purpose: a kitchen reader
  // scanning the bottom strip has ~3 seconds per item, so the only fields
  // we show are WHO and HOW MUCH. No dates, no weekday, no competition
  // name, no "następny:" / "LIVE:" prefix noise. K/M stays on every
  // result so women's and men's matches remain distinguishable.
  function resultTickerText(m) {
    if (!m) return null;
    var home = teamName(m.home || { name: "Polska" });
    var away = teamName(m.away || { name: "--" });
    var score = m.score
      || ((m.home_sets != null && m.away_sets != null)
            ? (m.home_sets + ":" + m.away_sets)
            : null);
    if (!score) return null;
    var txt = home + " " + score + " " + away;
    // Append (K)/(M) when group is known — user wants women vs men
    // distinguishable at-a-glance on the bottom ticker (2026-06-19).
    if (m._group === "K" || m._group === "M") txt += " (" + m._group + ")";
    return txt;
  }

  function liveTickerText(m) {
    if (!m) return null;
    var home = teamName(m.home || { name: "Polska" });
    var away = teamName(m.away || { name: "--" });
    var txt = "LIVE " + home + " vs " + away;
    if (m._group === "K" || m._group === "M") txt += " (" + m._group + ")";
    return txt;
  }

  function upcomingTickerText(m) {
    if (!m) return null;
    var home = teamName(m.home || { name: "Polska" });
    var away = teamName(m.away || { name: "--" });
    return home + " vs " + away;
  }

  function euroVolleyTickerRows(widgets) {
    var widget = widgets && widgets.eurovolley;
    var modules = window.PedroEuroScheduleModules || {};
    if (typeof modules.normalizeTicker === "function") {
      var model = modules.normalizeTicker(widget);
      return model && Array.isArray(model.rows) ? model.rows : [];
    }
    return [];
  }

  function tickerGroup(m) {
    return m && (m.gender === "K" || m.gender === "M") ? m.gender : "";
  }

  function tickerStartAt(m) {
    return (m && (m.startAt || m.start_at || m.date)) || "";
  }

  function tickerScore(m) {
    if (!m) return null;
    if (m.home_sets != null && m.away_sets != null) {
      return m.home_sets + ":" + m.away_sets;
    }
    if (typeof m.score === "string" && m.score.trim()) {
      return m.score.trim().split(/\s+/)[0];
    }
    return null;
  }

  function renderTicker(widgets) {
    var track = document.getElementById("ticker-track");
    if (!track) return;
    var rows = euroVolleyTickerRows(widgets);
    var items = [];

    // Order: LIVE (if any) → most recent EuroVolley results (latest first,
    // max 6). Upcoming fixtures belong in UL/LL, not in this compact strip.

    // 1. LIVE matches first. Trust the normalized CEV status instead of
    // deriving a live window from start_at; finished matches can have a
    // recent timestamp and must not be relabelled LIVE.
    rows.filter(function (m) { return m.status === "live"; })
      .sort(function (a, b) {
        return tickerStartAt(a).localeCompare(tickerStartAt(b));
      })
      .forEach(function (m) {
        var live = Object.assign({}, m, { _group: tickerGroup(m) });
        var s = liveTickerText(live);
        if (s) items.push(s);
      });

    // 2. Completed/current results. The module state contains the official
    // score; trim any per-set breakdown so the ticker stays readable.
    rows.filter(function (m) {
      return m.status === "finished" || tickerScore(m) != null;
    }).sort(function (a, b) {
      return tickerStartAt(b).localeCompare(tickerStartAt(a));
    }).slice(0, 6).forEach(function (m) {
      var result = Object.assign({}, m, {
        _group: tickerGroup(m),
        score: tickerScore(m)
      });
      var s = resultTickerText(result);
      if (s) items.push(s);
    });

    if (!items.length) items.push("Brak wyników EuroVolley");
    track.innerHTML = items.map(function (x) { return '<span>' + esc(x) + '</span>'; }).join('');
  }

  // ---- slot runtime adapters --------------------------------------------

  var SLOT_HOST_SELECTORS = {
    UL: "#card-volleyball [data-bind=body]",
    UR: "#card-video [data-bind=video-body]",
    LL: "#card-ll [data-bind=body]",
    LR: "#card-slideshow [data-bind=slideshow-body]"
  };

  function resolveSlotHost(slotId) {
    var selector = SLOT_HOST_SELECTORS[slotId];
    return selector ? document.querySelector(selector) : null;
  }

  function makeRenderModule(id, supportedSlots, dataDeps, renderer) {
    return {
      id: id,
      contractVersion: 1,
      supportedSlots: supportedSlots,
      dataDeps: dataDeps,
      select: function (slice) {
        return dataDeps.length === 1 ? slice[dataDeps[0]] : slice;
      },
      mount: function () {
        return {};
      },
      update: function (ctx, input) {
        renderer(ctx.host, input);
      },
      unmount: function (ctx) {
        clear(ctx.host);
      }
    };
  }

  function createSlotRegistry() {
    var euroModules = window.PedroEuroScheduleModules || {};
    var registry = {
      legacy: {
        id: "legacy",
        contractVersion: 1,
        supportedSlots: ["UL", "UR", "LL", "LR"],
        dataDeps: [],
        mount: function () { return {}; },
        update: function (ctx) {
          emptyMsg(ctx.host, "Moduł slotu jest wyłączony.");
        },
        unmount: function (ctx) { clear(ctx.host); }
      },
      volleyball: makeRenderModule("volleyball", ["UL"], ["volleyball"], renderVB),
      "polsat-status": makeRenderModule("polsat-status", ["UR"], ["media"], renderVideo),
      birdwatch: makeRenderModule("birdwatch", ["LL"], ["ll_tbd"], renderTBD),
      photos: makeRenderModule("photos", ["LR"], ["media"], renderSlideshow)
    };
    if (euroModules.polandEuroSchedule) registry["poland-euro-schedule"] = euroModules.polandEuroSchedule;
    if (euroModules.euroDailySchedule) registry["euro-daily-schedule"] = euroModules.euroDailySchedule;
    return registry;
  }

  function renderLegacySlotState(state) {
    // Compatibility path only: if slot-runtime.js itself is unavailable,
    // preserve the exact pre-runtime render ordering and card hosts.
    var w = (state && state.widgets) || {};
    var ul = resolveSlotHost("UL");
    var ur = resolveSlotHost("UR");
    var ll = resolveSlotHost("LL");
    var lr = resolveSlotHost("LR");
    if (ul) renderVB(ul, w.volleyball);
    if (ur) renderVideo(ur, w.media);
    if (ll) renderTBD(ll, w.ll_tbd);
    if (lr) renderSlideshow(lr, w.media);
  }

  function buildSlotRuntime(layout) {
    if (!window.PedroSlotRuntime) return null;
    try {
      var runtime = window.PedroSlotRuntime.create({
        layout: layout,
        registry: createSlotRegistry(),
        hostResolver: function (slotId) {
          return resolveSlotHost(slotId);
        },
        reportError: function (slotId, moduleId, error) {
          console.warn("slot failed:", slotId, moduleId, error);
        },
        renderError: function (host, slotId, moduleId, error) {
          errorMsg(host, moduleId + ": " + publicErrorText(error));
        }
      });
      document.body.setAttribute("data-slot-layout", runtime.getLayout().revision);
      return runtime;
    } catch (e) {
      console.warn("slot layout rejected; using legacy render path:", e);
      return null;
    }
  }

  function ensureSlotRuntime() {
    if (slotRuntimePromise) return slotRuntimePromise;
    slotRuntimePromise = safeFetch(SLOT_LAYOUT_URL).then(function (layout) {
      slotRuntime = buildSlotRuntime(layout || SLOT_LAYOUT_FALLBACK);
      if (!slotRuntime) {
        // The runtime asset can be absent during a cache race. The direct
        // renderer below is deliberately kept as a bounded compatibility
        // fallback; it is not the module-selection path.
        document.body.setAttribute("data-slot-layout", "legacy-fallback");
      }
      return slotRuntime;
    });
    return slotRuntimePromise;
  }

  // Left-column cards remain shell-owned direct renderers. The four
  // center/right cards are now selected by slot-layout.json through the
  // allowlisted runtime above.
  function renderCard(name, node, widget) {
    try {
      switch (name) {
        case "weather":  return renderWeather(node, widget);
        case "route":    return renderRoute(node, widget);
        case "calendar": return renderCalendar(node, widget);
        case "alerts":   return renderAlerts(node, widget);
      }
    } catch (e) {
      console.warn("render failed:", name, e);
      errorMsg(node, e && e.message ? e.message : String(e));
    }
  }

  function applyState(state) {
    if (!state || !state.widgets) return;
    var w = state.widgets;
    // URL/localStorage override wins over the state-driven skin so a
    // user (or a tester) can preview a skin without changing server state.
    var urlSkin = applyUrlSkinOverride();
    if (!urlSkin) applySkin(w.skin);
    else {
      // Still keep mode/label attributes for downstream consumers.
      var data = (w.skin && w.skin.data) || {};
      document.body.setAttribute("data-skin-mode", data.mode || "manual");
      document.body.setAttribute("data-skin-label", urlSkin);
    }

    var pairs = [
      ["weather",  "#card-weather"],
      ["route",    "#card-route"],
      ["calendar", "#card-calendar"],
      ["alerts",   "#card-alerts"]
    ];
    pairs.forEach(function (p) {
      var node = document.querySelector(p[1] + " [data-bind=body]");
      if (node) renderCard(p[0], node, w[p[0]]);
    });

    if (slotRuntime) slotRuntime.update(state);
    else renderLegacySlotState(state);

    // Fullscreen slideshow and rotation policy stay shell-owned. The LR
    // module only owns the ordinary slideshow card body.
    renderFullscreenSlideshow(w.media);
    updateDisplayRotation(w.media);
    renderTicker(w);
  }

  // ---- clock / passive ticker ------------------------------------------

  function tickClock() {
    var d = new Date();
    function pad(n) { return (n < 10 ? "0" : "") + n; }
    var days = ["niedz.", "pon.", "wt.", "śr.", "czw.", "pt.", "sob."];
    var t = pad(d.getHours()) + ":" + pad(d.getMinutes()) + " • " + days[d.getDay()] + " " + pad(d.getDate()) + "." + pad(d.getMonth() + 1);
    setText(document.getElementById("bottom-clock"), t);
  }

  // ---- loop -------------------------------------------------------------

  async function safeFetch(url) {
    try {
      var r = await fetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      return await r.json();
    } catch (e) {
      console.warn("fetch failed:", url, e);
      return null;
    }
  }

  async function loop() {
    var state = await safeFetch(STATE_URL);
    if (!state) return;
    await ensureSlotRuntime();
    applyState(state);
  }


  // Hermes Oracle: add 4 corner ornaments + ornamental side accents to
  // every .card when the active skin is "oracle". Pure DOM, no React.
  // The ornaments inherit the same pointer-events:none and are layered
  // between the .card::before/::after rings and the content.
  function applyOracleOrnaments() {
    if (document.body.getAttribute("data-skin") !== "oracle") return;
    if (document.body.hasAttribute("data-ornaments-applied")) return;
    document.body.setAttribute("data-ornaments-applied", "1");

    var cards = document.querySelectorAll(".card");
    cards.forEach(function (card) {
      if (card.querySelector(":scope > .oracle-corner")) return;
      ["tl", "tr", "bl", "br"].forEach(function (pos) {
        var c = document.createElement("div");
        c.className = "oracle-corner oracle-corner--" + pos;
        c.setAttribute("aria-hidden", "true");
        card.appendChild(c);
      });
    });
  }

  function start() {
    setDisplayMode("dashboard");
    tickClock();
    setInterval(tickClock, 30000);
    applyOracleOrnaments();
    loop();
    setInterval(loop, REFRESH_MS);
  }

  // Skin can change at runtime (e.g. via ?skin= override or set-skin).
  // Re-apply ornaments when the body data-skin attribute changes.
  try {
    new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        if (mutations[i].attributeName === "data-skin") {
          if (document.body.getAttribute("data-skin") === "oracle") {
            document.body.removeAttribute("data-ornaments-applied");
            applyOracleOrnaments();
          } else {
            document.body.removeAttribute("data-ornaments-applied");
          }
        }
      }
    }).observe(document.body, { attributes: true, attributeFilter: ["data-skin"] });
  } catch (e) {}

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
