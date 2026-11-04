(() => {
  "use strict";

  const cell = (value) => {
    const td = document.createElement("td");
    td.textContent = value == null ? "—" : String(value);
    return td;
  };

  const actionButton = (action, fields) => {
    const button = document.createElement("button");

    button.dataset.action = action.name;
    button.dataset.confirm = String(action.confirm);
    button.dataset.args = JSON.stringify({ ...action.args, ...fields });
    button.textContent = action.label;

    return button;
  };

  const SEARCH_DELAY = 250;

  const header = (state, column, sortable) => {
    const th = document.createElement("th");

    if (!sortable.includes(column)) {
      th.textContent = column;
      return th;
    }

    const button = document.createElement("button");
    const sorted = state.sortBy === column;
    button.type = "button";
    button.textContent = column + (sorted ? (state.descending ? " ▼" : " ▲") : "");
    button.addEventListener("click", () => {
      if (!sorted) {
        state.sortBy = column;
        state.descending = false;
      } else if (!state.descending) {
        state.descending = true;
      } else {
        state.sortBy = null;
        state.descending = false;
      }

      state.offset = 0;
      fetchPage(state);
    });

    th.setAttribute(
      "aria-sort",
      sorted ? (state.descending ? "descending" : "ascending") : "none",
    );
    th.appendChild(button);
    return th;
  };

  const buildTable = (state, payload) => {
    const columns = payload.columns ?? [];
    const rows = payload.rows ?? [];
    const sortable = payload.sortable ?? [];
    const withActions = rows.some((row) => row.actions?.length);
    const table = document.createElement("table");
    const head = document.createElement("tr");

    columns.forEach((column) => head.appendChild(header(state, column, sortable)));

    if (withActions) {
      head.appendChild(document.createElement("th"));
    }

    const thead = document.createElement("thead");
    thead.appendChild(head);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");

    rows.forEach((row) => {
      const tr = document.createElement("tr");

      columns.forEach((column) => tr.appendChild(cell(row.fields?.[column])));

      if (withActions) {
        const td = document.createElement("td");
        td.className = "table-row-actions";
        (row.actions ?? []).forEach((action) =>
          td.appendChild(actionButton(action, row.fields ?? {})),
        );
        tr.appendChild(td);
      }

      tbody.appendChild(tr);
    });

    // Padded to a full page, so a shorter last page doesn't resize the
    // card against its neighbours as you page through.
    for (let i = rows.length; i < (payload.limit ?? rows.length); i++) {
      const tr = document.createElement("tr");
      tr.className = "table-filler-row";

      columns.forEach(() => tr.appendChild(document.createElement("td")));

      if (withActions) {
        tr.appendChild(document.createElement("td"));
      }

      tbody.appendChild(tr);
    }

    table.appendChild(tbody);
    return table;
  };

  // Without a total, a full page means there may be more, so "›" stays on
  // until a short page comes back.
  const paint = (state, payload) => {
    const rows = payload.rows ?? [];
    const total = payload.total ?? null;

    state.offset = payload.offset ?? 0;
    state.limit = payload.limit ?? rows.length;
    state.search.hidden = !payload.search;

    state.container.replaceChildren(buildTable(state, payload));

    const shown = rows.length
      ? `${state.offset + 1}–${state.offset + rows.length}`
      : "0";
    state.count.textContent = total == null ? shown : `${shown} of ${total}`;

    state.prev.disabled = state.offset === 0;
    state.next.disabled =
      total == null
        ? rows.length < state.limit
        : state.offset + rows.length >= total;
  };

  const fetchPage = async (state) => {
    const params = new URLSearchParams({
      offset: state.offset,
      limit: state.limit,
    });

    if (state.query) params.set("search", state.query);
    if (state.sortBy) params.set("sort", state.sortBy);
    if (state.descending) params.set("dir", "desc");

    const response = await fetch(`/_widgets/${state.name}/page?${params}`);
    paint(state, await response.json());
  };

  const searchBox = (state) => {
    const input = document.createElement("input");
    let timer;

    input.type = "search";
    input.className = "table-search";
    input.placeholder = "Search";
    input.setAttribute("aria-label", "Search");
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        state.query = input.value.trim();
        state.offset = 0;
        fetchPage(state);
      }, SEARCH_DELAY);
    });

    return input;
  };

  const pager = (state) => {
    const nav = document.createElement("div");
    nav.className = "table-pager";

    const count = document.createElement("span");
    count.className = "table-count";

    const prev = document.createElement("button");
    prev.type = "button";
    prev.textContent = "‹";
    prev.addEventListener("click", () => {
      state.offset = Math.max(0, state.offset - state.limit);
      fetchPage(state);
    });

    const next = document.createElement("button");
    next.type = "button";
    next.textContent = "›";
    next.addEventListener("click", () => {
      state.offset += state.limit;
      fetchPage(state);
    });

    nav.append(count, prev, next);

    state.count = count;
    state.prev = prev;
    state.next = next;

    return nav;
  };

  window.Dachshund.widget("table", {
    mount(card, payload) {
      const container = card.querySelector(".card-content");
      container.classList.add("table");

      const state = {
        container,
        name: card.dataset.widget,
        query: "",
        sortBy: payload.sort_by ?? null,
        descending: payload.descending ?? false,
        offset: 0,
        limit: payload.limit,
      };

      state.search = searchBox(state);
      card.insertBefore(state.search, container);
      card.appendChild(pager(state));
      paint(state, payload);

      return state;
    },
    // A live update carries no row data, just a signal to refetch the page
    // on screen with the current search, sort and offset.
    replace(state) {
      fetchPage(state);
    },
  });
})();
