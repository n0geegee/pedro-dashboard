/* Pedro Dashboard — CEV EuroVolley 2026 slot modules.
 * Vanilla JS, explicit allowlist contracts, no dynamic imports.
 */
(function (root) {
  "use strict";

  var WARSAW = "Europe/Warsaw";
  var STATUS_LABELS = {
    scheduled: "PLAN",
    live: "LIVE",
    finished: "KONIEC",
    postponed: "ODWOŁANY",
    tbd: "TBD"
  };

  function own(obj, key) {
    return Object.prototype.hasOwnProperty.call(obj, key);
  }

  function text(value, fallback) {
    if (value == null || value === "") return fallback || "";
    return String(value);
  }

  function make(doc, tag, className, value) {
    var node = doc.createElement(tag);
    if (className) node.className = className;
    if (value != null) node.textContent = value;
    return node;
  }

  function replaceChildren(node) {
    if (!node) return;
    if (typeof node.replaceChildren === "function") {
      node.replaceChildren();
      return;
    }
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function validTeam(team) {
    return team && typeof team === "object" && text(team.name, "") !== "";
  }

  function normalizeMatch(raw) {
    if (!raw || typeof raw !== "object" || !validTeam(raw.home) || !validTeam(raw.away)) return null;
    var home = {
      name: text(raw.home.name, raw.home.source_name || "?") ,
      code: text(raw.home.code, ""),
      source_name: text(raw.home.source_name, "")
    };
    var away = {
      name: text(raw.away.name, raw.away.source_name || "?") ,
      code: text(raw.away.code, ""),
      source_name: text(raw.away.source_name, "")
    };
    var gender = raw.gender === "K" ? "K" : raw.gender === "M" ? "M" : "";
    if (!gender) return null;
    return {
      id: text(raw.id, gender + "-" + home.code + "-" + away.code),
      gender: gender,
      genderLabel: gender === "K" ? "KOBIETY" : "MĘŻCZYŹNI",
      home: home,
      away: away,
      phase: text(raw.phase, "EuroVolley 2026"),
      round: text(raw.round, ""),
      status: text(raw.status, "scheduled"),
      score: raw.score == null ? "" : text(raw.score, ""),
      date: text(raw.warsaw_date || raw.source_date, ""),
      time: text(raw.warsaw_time || raw.source_time, "--:--"),
      sourceTime: text(raw.source_time, ""),
      sourceDate: text(raw.source_date, ""),
      sourceUrl: text(raw.source && raw.source.url, ""),
      startAt: text(raw.start_at, "")
    };
  }

  function sortMatches(a, b) {
    var ad = a.startAt || (a.date + "T" + a.time);
    var bd = b.startAt || (b.date + "T" + b.time);
    return String(ad).localeCompare(String(bd)) || a.gender.localeCompare(b.gender) || a.id.localeCompare(b.id);
  }

  function dedupeAndSort(rows) {
    var seen = Object.create(null);
    var result = [];
    (Array.isArray(rows) ? rows : []).forEach(function (raw) {
      var row = normalizeMatch(raw);
      if (!row || seen[row.id]) return;
      seen[row.id] = true;
      result.push(row);
    });
    return result.sort(sortMatches);
  }

  function normalizeWidget(widget, mode) {
    var envelope = widget && typeof widget === "object" ? widget : {};
    var data = envelope.data && typeof envelope.data === "object" ? envelope.data : {};
    var rows;
    var days = [];
    if (mode === "poland") {
      rows = dedupeAndSort(data.poland_matches);
    } else {
      if (Array.isArray(data.days)) {
        data.days.forEach(function (day) {
          if (!day || typeof day !== "object") return;
          var dayRows = dedupeAndSort(day.matches);
          if (dayRows.length) days.push({ date: text(day.date, dayRows[0].date), matches: dayRows });
        });
      }
      if (!days.length) {
        rows = dedupeAndSort(data.matches);
        if (rows.length) days = [{ date: rows[0].date, matches: rows }];
      }
    }
    return {
      status: text(envelope.status, "empty"),
      refreshStatus: text(data.freshness && data.freshness.refresh_status, ""),
      selectedDate: text(data.selected_date, ""),
      updatedAt: text(envelope.updated_at || data.freshness && data.freshness.retrieved_at, ""),
      timezone: text(data.timezone, WARSAW),
      rows: rows || [],
      days: days,
      sourceCount: Number(data.freshness && data.freshness.source_match_count) || 0
    };
  }

  function dateLabel(isoDate, selectedDate) {
    if (!isoDate) return "TERMIN";
    var parts = isoDate.split("-");
    var shortDate = parts.length === 3 ? parts[2] + "." + parts[1] : isoDate;
    return isoDate === selectedDate ? "DZIŚ · " + shortDate : shortDate;
  }

  function statusLabel(row) {
    if (row.score) return row.score;
    return STATUS_LABELS[row.status] || row.status.toUpperCase();
  }

  function statusClass(row) {
    if (row.score || row.status === "finished") return "euro-schedule__status--finished";
    if (row.status === "live") return "euro-schedule__status--live";
    if (row.status === "postponed") return "euro-schedule__status--postponed";
    return "euro-schedule__status--scheduled";
  }

  function appendHeader(doc, rootNode, title, model) {
    var head = make(doc, "div", "euro-schedule__intro");
    head.appendChild(make(doc, "div", "euro-schedule__kicker", title));
    var freshness = model.status === "stale" || model.refreshStatus === "cached_after_probe_error"
      ? "CEV · DANE NIEŚWIEŻE"
      : model.status === "ok" ? "CEV · OFICJALNY FEED" : "CEV · BRAK DANYCH";
    head.appendChild(make(doc, "div", "euro-schedule__freshness", freshness));
    rootNode.appendChild(head);
  }

  function appendRow(doc, parent, row) {
    var item = make(doc, "div", "euro-schedule__row");
    item.setAttribute("data-gender", row.gender);
    item.appendChild(make(doc, "div", "euro-schedule__time", row.time + " PL"));
    var match = make(doc, "div", "euro-schedule__match");
    var teams = make(doc, "div", "euro-schedule__teams");
    teams.appendChild(make(doc, "span", "euro-schedule__team euro-schedule__team--home", row.home.name));
    teams.appendChild(make(doc, "span", "euro-schedule__versus", "—"));
    teams.appendChild(make(doc, "span", "euro-schedule__team euro-schedule__team--away", row.away.name));
    match.appendChild(teams);
    var meta = make(doc, "div", "euro-schedule__meta");
    meta.appendChild(make(doc, "span", "euro-schedule__gender", row.gender));
    meta.appendChild(make(doc, "span", "euro-schedule__phase", row.phase));
    match.appendChild(meta);
    item.appendChild(match);
    item.appendChild(make(doc, "div", "euro-schedule__status " + statusClass(row), statusLabel(row)));
    parent.appendChild(item);
  }

  function appendEmpty(doc, parent, message) {
    parent.appendChild(make(doc, "p", "euro-schedule__empty", message));
  }

  function renderPoland(rootNode, model) {
    var doc = rootNode.ownerDocument;
    replaceChildren(rootNode);
    appendHeader(doc, rootNode, "POLSKA · EUROVOLLEY 2026", model);
    if (!model.rows.length) {
      appendEmpty(doc, rootNode, "Brak potwierdzonego terminarza Polski w oficjalnym feedzie CEV.");
      return;
    }
    var groups = { K: [], M: [] };
    model.rows.forEach(function (row) { if (own(groups, row.gender)) groups[row.gender].push(row); });
    ["K", "M"].forEach(function (gender) {
      if (!groups[gender].length) return;
      var section = make(doc, "section", "euro-schedule__gender-section");
      section.appendChild(make(doc, "h3", "euro-schedule__section-title", gender === "K" ? "KOBIETY (K)" : "MĘŻCZYŹNI (M)"));
      groups[gender].forEach(function (row) { appendRow(doc, section, row); });
      rootNode.appendChild(section);
    });
  }

  function renderDaily(rootNode, model) {
    var doc = rootNode.ownerDocument;
    replaceChildren(rootNode);
    appendHeader(doc, rootNode, "EUROVOLLEY 2026 · MECZE DNIA", model);
    if (!model.days.length) {
      appendEmpty(doc, rootNode, "Brak konkretnych meczów w aktualnym oficjalnym feedzie CEV.");
      return;
    }
    model.days.forEach(function (day) {
      var section = make(doc, "section", "euro-schedule__day");
      section.appendChild(make(doc, "h3", "euro-schedule__day-title", dateLabel(day.date, model.selectedDate)));
      day.matches.forEach(function (row) { appendRow(doc, section, row); });
      rootNode.appendChild(section);
    });
  }

  function mountModule(className) {
    return function (ctx) {
      var doc = ctx.host.ownerDocument || root.document;
      var rootNode = make(doc, "div", "euro-schedule " + className);
      replaceChildren(ctx.host);
      ctx.host.appendChild(rootNode);
      return { root: rootNode, disposed: false };
    };
  }

  function unmountModule(ctx, instance) {
    if (!instance || instance.disposed) return;
    instance.disposed = true;
    if (instance.root && instance.root.parentNode === ctx.host) instance.root.parentNode.removeChild(instance.root);
  }

  function makeModule(id, slot, mode, className, renderer) {
    return {
      id: id,
      contractVersion: 1,
      supportedSlots: [slot],
      dataDeps: ["eurovolley"],
      select: function (slice) {
        return normalizeWidget(slice && slice.eurovolley, mode);
      },
      mount: mountModule(className),
      update: function (ctx, input, instance) {
        if (!instance || instance.disposed || (ctx.isCurrent && !ctx.isCurrent())) return;
        renderer(instance.root, input || normalizeWidget(null, mode));
      },
      unmount: unmountModule
    };
  }

  var modules = {
    polandEuroSchedule: makeModule("poland-euro-schedule", "UL", "poland", "euro-schedule--poland", renderPoland),
    euroDailySchedule: makeModule("euro-daily-schedule", "LL", "daily", "euro-schedule--daily", renderDaily)
  };

  // Expose pure selectors for deterministic tests without exposing DOM helpers.
  modules.normalizePoland = function (widget) { return normalizeWidget(widget, "poland"); };
  modules.normalizeDaily = function (widget) { return normalizeWidget(widget, "daily"); };
  root.PedroEuroScheduleModules = modules;
}(typeof globalThis !== "undefined" ? globalThis : this));
