/* Pedro Dashboard — replaceable slot runtime (v1).
 * No dynamic imports. The shell supplies hosts and an allowlisted registry.
 * CommonJS export exists only for deterministic Node contract tests.
 */
(function (root, factory) {
  "use strict";
  var api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PedroSlotRuntime = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  "use strict";

  var SLOT_IDS = Object.freeze(["UL", "UR", "LL", "LR"]);

  function hasOwn(obj, key) {
    return Object.prototype.hasOwnProperty.call(obj, key);
  }

  function copyAssignment(raw) {
    return {
      module: String(raw.module),
      enabled: raw.enabled !== false
    };
  }

  function validateLayout(layout, registry) {
    if (!layout || typeof layout !== "object") {
      throw new Error("slot layout must be an object");
    }
    if (layout.schema_version !== 1) {
      throw new Error("unsupported slot layout schema_version");
    }
    if (layout.engine !== "slots-v1") {
      throw new Error("unsupported slot layout engine");
    }
    if (!layout.revision || typeof layout.revision !== "string") {
      throw new Error("slot layout revision is required");
    }
    if (!layout.slots || typeof layout.slots !== "object") {
      throw new Error("slot layout slots are required");
    }

    var errors = [];
    Object.keys(layout.slots).forEach(function (slotId) {
      if (SLOT_IDS.indexOf(slotId) < 0) errors.push("unknown slot " + slotId);
    });

    var normalized = {
      schema_version: 1,
      engine: "slots-v1",
      revision: layout.revision,
      slots: {}
    };

    SLOT_IDS.forEach(function (slotId) {
      var raw = layout.slots[slotId];
      if (!raw || typeof raw !== "object") {
        errors.push("missing assignment for " + slotId);
        return;
      }

      /* A disabled slot intentionally resolves to the local fallback. It does
       * not need a module entry because it must not run module code. */
      if (raw.enabled === false) {
        normalized.slots[slotId] = { module: "legacy", enabled: false };
        return;
      }

      if (!raw.module || typeof raw.module !== "string") {
        errors.push("missing module for " + slotId);
        return;
      }
      var moduleDef = registry && hasOwn(registry, raw.module)
        ? registry[raw.module]
        : null;
      if (!moduleDef) {
        errors.push("unknown module " + raw.module + " for " + slotId);
        return;
      }
      if (!Array.isArray(moduleDef.supportedSlots) ||
          moduleDef.supportedSlots.indexOf(slotId) < 0) {
        errors.push("module " + raw.module + " does not support " + slotId);
        return;
      }
      normalized.slots[slotId] = copyAssignment(raw);
    });

    if (errors.length) {
      throw new Error("invalid slot layout: " + errors.join("; "));
    }
    return normalized;
  }

  function makeAbortController() {
    if (typeof AbortController === "function") return new AbortController();

    var aborted = false;
    var listeners = [];
    var signal = {
      get aborted() { return aborted; },
      addEventListener: function (type, fn) {
        if (type === "abort" && typeof fn === "function") listeners.push(fn);
      },
      removeEventListener: function (type, fn) {
        if (type !== "abort") return;
        listeners = listeners.filter(function (x) { return x !== fn; });
      }
    };
    return {
      signal: signal,
      abort: function () {
        if (aborted) return;
        aborted = true;
        listeners.slice().forEach(function (fn) {
          try { fn.call(signal); } catch (e) {}
        });
      }
    };
  }

  function clearHost(host) {
    if (!host) return;
    if (typeof host.replaceChildren === "function") {
      host.replaceChildren();
      return;
    }
    while (host.firstChild) host.removeChild(host.firstChild);
  }

  function create(options) {
    options = options || {};
    var registry = options.registry || {};
    var layout = validateLayout(options.layout, registry);
    var hostResolver = options.hostResolver;
    if (typeof hostResolver !== "function") {
      throw new Error("slot runtime hostResolver is required");
    }

    var mounted = Object.create(null);
    var generationBySlot = Object.create(null);
    var destroyed = false;
    var services = options.services || {};

    function reportError(slotId, moduleId, error) {
      if (typeof options.reportError === "function") {
        options.reportError(slotId, moduleId, error);
        return;
      }
      if (root && root.console && typeof root.console.warn === "function") {
        root.console.warn("slot module failed:", slotId, moduleId, error);
      }
    }

    function renderError(host, slotId, moduleId, error) {
      if (typeof options.renderError === "function") {
        try { options.renderError(host, slotId, moduleId, error); } catch (renderErr) {
          reportError(slotId, moduleId, renderErr);
        }
      }
    }

    function selectInput(moduleDef, state, slotId) {
      var widgets = (state && state.widgets) || {};
      var deps = Array.isArray(moduleDef.dataDeps) ? moduleDef.dataDeps : [];
      var slice = {};
      deps.forEach(function (dep) { slice[dep] = widgets[dep]; });
      if (typeof moduleDef.select === "function") {
        return moduleDef.select(slice, { slotId: slotId, services: services });
      }
      return deps.length === 1 ? slice[deps[0]] : slice;
    }

    function makeContext(slotId, record) {
      return {
        slotId: slotId,
        host: record.host,
        services: services,
        signal: record.controller.signal,
        generation: record.generation,
        isCurrent: function () {
          return !destroyed &&
            mounted[slotId] === record &&
            record.generation === generationBySlot[slotId] &&
            !record.controller.signal.aborted;
        },
        reportError: function (error) {
          reportError(slotId, record.moduleId, error);
        }
      };
    }

    function unmountRecord(record) {
      if (!record) return;
      try { record.controller.abort(); } catch (e) {}
      try {
        if (record.module && typeof record.module.unmount === "function") {
          record.module.unmount(record.context, record.instance);
        }
      } catch (e) {
        reportError(record.slotId, record.moduleId, e);
      } finally {
        clearHost(record.host);
      }
    }

    function mountRecord(slotId, moduleId, host) {
      var moduleDef = registry[moduleId] || registry.legacy;
      if (!moduleDef) {
        reportError(slotId, moduleId, new Error("missing legacy fallback"));
        return null;
      }
      var controller = makeAbortController();
      var generation = (generationBySlot[slotId] || 0) + 1;
      generationBySlot[slotId] = generation;
      var record = {
        slotId: slotId,
        moduleId: moduleId,
        module: moduleDef,
        host: host,
        generation: generation,
        controller: controller,
        instance: null,
        failed: false,
        context: null
      };
      record.context = makeContext(slotId, record);
      mounted[slotId] = record;
      try {
        record.instance = typeof moduleDef.mount === "function"
          ? (moduleDef.mount(record.context) || {})
          : {};
      } catch (e) {
        record.failed = true;
        reportError(slotId, moduleId, e);
        renderError(host, slotId, moduleId, e);
      }
      return record;
    }

    function updateSlot(slotId, state) {
      var assignment = layout.slots[slotId];
      var host = hostResolver(slotId, assignment);
      var current = mounted[slotId];
      var desiredModuleId = assignment.enabled === false ? "legacy" : assignment.module;

      if (!host) {
        if (current) {
          unmountRecord(current);
          delete mounted[slotId];
        }
        reportError(slotId, desiredModuleId, new Error("slot host not found"));
        return;
      }

      if (!assignment.enabled) {
        if (!current || current.moduleId !== "legacy" || current.host !== host) {
          if (current) {
            unmountRecord(current);
            delete mounted[slotId];
          }
          clearHost(host);
          current = mountRecord(slotId, "legacy", host);
        }
      } else if (!current || current.moduleId !== desiredModuleId || current.host !== host) {
        if (current) {
          unmountRecord(current);
          delete mounted[slotId];
        }
        current = mountRecord(slotId, desiredModuleId, host);
      }

      if (!current || current.failed) return;
      try {
        var input = selectInput(current.module, state, slotId);
        if (typeof current.module.update === "function") {
          current.module.update(current.context, input, current.instance);
        }
      } catch (e) {
        current.failed = true;
        reportError(slotId, current.moduleId, e);
        renderError(current.host, slotId, current.moduleId, e);
      }
    }

    function update(state) {
      if (destroyed) return;
      SLOT_IDS.forEach(function (slotId) {
        try { updateSlot(slotId, state); } catch (e) {
          reportError(slotId, layout.slots[slotId].module, e);
        }
      });
    }

    function setLayout(nextLayout) {
      if (destroyed) throw new Error("slot runtime is destroyed");
      layout = validateLayout(nextLayout, registry);
      return getLayout();
    }

    function getLayout() {
      var slots = {};
      SLOT_IDS.forEach(function (slotId) {
        slots[slotId] = copyAssignment(layout.slots[slotId]);
      });
      return {
        schema_version: layout.schema_version,
        engine: layout.engine,
        revision: layout.revision,
        slots: slots
      };
    }

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      SLOT_IDS.forEach(function (slotId) {
        if (mounted[slotId]) {
          unmountRecord(mounted[slotId]);
          delete mounted[slotId];
        }
      });
    }

    return {
      update: update,
      setLayout: setLayout,
      getLayout: getLayout,
      getMounted: function (slotId) {
        var record = mounted[slotId];
        if (!record) return null;
        return {
          moduleId: record.moduleId,
          generation: record.generation,
          failed: record.failed
        };
      },
      destroy: destroy
    };
  }

  return {
    SLOT_IDS: SLOT_IDS,
    validateLayout: validateLayout,
    create: create
  };
}));
