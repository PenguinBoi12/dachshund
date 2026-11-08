(() => {
  "use strict";

  const compact = new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1,
  });

  const format = (value) => {
    if (value == null) return "—";

    if (Math.abs(value) < 1000) {
      return Number.isInteger(value) ? String(value) : value.toFixed(2);
    }

    // Intl's default is "1.5K" (capitalized); lowercased to match this widget's style.
    return compact.format(value).toLowerCase();
  };

  const paint = (state, payload) => {
    state.number.textContent = format(payload.value);
    state.unit.textContent = payload.value == null ? "" : (payload.unit ?? "");
  };

  window.Dachshund.widget("number", {
    mount(card, payload) {
      const container = card.querySelector(".card-content");
      container.classList.add("number");

      const wrap = document.createElement("div");
      wrap.className = "number-reading";

      const number = document.createElement("span");
      number.className = "number-value";
      const unit = document.createElement("span");
      unit.className = "number-unit";

      wrap.append(number, unit);
      container.append(wrap);

      const state = { number, unit };
      paint(state, payload);

      return state;
    },
    replace: paint,
  });
})();
