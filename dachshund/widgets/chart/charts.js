(() => {
  "use strict";

  const POINTS = 500;
  const PALETTE = 8;
  const WHEEL_ZOOM_FACTOR = 0.75;
  // Seconds: a timeseries opens zoomed to its last hour.
  const DEFAULT_WINDOW = 3600;

  const RANGES = [
    { label: "1h", seconds: 3600 },
    { label: "6h", seconds: 21600 },
    { label: "24h", seconds: 86400 },
    { label: "All", seconds: Infinity },
  ];

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

  const widen = (bound, next) =>
    bound && next
      ? [Math.min(bound[0], next[0]), Math.max(bound[1], next[1])]
      : (bound ?? next);

  const clamp = (min, max, range, boundMin, boundMax, boundRange) => {
    if (range > boundRange) return [boundMin, boundMax];
    if (min < boundMin) return [boundMin, boundMin + range];
    if (max > boundMax) return [boundMax - range, boundMax];
    return [min, max];
  };

  /**
   * Scroll to zoom, middle-drag to pan, double-click to reset. Ported from
   * uPlot's own zoom-wheel demo (github.com/leeoniya/uPlot, demos/zoom-wheel.html),
   * scoped to the x axis only so it composes with uPlot's built-in dblclick
   * handler, which already resets x (not y) via autoScaleX(). Zooming y too
   * would leave that reset partial, and would fight the bar charts' y axis
   * always starting at zero.
   *
   * The demo takes its pan/zoom-out bound once, from the scale range at
   * mount. Live charts keep streaming past that range, so here the bound
   * widens on every setData instead of staying frozen at whatever the chart
   * looked like on first paint. It's also seeded from the data itself, not
   * the initial scale range, since a timeseries opens zoomed to an hour
   * while the data behind it can already cover much more.
   */
  const wheelZoom = (factor = WHEEL_ZOOM_FACTOR) => {
    let bound = null;

    const widenBound = (plot) => {
      const [xs] = plot.data;

      bound = widen(bound, xs.length ? [xs[0], xs[xs.length - 1]] : null);
    };

    return {
      hooks: {
        ready: (plot) => {
          widenBound(plot);

          const over = plot.over;

          // Reserves the middle button for panning, since the left button is
          // already claimed by uPlot's own select-drag.
          over.addEventListener("mousedown", (event) => {
            if (event.button !== 1) return;
            event.preventDefault();

            const left0 = event.clientX;
            const min0 = plot.scales.x.min;
            const max0 = plot.scales.x.max;
            const perPixel = plot.posToVal(1, "x") - plot.posToVal(0, "x");

            const onMove = (e) => {
              e.preventDefault();
              const dx = perPixel * (e.clientX - left0);
              plot.setScale("x", { min: min0 - dx, max: max0 - dx });
              plot.zoomed = true;
            };

            const onUp = () => {
              document.removeEventListener("mousemove", onMove);
              document.removeEventListener("mouseup", onUp);
            };

            document.addEventListener("mousemove", onMove);
            document.addEventListener("mouseup", onUp);
          });

          over.addEventListener("wheel", (event) => {
            event.preventDefault();

            const rect = over.getBoundingClientRect();
            const leftPct = plot.cursor.left / rect.width;
            const xVal = plot.posToVal(plot.cursor.left, "x");
            const scale = event.deltaY < 0 ? factor : 1 / factor;

            const [boundMin, boundMax] = bound;

            let nMin = xVal - leftPct * (plot.scales.x.max - plot.scales.x.min) * scale;
            let nMax = nMin + (plot.scales.x.max - plot.scales.x.min) * scale;
            [nMin, nMax] = clamp(
              nMin,
              nMax,
              nMax - nMin,
              boundMin,
              boundMax,
              boundMax - boundMin,
            );

            plot.setScale("x", { min: nMin, max: nMax });
            plot.zoomed = true;
          });

          // uPlot's own dblclick handler (bound alongside this one, since
          // both listen on `over`) already runs autoScaleX() first; this
          // only clears the flag so the next live update auto-fits again.
          over.addEventListener("dblclick", () => {
            plot.zoomed = false;
          });
        },
        setData: widenBound,
      },
    };
  };

  const rangePicker = (state) => {
    const nav = document.createElement("div");
    nav.className = "chart-ranges";

    RANGES.forEach(({ label, seconds }) => {
      const button = document.createElement("button");

      button.type = "button";
      button.textContent = label;
      button.setAttribute("aria-pressed", String(seconds === state.window));

      button.addEventListener("click", () => {
        state.window = seconds;
        state.chart.zoomed = false;
        state.chart.setData(state.data, true);

        nav
          .querySelectorAll("button")
          .forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      });

      nav.appendChild(button);
    });

    return nav;
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
      plugins: [wheelZoom()],
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
        const container = card.querySelector(".card-content");
        const tooltip = document.createElement("div");

        // A chart needs a fixed height to draw into; a plain content div
        // doesn't, so this class (not the shared one) carries that sizing.
        container.classList.add("chart");

        tooltip.className = "chart-tooltip";
        tooltip.hidden = true;
        container.appendChild(tooltip);

        // One object, mutated in place, so the option closures above keep
        // seeing the current names and labels after a replace.
        const state = {
          names: payload.series ?? ["value"],
          labels: payload.x ?? [],
          data: spec.data(payload),
          window: spec.window,
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

        if (spec.window != null) {
          card.insertBefore(rangePicker(state), container);
        }

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

        // A user mid-zoom doesn't want the next tick to snap them back out.
        state.chart.setData(state.data, !state.chart.zoomed);
      },

      replace(state, payload) {
        state.labels = payload.x ?? [];
        state.data = spec.data(payload);
        state.chart.setData(state.data, !state.chart.zoomed);
      },
    };
  };

  // Drawn only on hover: uPlot's cursor dot reads size/stroke/fill from
  // here regardless of `show`, so this still styles it even though the
  // line itself never paints one at every point.
  const points = (index) => ({
    show: false,
    size: 7,
    stroke: colour(index),
    fill: colour(index),
  });

  const lines = (time) =>
    chart({
      window: time ? DEFAULT_WINDOW : undefined,
      scale: (state) => ({
        time,
        ...(time && {
          range: (plot, dataMin, dataMax) =>
            dataMax == null
              ? [dataMin, dataMax]
              : [Math.max(dataMin, dataMax - state.window), dataMax],
        }),
      }),
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

  window.Dachshund.widget("timeseries", lines(true));
  window.Dachshund.widget("line", lines(false));
  window.Dachshund.widget("bar", bars());

  // Reused by other widgets wanting the same palette/theme tokens.
  window.Dachshund.token = token;
  window.Dachshund.colour = colour;
  window.Dachshund.translucent = translucent;
})();
