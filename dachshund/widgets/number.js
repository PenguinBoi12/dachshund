(() => {
  "use strict";

  const format = (value) =>
    value == null ? "—" : Number.isInteger(value) ? String(value) : value.toFixed(2);

  const paint = (state, payload) => {
    state.number.textContent = format(payload.value);
  };

  window.Dachshund.widget("number", {
    mount(card, payload) {
      const container = card.querySelector(".card-content");
      container.classList.add("number");

      const number = document.createElement("div");
      number.className = "number-value";
      container.append(number);

      const state = { number };
      paint(state, payload);

      return state;
    },
    replace: paint,
  });
})();
