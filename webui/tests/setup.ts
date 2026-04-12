Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: function matchMedia(query) {
    return {
      matches: false,
      media: query,
      onchange: null,
      addListener: function addListener() {},
      removeListener: function removeListener() {},
      addEventListener: function addEventListener() {},
      removeEventListener: function removeEventListener() {},
      dispatchEvent: function dispatchEvent() {
        return false;
      }
    };
  }
});

window.sessionStorage.clear();
