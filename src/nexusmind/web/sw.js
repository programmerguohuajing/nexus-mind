/* NexusMind Service Worker：静态资源缓存 + API 网络优先 + 离线回退到移动页。 */
const CACHE = "nexusmind-v1";
const STATIC_ASSETS = [
  "/m",
  "/styles.css",
  "/ui.js",
  "/app.js",
  "/extras.js",
  "/assets/nexusmind-agent.png",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/mcp/")) {
    // API 网络优先，失败时返回缓存（只读展示）或离线提示
    event.respondWith(
      fetch(event.request).catch(() =>
        caches.match(event.request).then(
          (hit) => hit || new Response(JSON.stringify({ detail: "offline" }), {
            status: 503,
            headers: { "Content-Type": "application/json" },
          })
        )
      )
    );
    return;
  }
  event.respondWith(
    caches.match(event.request).then((hit) => {
      const network = fetch(event.request).then((resp) => {
        if (resp.ok && url.origin === self.location.origin) {
          const copy = resp.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return resp;
      }).catch(() => hit);
      return hit || network;
    })
  );
});
