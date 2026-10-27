/// <reference lib="webworker" />
// The service worker (DESIGN §18.11): the app shell offline, and the last answer to each query when fridayd can't be
// reached (marked so the app shows its offline banner). Plain Cache API; vite-plugin-pwa only injects the list of
// files to keep. (Web Push went with notifications, 27 Oct.)

declare const self: ServiceWorkerGlobalScope & { __WB_MANIFEST: { url: string; revision: string | null }[] }

const SHELL = "friday-shell"
const DATA = "friday-data"
const OFFLINE_HEADER = "x-friday-offline" // read by api/client.ts

self.addEventListener("install", (event) => {
  // The plugin lists the manifest's icons a second time, and addAll refuses duplicates.
  const files = [...new Set(["/", ...self.__WB_MANIFEST.map((f) => (f.url.startsWith("/") ? f.url : `/${f.url}`))])]
  event.waitUntil(
    caches
      .delete(SHELL)
      .then(() => caches.open(SHELL))
      .then((cache) => cache.addAll(files))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()))

self.addEventListener("fetch", (event) => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname === "/events") return
  if (url.pathname.startsWith("/api/q/")) event.respondWith(lastKnown(request))
  else if (request.mode === "navigate") event.respondWith(fetch(request).catch(() => shell("/")))
  // A file the cache doesn't have (a newer build's) comes from the network; otherwise a new build loads blank.
  else if (!url.pathname.startsWith("/api/")) event.respondWith(cached(request).then((hit) => hit ?? fetch(request)))
})

async function cached(request: Request | string): Promise<Response | undefined> {
  return caches.match(request, { cacheName: SHELL })
}

async function shell(request: Request | string): Promise<Response> {
  return (await cached(request)) ?? Response.error()
}

/** The network's answer, kept; without a network, the last one kept, marked as such. */
async function lastKnown(request: Request): Promise<Response> {
  try {
    const response = await fetch(request)
    if (response.ok) {
      const cache = await caches.open(DATA)
      await cache.put(request, response.clone())
    }
    return response
  } catch (error) {
    const kept = await caches.match(request, { cacheName: DATA })
    if (!kept) throw error
    const headers = new Headers(kept.headers)
    headers.set(OFFLINE_HEADER, "1")
    return new Response(await kept.blob(), { status: kept.status, headers })
  }
}
