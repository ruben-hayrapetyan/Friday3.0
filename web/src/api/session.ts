// Who is signed in to a hosted Friday, and signing out (HOSTED.md S4). Your Friday on the Mac has no accounts: there
// /auth/me is the website's own page (HTML), so nobody is signed in and nothing about signing out is shown.

export type Me = { email: string; username: string; name: string }

/** The account signed in, or null: your own Friday, or not answered. */
export async function whoAmI(fetcher: typeof fetch = fetch): Promise<Me | null> {
  try {
    const response = await fetcher("/auth/me")
    if (!response.ok || !(response.headers.get("content-type") ?? "").includes("application/json")) return null
    return (await response.json()) as Me
  } catch {
    return null
  }
}

/** Ends this browser's session, drops what the service worker kept of your plan, and opens the sign-in page. */
export async function signOut(fetcher: typeof fetch = fetch, go: (path: string) => void = (p) => window.location.assign(p)): Promise<void> {
  await fetcher("/auth/signout", { method: "POST" }).catch(() => undefined)
  if (typeof caches !== "undefined") for (const key of await caches.keys()) await caches.delete(key)
  go("/signin")
}

/** Where a 401 from a hosted Friday says to sign in, or null for any other answer. */
export function signInPage(status: number, body: unknown): string | null {
  if (status !== 401 || typeof body !== "object" || body === null) return null
  const page = (body as { signin?: unknown }).signin
  return typeof page === "string" && page.startsWith("/") ? page : null
}
