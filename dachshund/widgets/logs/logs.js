(() => {
  "use strict";

  const LEVELS = [
    ["DEBUG", 10],
    ["INFO", 20],
    ["WARNING", 30],
    ["ERROR", 40],
    ["CRITICAL", 50],
  ];
  const SEARCH_DELAY = 250;

  const span = (className, text) => {
    const element = document.createElement("span");
    element.className = className;
    element.textContent = text;
    return element;
  };

  const two = (number) => String(number).padStart(2, "0");

  // HH:MM:SS whatever the browser's locale, so it fits its column.
  const time = (seconds) => {
    if (seconds == null) return "";

    const at = new Date(seconds * 1000);
    return `${two(at.getHours())}:${two(at.getMinutes())}:${two(at.getSeconds())}`;
  };

  // textContent throughout: log lines are application text, never markup.
  const line = (fields) => {
    const row = document.createElement("div");
    const level = span("logs-level", fields.level ?? "");

    row.className = "logs-line";
    level.dataset.level = fields.level ?? "";
    row.append(
      span("logs-time", time(fields.time)),
      level,
      span("logs-logger", fields.logger ?? ""),
      span("logs-message", fields.message ?? ""),
    );

    if (!fields.exception) return [row];

    const trace = document.createElement("pre");
    trace.className = "logs-exception";
    trace.textContent = fields.exception;
    trace.hidden = true;
    row.classList.add("expandable");
    row.title = "Show the traceback";
    row.addEventListener("click", () => {
      trace.hidden = !trace.hidden;
    });

    return [row, trace];
  };

  const name = (number) =>
    LEVELS.find(([, value]) => value === number)?.[0] ?? String(number);

  // One toggle per captured level. None picked means all of them, so every
  // toggle shows pressed.
  const drawToggles = (state) => {
    state.toggles.replaceChildren(
      ...state.offered.map((number) => {
        const toggle = button(name(number), () => flip(state, number));
        const pressed = state.levels.size === 0 || state.levels.has(number);

        toggle.className = "logs-toggle";
        toggle.dataset.level = name(number);
        toggle.setAttribute("aria-pressed", String(pressed));

        return toggle;
      }),
    );
  };

  // Turning every level on, or the last one off, goes back to all of them.
  const flip = (state, number) => {
    const shown = new Set(state.levels.size ? state.levels : state.offered);

    if (shown.has(number)) {
      shown.delete(number);
    } else {
      shown.add(number);
    }

    const all = shown.size === 0 || shown.size === state.offered.length;
    state.levels = all ? new Set() : shown;
    state.offset = 0;
    drawToggles(state);
    fetchPage(state);
  };

  const paint = (state, payload) => {
    const rows = payload.rows ?? [];
    const total = payload.total ?? rows.length;

    state.offset = payload.offset ?? 0;
    state.limit = payload.limit ?? rows.length;
    state.search.hidden = !payload.search;

    const offered = payload.levels ?? [];

    if (offered.join() !== state.offered.join()) {
      state.offered = offered;
      drawToggles(state);
    }

    if (rows.length) {
      state.container.replaceChildren(...rows.flatMap((row) => line(row.fields ?? {})));
    } else {
      state.container.replaceChildren(span("logs-empty", "No lines yet."));
    }

    // Back to the newest line.
    state.container.scrollTop = 0;

    const shown = rows.length ? `${state.offset + 1}–${state.offset + rows.length}` : "0";
    state.count.textContent = `${shown} of ${total}`;
    state.prev.disabled = state.offset === 0;
    state.next.disabled = state.offset + rows.length >= total;
  };

  const fetchPage = async (state) => {
    const params = new URLSearchParams({
      offset: state.offset,
      limit: state.limit,
    });

    for (const number of state.levels) params.append("level", number);

    if (state.query) params.set("search", state.query);

    const response = await fetch(`/_widgets/${state.name}/page?${params}`);
    paint(state, await response.json());
  };

  const button = (text, onClick) => {
    const element = document.createElement("button");
    element.type = "button";
    element.textContent = text;
    element.addEventListener("click", onClick);
    return element;
  };

  const controls = (state) => {
    const bar = document.createElement("div");
    const toggles = document.createElement("div");
    const search = document.createElement("input");
    let timer;

    bar.className = "logs-controls";
    toggles.className = "logs-toggles";
    toggles.setAttribute("role", "group");
    toggles.setAttribute("aria-label", "Levels shown");

    search.type = "search";
    search.placeholder = "Search";
    search.setAttribute("aria-label", "Search");
    search.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        state.query = search.value.trim();
        state.offset = 0;
        fetchPage(state);
      }, SEARCH_DELAY);
    });

    const pause = button("Pause", () => {
      state.paused = !state.paused;
      pause.setAttribute("aria-pressed", String(state.paused));
      pause.textContent = state.paused ? "Resume" : "Pause";

      if (!state.paused) fetchPage(state);
    });
    pause.setAttribute("aria-pressed", "false");

    bar.append(toggles, search, pause);
    state.toggles = toggles;
    state.search = search;

    return bar;
  };

  const pager = (state) => {
    const nav = document.createElement("div");
    nav.className = "logs-pager";

    state.count = document.createElement("span");
    state.prev = button("‹", () => {
      state.offset = Math.max(0, state.offset - state.limit);
      fetchPage(state);
    });
    state.next = button("›", () => {
      state.offset += state.limit;
      fetchPage(state);
    });

    nav.append(state.count, state.prev, state.next);
    return nav;
  };

  window.Dachshund.widget("logs", {
    mount(card, payload) {
      const container = card.querySelector(".card-content");
      container.classList.add("logs");

      const state = {
        container,
        name: card.dataset.widget,
        query: "",
        levels: new Set(),
        offered: [],
        offset: 0,
        limit: payload.limit,
        paused: false,
      };

      card.insertBefore(controls(state), container);
      card.appendChild(pager(state));
      paint(state, payload);

      return state;
    },
    // A new line only signals a refetch, held while the view is paused.
    replace(state) {
      if (!state.paused) fetchPage(state);
    },
  });
})();
