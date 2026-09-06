"use strict";
// Service worker: caches the static app shell so Cairn installs as a PWA
// and loads instantly. Pages themselves are never cached (they hold
// private financial data and are served no-store).
var CACHE = "cairn-static-v1";
var SHELL = [
  "/static/css/app.css",
  "/static/js/theme.js",
  "/static/js/app.js",
  "/static/js/charts.js",
  "/static/img/logo.svg",
  "/static/img/favicon.svg",
  "/static/img/icon-192.png",
  "/static/img/icon-512.png"
];

self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) { return c.addAll(SHELL); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE; })
        .map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (e) {
  var url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.indexOf("/static/") !== 0) return; // never cache pages
  e.respondWith(
    caches.match(e.request).then(function (hit) {
      if (hit) return hit;
      return fetch(e.request).then(function (res) {
        if (res && res.ok) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        }
        return res;
      });
    })
  );
});
