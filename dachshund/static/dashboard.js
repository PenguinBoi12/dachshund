(() => {
  "use strict";

  const POINTS = 500;
  const RECONNECT_DELAY = 2000;
  const PALETTE = 8;

  const token = (name) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  // Colours follow the series, never its rank, so a chart keeps its identity
  // however many lines it draws.
  const colour = (index) =>
    index < PALETTE ? token(`--series-${index + 1}`) : token("--text-muted");

  const translucent = (color, alpha) => {
    const hex = color.replace("#", "");
    const value = parseInt(
      hex.length === 3
        ? hex
            .split("")
            .map((c) => c + c)
            .join("")
        : hex,
      16,
    );

    const r = (value >> 16) & 255;
    const g = (value >> 8) & 255;
    const b = value & 255;

    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  };

  const number = (value) => (Number.isInteger(value) ? value : value.toFixed(2));

  const swatch = (index) => {
    const mark = document.createElement("span");

    mark.className = "legend-swatch";
    mark.style.background = colour(index);

    return mark;
  };

  // Appended to the card rather than the plot box, so it can never land on
  // the axis labels uPlot draws at the bottom of its own canvas.
  const legend = (card, names) => {
    if (names.length < 2) {
      return;
    }

    const list = document.createElement("ul");
    list.className = "chart-legend";

    names.forEach((name, index) => {
      const item = document.createElement("li");

      // textContent, never innerHTML: these are application names.
      item.appendChild(swatch(index));
      item.appendChild(document.createTextNode(name));
      list.appendChild(item);
    });

    card.appendChild(list);
  };

  const reading = (name, value, index, named) => {
    const line = document.createElement("div");

    if (named) {
      line.appendChild(swatch(index));
    }

    line.appendChild(
      document.createTextNode(named ? `${name} ${number(value)}` : number(value)),
    );

    return line;
  };

  const hover = (tooltip, state, at) => (plot) => {
    const { idx, left, top } = plot.cursor;
    const values = state.names.map((_, index) => plot.data[index + 1]?.[idx]);
    // Live data can shrink under the cursor between redraws.
    const readable = idx != null && values.some((value) => value != null);

    if (!readable) {
      tooltip.hidden = true;
      return;
    }

    const header = document.createElement("div");

    header.className = "tooltip-at";
    header.textContent = at(state, idx);

    const rows = state.names
      .map((name, index) => [name, values[index], index])
      .filter(([, value]) => value != null)
      .map(([name, value, index]) =>
        reading(name, value, index, state.names.length > 1),
      );

    tooltip.replaceChildren(header, ...rows);
    tooltip.hidden = false;
    tooltip.style.left = `${plot.over.offsetLeft + left}px`;
    tooltip.style.top = `${plot.over.offsetTop + top}px`;
  };

  /**
   * Build a renderer from the little a chart type does differently.
   *
   * Everything shared (the themed axes and cursor, mounting, resizing, the
   * legend, the tooltip, appending and replacing) lives here. A type supplies
   * only its own `scale`, `axis`, `series`, `data` and `at`, which is also all a
   * custom widget's renderer has to write.
   */
  const chart = (spec) => {
    const axis = () => ({
      stroke: token("--text-dim"),
      grid: { stroke: token("--border"), width: 1 },
      ticks: { stroke: token("--border"), width: 1 },
      font: `10px ${token("--font-mono")}`,
    });

    const options = (container, tooltip, state) => ({
      width: container.clientWidth,
      height: container.clientHeight,
      legend: { show: false },
      cursor: { y: false },
      scales: { x: spec.scale(state), ...(spec.scales ?? {}) },
      axes: [
        { ...axis(), ...spec.axis(state) },
        { ...axis(), size: 44 },
      ],
      series: [
        {},
        ...state.names.map((name, index) => ({
          label: name,
          ...spec.series(name, index, state),
        })),
      ],
      hooks: { setCursor: [hover(tooltip, state, spec.at)] },
    });

    return {
      mount(card, payload) {
        const container = card.querySelector(".card-chart");
        const tooltip = document.createElement("div");

        tooltip.className = "chart-tooltip";
        tooltip.hidden = true;
        container.appendChild(tooltip);

        // One object, mutated in place, so the option closures above keep
        // seeing the current names and labels after a replace.
        const state = {
          names: payload.series ?? ["value"],
          labels: payload.x ?? [],
          data: spec.data(payload),
        };

        state.chart = new uPlot(
          options(container, tooltip, state),
          state.data,
          container,
        );

        new ResizeObserver(() => {
          state.chart.setSize({
            width: container.clientWidth,
            height: container.clientHeight,
          });
        }).observe(container);

        legend(card, state.names);

        return state;
      },

      append(state, point) {
        const [x, ...lines] = state.data;

        x.push(point.x);
        lines.forEach((line, index) => line.push(point.y[index] ?? null));

        if (x.length > POINTS) {
          state.data.forEach((column) => column.shift());
        }

        state.chart.setData(state.data);
      },

      replace(state, payload) {
        state.labels = payload.x ?? [];
        state.data = spec.data(payload);
        state.chart.setData(state.data);
      },
    };
  };

  const points = (index) => ({
    show: true,
    size: 4,
    stroke: colour(index),
    fill: colour(index),
  });

  const lines = (time) =>
    chart({
      scale: () => ({ time }),
      axis: () => ({}),
      data: (payload) => [payload.x ?? [], ...(payload.y ?? [[]])],
      at: (state, idx) =>
        time
          ? new Date(state.data[0][idx] * 1000).toLocaleTimeString()
          : number(state.data[0][idx]),
      series: (name, index, state) => ({
        stroke: colour(index),
        width: 2,
        // Overlapping fills muddy each other, so only a lone line gets one.
        fill: state.names.length === 1 ? translucent(colour(index), 0.12) : undefined,
        points: points(index),
      }),
    });

  const bars = () =>
    chart({
      // Half a slot of padding either side, so every bar gets equal room.
      scale: () => ({
        time: false,
        range: (plot, min, max) => [(min ?? 0) - 0.5, (max ?? 0) + 0.5],
      }),
      // A bar is read by its height, so it has to start at zero. Letting the
      // axis begin at the smallest value draws the shortest bar as nothing.
      //
      // A chart with no bars yet has no maximum, and uPlot cannot scale to a
      // null one, so it holds an empty axis until the first event lands.
      scales: {
        y: {
          range: (plot, min, max) =>
            uPlot.rangeNum(0, max > 0 ? max : 1, 0.1, true),
        },
      },
      axis: (state) => ({
        grid: { show: false },
        values: (plot, splits) => splits.map((index) => state.labels[index] ?? ""),
        splits: () => state.labels.map((_, index) => index),
      }),
      data: (payload) => [
        (payload.x ?? []).map((_, index) => index),
        ...(payload.y ?? [[]]),
      ],
      at: (state, idx) => state.labels[idx],
      series: (name, index) => ({
        stroke: colour(index),
        fill: translucent(colour(index), 0.45),
        width: 1,
        paths: uPlot.paths.bars({ size: [0.8, Infinity] }),
        points: { show: false },
      }),
    });

  // One entry per widget type, matching the `type` its Python class declares.
  const renderers = {
    timeseries: lines(true),
    line: lines(false),
    bar: bars(),
  };

  const mount = () => {
    const widgets = new Map();

    for (const card of document.querySelectorAll("[data-widget]")) {
      const type = card.dataset.type;
      const renderer = renderers[type];

      if (!renderer) {
        continue;
      }

      const widget = renderer.mount(card, JSON.parse(card.dataset.payload));

      widget.type = type;
      widgets.set(card.dataset.widget, widget);
    }

    return widgets;
  };

  const apply = (widgets, message) => {
    const widget = widgets.get(message.widget);
    const renderer = widget && renderers[widget.type];
    const handler = renderer && renderer[message.op];

    if (handler) {
      handler(widget, message.data);
    }
  };

  const listen = (widgets) => {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${scheme}://${location.host}/_ws`);

    socket.addEventListener("message", (event) => {
      for (const message of JSON.parse(event.data)) {
        apply(widgets, message);
      }
    });

    // A dropped connection means a dropped dashboard, so keep trying.
    socket.addEventListener("close", () => {
      setTimeout(() => listen(widgets), RECONNECT_DELAY);
    });
  };

  document.addEventListener("DOMContentLoaded", () => listen(mount()));
})();
