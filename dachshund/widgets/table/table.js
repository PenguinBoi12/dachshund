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

  const buildTable = (columns, rows, withActions, pageSize) => {
    const table = document.createElement("table");
    const head = document.createElement("tr");

    columns.forEach((column) => {
      const th = document.createElement("th");
      th.textContent = column;
      head.appendChild(th);
    });

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
    for (let i = rows.length; i < pageSize; i++) {
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

  // The server paginates with forward-only cursors: `payload` is always one
  // page plus the cursor for the next one, never a total. `state.history`
  // holds the cursors already visited, so "‹" can step back without the
  // server needing to support reverse pagination at all.
  const paint = (state, cursor, payload) => {
    const columns = payload.columns ?? [];
    const rows = payload.rows ?? [];
    const withActions = rows.some((row) => row.actions?.length);

    state.cursor = cursor;
    state.nextCursor = payload.next_cursor ?? null;

    state.container.replaceChildren(
      buildTable(columns, rows, withActions, payload.page_size ?? rows.length),
    );

    state.prev.disabled = state.history.length === 0;
    state.next.disabled = state.nextCursor == null;
    state.nav.hidden = state.prev.disabled && state.next.disabled;
  };

  const fetchPage = async (state, cursor) => {
    const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
    const response = await fetch(`/_widgets/${state.name}/page${query}`);
    paint(state, cursor, await response.json());
  };

  const pager = (state) => {
    const nav = document.createElement("div");
    nav.className = "table-pager";

    const prev = document.createElement("button");
    prev.type = "button";
    prev.textContent = "‹";
    prev.addEventListener("click", () => fetchPage(state, state.history.pop()));

    const next = document.createElement("button");
    next.type = "button";
    next.textContent = "›";
    next.addEventListener("click", () => {
      state.history.push(state.cursor);
      fetchPage(state, state.nextCursor);
    });

    nav.append(prev, next);

    state.nav = nav;
    state.prev = prev;
    state.next = next;

    return nav;
  };

  window.Dachshund.widget("table", {
    mount(card, payload) {
      const container = card.querySelector(".card-content");
      container.classList.add("table");

      const state = { container, name: card.dataset.widget, history: [] };

      card.appendChild(pager(state));
      paint(state, null, payload);

      return state;
    },
    // A live update carries no row data, just a signal to refetch the page
    // currently on screen; the response's own `next_cursor` may differ if
    // the table shrank, same as `paint` always trusting it.
    replace(state) {
      fetchPage(state, state.cursor);
    },
  });
})();
