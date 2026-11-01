(() => {
  "use strict";

  const RECONNECT_DELAY = 2000;
  const FLASH_DURATION = 2000;
  const TOAST_DURATION = 6000;

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
    const page = encodeURIComponent(document.body.dataset.page);
    const socket = new WebSocket(`${scheme}://${location.host}/_ws?page=${page}`);

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

  const toast = (title, message) => {
    let stack = document.querySelector(".toasts");

    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toasts";
      stack.setAttribute("role", "status");
      document.body.appendChild(stack);
    }

    const item = document.createElement("div");
    const heading = document.createElement("strong");
    const body = document.createElement("p");

    item.className = "toast toast-error";
    heading.textContent = title;
    body.textContent = message;
    item.append(heading, body);
    item.addEventListener("click", () => item.remove());
    stack.appendChild(item);

    setTimeout(() => item.remove(), TOAST_DURATION);
  };

  const runAction = async (button) => {
    if (button.dataset.confirm === "true" && !confirm(`Run "${button.textContent}"?`)) {
      return;
    }

    const args = button.dataset.args ? JSON.parse(button.dataset.args) : {};
    let ok = false;
    let error = "The dashboard couldn't be reached.";

    try {
      const response = await fetch(`/_actions/${button.dataset.action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ args }),
      });
      const result = await response.json();

      ok = result.ok;
      error = result.error ?? `Request failed (${response.status}).`;
    } catch {
      ok = false;
    }

    button.classList.remove("action-ok", "action-error");
    button.classList.add(ok ? "action-ok" : "action-error");

    clearTimeout(button.flashTimer);
    button.flashTimer = setTimeout(
      () => button.classList.remove("action-ok", "action-error"),
      FLASH_DURATION,
    );

    if (!ok) {
      toast(`${button.textContent.trim()} failed`, error);
    }
  };

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");

    if (button) {
      runAction(button);
    }
  });

  document.addEventListener("DOMContentLoaded", () => listen(mount()));
})();
