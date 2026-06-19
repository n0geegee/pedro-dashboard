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
  var REFRESH_MS = 5000;
  var STATE_URL = "/api/state";
  var HEALTH_URL = "/api/health";

  // ---- helpers ----------------------------------------------------------

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function setText(el, txt) { if (el) el.textContent = (txt == null) ? "" : String(txt); }
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
      var ad = String(a.date || "9999-12-31") + " " + String(a.time || "99:99");
      var bd = String(b.date || "9999-12-31") + " " + String(b.time || "99:99");
      return ad.localeCompare(bd);
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
        var date = m.date_human || m.date || "--";
        var tm   = m.time || "";
        var comp = m.competition || "";
        var loc  = m.location || "";
        var sd = parseStartAt(m);
        var st = matchStatus(m, now);
        var plTime = sd ? formatTimeWarsaw(sd) : "";

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

  function renderTBD(node, widget) {
    if (widget && widget.status === "error") return errorMsg(node, widget.error);
    var d = (widget && widget.data) || {};
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
    var root = (widget.data) || {};
    var d = root.slideshow || root;
    var total = d.total || 42;
    var current = Math.max(1, Math.min(total, d.current || 10));

    var imageUrl = d.image_url || d.imageUrl || "";
    var album = d.album || "pedro slideshow";
    var orientation = d.image_orientation || d.orientation || "";
    // Build a class suffix so the CSS can pick cover vs contain per orientation.
    // Landscape and square keep the default cover behaviour. Portrait switches
    // to contain so the full image is visible inside the card box (with a
    // black letterbox on the sides) — without this, cover crops the top and
    // bottom of any vertical photo, which looks like "missing centre".
    var photoClass = "slideshow__photo slideshow__photo--image";
    if (orientation === "portrait") {
      photoClass += " slideshow__photo--portrait";
    } else if (orientation === "square") {
      photoClass += " slideshow__photo--square";
    }

    var html = "";
    html += '<div class="slideshow" data-slideshow-current="' + current + '" data-slideshow-total="' + total + '">';
    if (imageUrl) {
      html += '<div class="' + photoClass + '" style="background-image:url(\'' + escAttr(imageUrl) + '\')"></div>';
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
  // name, no "następny:" / "LIVE:" prefix noise. Group letter (K/M) is
  // omitted because all readers already know if they care about men's
  // or women's results.
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

  function renderTicker(widgets) {
    var track = document.getElementById("ticker-track");
    if (!track) return;
    var vb = widgets && widgets.volleyball && widgets.volleyball.data ? widgets.volleyball.data : {};
    var recent = vb.recent_results || {};
    var menResults = Array.isArray(recent.men) ? recent.men : [];
    var womenResults = Array.isArray(recent.women) ? recent.women : [];
    var men = Array.isArray(vb.men) ? vb.men : [];
    var women = Array.isArray(vb.women) ? vb.women : [];
    var items = [];
    var now = nowMs();

    // Order: LIVE (if any) → most recent results (latest first, max 6) →
    // nothing else. We deliberately do NOT show "następny" / "termin"
    // items in the ticker — those belong in the widget above and they
    // were the main source of the noise Jurand reported on 2026-06-18.

    // 1. LIVE matches first. The reader wants to know "who is playing
    //    right now" before anything else.
    var combinedAll = [];
    men.forEach(function (m) { combinedAll.push({ group: "M", match: m }); });
    women.forEach(function (m) { combinedAll.push({ group: "K", match: m }); });
    combinedAll.forEach(function (entry) {
      var st = matchStatus(entry.match, now);
      if (st.status === "LIVE") {
        var s = liveTickerText(Object.assign({}, entry.match, { _group: entry.group }));
        if (s) items.push(s);
      }
    });

    // 2. Recent results. Sort newest → oldest by date desc, take up to 6.
    //    "3:2 (19:25, 18:25, 25:22, 25:21, 15:11)" is the full string
    //    from m.score — but for the ticker we want just the SET COUNT
    //    (e.g. "3:2"), not the per-set breakdown. m.score is currently
    //    "3:2 (19:25, ...)" so we strip the parenthesised breakdown.
    var combinedResults = [];
    menResults.forEach(function (m) { combinedResults.push({ group: "M", match: m }); });
    womenResults.forEach(function (m) { combinedResults.push({ group: "K", match: m }); });
    combinedResults.sort(function (a, b) {
      var ad = (a.match && (a.match.start_at || a.match.date)) || "";
      var bd = (b.match && (b.match.start_at || b.match.date)) || "";
      return String(bd).localeCompare(String(ad));
    });
    combinedResults.slice(0, 6).forEach(function (entry) {
      // Build a synthetic match with just the set count so resultTickerText
      // produces "Polska 3:2 Ukraine" rather than the full per-set dump.
      var m = entry.match || {};
      var trimmed = Object.assign({}, m, {
        _group: entry.group,
        score: (m.home_sets != null && m.away_sets != null)
                 ? (m.home_sets + ":" + m.away_sets)
                 : null
      });
      var s = resultTickerText(trimmed);
      if (s) items.push(s);
    });

    if (!items.length) items.push("Brak wyników ostatnich meczów");
    track.innerHTML = items.map(function (x) { return '<span>' + esc(x) + '</span>'; }).join('');
  }

  // ---- dispatch ---------------------------------------------------------

  function renderCard(name, node, widget) {
    try {
      switch (name) {
        case "weather":    return renderWeather(node, widget);
        case "route":      return renderRoute(node, widget);
        case "calendar":   return renderCalendar(node, widget);
        case "alerts":     return renderAlerts(node, widget);
        case "volleyball": return renderVB(node, widget);
        case "ll_tbd":     return renderTBD(node, widget);
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
      ["weather",    "#card-weather"],
      ["route",      "#card-route"],
      ["calendar",   "#card-calendar"],
      ["alerts",     "#card-alerts"],
      ["volleyball", "#card-volleyball"],
      ["ll_tbd",     "#card-ll"],
    ];
    pairs.forEach(function (p) {
      var node = document.querySelector(p[1] + " [data-bind=body]");
      if (node) renderCard(p[0], node, w[p[0]]);
    });

    // media widget renders into BOTH video and slideshow body
    var videoNode = document.querySelector("#card-video [data-bind=video-body]");
    var slideNode = document.querySelector("#card-slideshow [data-bind=slideshow-body]");
    if (videoNode) renderVideo(videoNode, w.media);
    if (slideNode) renderSlideshow(slideNode, w.media);
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
    if (state) applyState(state);
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
