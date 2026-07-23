const CACHE_NAME = "vermessung-v2";
const CORE_ASSETS = [
  "./",
  "./index.html",
  "./manifest.json",
  "./css/style.css",
  "./js/main.js",
  "./js/state.js",
  "./js/storage.js",
  "./js/coords.js",
  "./js/mapView.js",
  "./js/gpsRecorder.js",
  "./js/dxfExport.js",
  "./icons/icon.svg",
  "./icons/icon-192.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Once internetten guncel dosyayi cekmeye calisir (network-first); sadece cevrimdisiyken
// veya istek basarisiz olursa onbellekten doner. Boylece internet varken her zaman en
// guncel surum gosterilir, cevrimdisiyken de uygulama acilabilir.
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return networkResponse;
      })
      .catch(() => caches.match(event.request))
  );
});
