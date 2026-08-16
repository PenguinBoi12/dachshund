(() => {
  "use strict";

  const RECONNECT_DELAY = 2000;

  const mount = () => {
    const renderers = window.Dachshund.renderers;
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
    const renderer = widget && window.Dachshund.renderers[widget.type];
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
