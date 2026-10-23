/// <reference lib="webworker" />
// The service worker (DESIGN §18.11, §20.1): the app shell offline, the last answer to each query when fridayd
// can't be reached (marked so the app shows its offline banner), and Web Push with buttons that work from the
// notification. Plain Cache API; vite-plugin-pwa only injects the list of files to keep.

declare const self: ServiceWorkerGlobalScope & { __WB_MANIFEST: { url: string; revision: string | null }[] }

const SHELL = "friday-shell"
const DATA = "friday-data"
const OFFLINE_HEADER = "x-friday-offline" // read by api/client.ts

interface Pushed {
  title: string
  body: string
  url: string
  actions: { label: string; token: string | null; url: string | null }[]
  open_token: string | null
  dismiss_token: string | null
}

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

self.addEventListener("push", (event) => {
  const data = event.data?.json() as Pushed
  const options: NotificationOptions & { actions?: { action: string; title: string }[] } = {
    body: data.body,
    data,
    tag: data.title,
    actions: data.actions.slice(0, 2).map((a, i) => ({ action: String(i), title: a.label })),
  }
  event.waitUntil(self.registration.showNotification(data.title, options))
})

self.addEventListener("notificationclick", (event) => {
  const data = event.notification.data as Pushed
  event.notification.close()
  const chosen = event.action ? data.actions[Number(event.action)] : null
  if (chosen?.token) {
    event.waitUntil(act(chosen.token))
    return
  }
  event.waitUntil(Promise.all([data.open_token ? act(data.open_token) : null, open(chosen?.url ?? data.url)]))
})

self.addEventListener("notificationclose", (event) => {
  const data = event.notification.data as Pushed
  if (data.dismiss_token) event.waitUntil(act(data.dismiss_token))
})

async function act(token: string): Promise<void> {
  await fetch("/api/c/act", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token }),
  }).catch(() => undefined)
}

async function open(path: string): Promise<void> {
  const target = `${self.location.origin}/#${path}`
  const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true })
  const existing = windows[0] as WindowClient | undefined
  if (existing) {
    await existing.focus()
    await existing.navigate(target)
  } else {
    await self.clients.openWindow(target)
  }
}
