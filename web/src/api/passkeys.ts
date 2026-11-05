// Passkeys from Settings → About you (HOSTED.md S4; H88, H90): made with Touch ID in this browser, listed, removed.
// Bytes travel as base64url both ways, as on the sign-in pages (src/friday/server/passkey_page.py).

export type Passkey = { id: string; name: string; created: number; used: number | null }

export function fromBase64url(text: string): Uint8Array {
  const plain = text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4)
  return Uint8Array.from(atob(plain), (c) => c.charCodeAt(0))
}

export function toBase64url(bytes: ArrayBuffer | Uint8Array): string {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)
  return btoa(String.fromCharCode(...view)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
}

/** Whether this window can make a passkey: a browser with WebAuthn, not the Mac app's window (it signs in through
 * the browser, H43). */
export function canMakePasskeys(win: { PublicKeyCredential?: unknown; navigator: { userAgent: string } } = window): boolean {
  return Boolean(win.PublicKeyCredential) && !win.navigator.userAgent.includes("FridayMac")
}

async function post<T>(path: string, body: unknown, fetcher: typeof fetch): Promise<T> {
  const response = await fetcher(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
  const answer = await response.json()
  if (!response.ok) throw new Error(answer.message ?? `${response.status}`)
  return answer as T
}

export async function listPasskeys(fetcher: typeof fetch = fetch): Promise<Passkey[]> {
  const response = await fetcher("/auth/passkeys")
  if (!response.ok || !(response.headers.get("content-type") ?? "").includes("application/json")) return []
  return (await response.json()) as Passkey[]
}

export async function removePasskey(id: string, fetcher: typeof fetch = fetch): Promise<boolean> {
  return (await post<{ removed: boolean }>("/auth/passkeys/remove", { id }, fetcher)).removed
}

type Options = { flow: string; options: Record<string, any> } // eslint-disable-line @typescript-eslint/no-explicit-any

/** The server's options as the browser takes them: the challenge, your id and the keys to leave out as bytes. */
export function creationOptions(options: Options["options"]): PublicKeyCredentialCreationOptions {
  return {
    ...options,
    challenge: fromBase64url(options.challenge),
    user: { ...options.user, id: fromBase64url(options.user.id) },
    excludeCredentials: (options.excludeCredentials ?? []).map((c: { id: string; type: "public-key" }) => ({ ...c, id: fromBase64url(c.id) })),
  } as unknown as PublicKeyCredentialCreationOptions
}

/** Makes a passkey in this browser (Touch ID asks) and keeps it on the server; its name, e.g. "Mac, Chrome". */
export async function addPasskey(fetcher: typeof fetch = fetch, credentials: CredentialsContainer = navigator.credentials): Promise<string> {
  const asked = await post<Options>("/auth/passkey/register/options", {}, fetcher)
  const made = (await credentials.create({ publicKey: creationOptions(asked.options) })) as PublicKeyCredential | null
  if (!made) throw new Error("No passkey made")
  const r = made.response as AuthenticatorAttestationResponse
  const credential = {
    id: made.id,
    rawId: toBase64url(made.rawId),
    type: made.type,
    authenticatorAttachment: made.authenticatorAttachment,
    clientExtensionResults: made.getClientExtensionResults(),
    response: { clientDataJSON: toBase64url(r.clientDataJSON), attestationObject: toBase64url(r.attestationObject), transports: r.getTransports?.() ?? [] },
  }
  return (await post<{ name: string }>("/auth/passkey/register", { flow: asked.flow, credential }, fetcher)).name
}
