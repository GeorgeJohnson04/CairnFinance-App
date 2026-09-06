"use strict";
// Runs synchronously in <head> so the right theme is applied before the
// first paint (no flash). Saved choice wins; otherwise follow the system.
(function () {
  var root = document.documentElement;
  function apply(t) { root.setAttribute("data-theme", t); }
  try {
    var saved = localStorage.getItem("cairn-theme");
    var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
    var theme = (saved === "dark" || saved === "light") ? saved
      : (mq && mq.matches ? "dark" : "light");
    apply(theme);
    if (mq && mq.addEventListener) {
      mq.addEventListener("change", function (e) {
        if (localStorage.getItem("cairn-theme")) return; // user chose explicitly
        apply(e.matches ? "dark" : "light");
        if (window.cairnRenderCharts) window.cairnRenderCharts();
      });
    }
  } catch (e) {
    apply("light");
  }
})();
