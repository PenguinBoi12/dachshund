(() => {
  "use strict";

  const paint = (state, payload) => {
    if (payload.html == null) {
      state.content.textContent = "—";
    } else {
      state.content.innerHTML = payload.html;
    }
  };

  window.Dachshund.widget("text", {
    mount(card, payload) {
      const container = card.querySelector(".card-content");
      container.classList.add("text");

      const content = document.createElement("div");
      content.className = "text-content";
      container.append(content);

      const state = { content };
      paint(state, payload);
      return state;
    },
    replace: paint,
  });
})();
