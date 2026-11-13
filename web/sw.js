/* XAHOO service worker: installable app shell + private push notifications.
   Pushes carry NO data; on wake-up we fetch the newest alert from our own server with the owner's session,
   so alert contents never pass through Google/Apple/Mozilla push services. API responses are never cached. */
const VERSION = "xahoo-v1";
const SHELL = ["/", "/app.js", "/styles.css", "/manifest.webmanifest", "/vendor/lightweight-charts-4.2.0.js",
               "/vendor/fonts/JetBrainsMono-latin.woff2", "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL).catch(() => {})).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  // network first (always fresh, login redirects respected), cached shell only when offline
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok && SHELL.includes(url.pathname)) { const copy = r.clone(); caches.open(VERSION).then(c => c.put(e.request, copy)); }
    return r;
  }).catch(() => caches.match(e.request).then(r => r || caches.match("/"))));
});

self.addEventListener("push", e => {
  e.waitUntil(
    fetch("/api/alerts/latest", { credentials: "same-origin", cache: "no-store" })
      .then(r => r.ok ? r.json() : { title: "XAHOO", body: "New alert — open the app (login needed)" })
      .catch(() => ({ title: "XAHOO", body: "New alert — open the app" }))
      .then(a => self.registration.showNotification(a.title || "XAHOO", {
        body: a.body || "", tag: "xahoo-" + (a.id || Date.now()), renotify: true,
        icon: "/icons/icon-192.png", badge: "/icons/icon-192.png",
        requireInteraction: a.kind === "signal" || a.kind === "prealert",
        vibrate: a.kind === "signal" ? [200, 100, 200, 100, 400] : [150, 80, 150],
        data: { url: "/" },
      }))
  );
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(cs => {
    for (const c of cs) if ("focus" in c) return c.focus();
    return self.clients.openWindow(e.notification.data && e.notification.data.url || "/");
  }));
});
