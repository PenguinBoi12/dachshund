window.Dachshund.widget("test_gauge", {
  mount(card, payload) {
    return { value: payload.value };
  },
  replace(state, data) {
    state.value = data.value;
  },
});
