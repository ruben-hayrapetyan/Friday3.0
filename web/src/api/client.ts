// A typed `command(name, input)` and `query(name, params)` over the generated OpenAPI types (DESIGN §18.1).

import { noteResponse } from "./offline"
import type { components, operations } from "./schema"

export type Schemas = components["schemas"]
type Ops = operations
type Json<T> = T extends { content: { "application/json": infer B } } ? B : never

export type Output<N extends keyof Ops> = Json<Ops[N]["responses"][200]>
// A body whose fields all have defaults is optional, so read it through NonNullable; a GET's is `never`.
type Body<K extends keyof Ops> = NonNullable<Ops[K]["requestBody"]>
export type CommandName = {
  [K in keyof Ops]: [Body<K>] extends [never] ? never : Output<K> extends { command_id: unknown } ? K : never
}[keyof Ops]
export type QueryName = Exclude<keyof Ops, CommandName | "preview_weights">
export type CommandInput<N extends CommandName> = Json<Body<N>>
export type QueryParams<N extends QueryName> = NonNullable<Ops[N]["parameters"]["query"]>
// A query whose input carries a mapping (`fit`) is a POST with a JSON body, not a query string.
export type BodyQueryName = { [K in QueryName]: [Body<K>] extends [never] ? never : K }[QueryName]

export type Block = Schemas["BlockOut"]
export type Item = Schemas["ItemOut"]

export class ApiError extends Error {
  status: number
  field: string | null // the input it's about, for a form to point at; never put in front of the words (8 Nov)

  constructor(message: string, status: number, field: string | null = null) {
    super(message)
    this.status = status
    this.field = field
  }
}

/** A field's key as words: "duration_min" → "Duration", "start" → "Start". */
export function fieldWords(key: string): string {
  const words = key.replace(/_(min|utc|id)$/, "").replace(/_/g, " ").trim()
  return words ? words[0].toUpperCase() + words.slice(1) : key
}

/** What went wrong, as a sentence to read on the spot (8 Nov: "make all errors and warnings very user friendly so
 * that they can debug it on the spot"): the server's own words without its field keys in front ("end: end: …",
 * "value: planner.debounce_s: …"), a check that failed named by its field in words, and when there's no server's
 * word at all, what it means and what to do. */
export function messageFrom(status: number, body: unknown): string {
  const b = (body ?? {}) as { message?: unknown; field?: unknown; detail?: unknown }
  if (typeof b.message === "string" && b.message) return withoutKeys(b.message, typeof b.field === "string" ? b.field : null)
  if (Array.isArray(b.detail)) {
    return b.detail
      .map((d: { msg?: string; loc?: unknown[] }) => {
        const key = [...(d.loc ?? [])].reverse().find((part) => typeof part === "string" && part !== "body") as string | undefined
        return `${key ? `${fieldWords(key)}: ` : ""}${(d.msg ?? "").replace(/^Value error, /, "")}`
      })
      .join("; ")
  }
  if (status >= 500) return "Something went wrong inside Friday. Try again; if it keeps happening, Settings → Advanced → Diagnose shows what happened."
  if (status === 404) return "Friday doesn't know that one any more: it may have been deleted. Reload the page."
  return `Friday said no (${status}). Try again; if it keeps happening, Settings → Advanced → Diagnose shows why.`
}

/** "end: that's later than now" → "That's later than now"; "value: planner.debounce_s: Input should be …" → "Input should be …". */
function withoutKeys(message: string, field: string | null): string {
  let said = message
  if (field) while (said.startsWith(`${field}: `)) said = said.slice(field.length + 2)
  // a setting's path after "value: " ("planner.debounce_s: …"); only for a setting, so "lab_report: …" keeps its words
  if (field === "value") said = said.replace(/^[a-z_]+(\.[a-z_]+)*: /, "")
  return said ? said[0].toUpperCase() + said.slice(1) : message
}

/** Any error as words for a toast: the server's, or what it means when there was no answer at all. */
export function errorWords(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof DOMException && error.name === "AbortError") return "Stopped."
  if (error instanceof TypeError && /load failed|failed to fetch|networkerror|network connection was lost/i.test(error.message)) {
    // fetch itself failed: nothing answered (any other TypeError is a mistake in the page, said as it is)
    return "Friday's server didn't answer: it may be starting up or restarting. Try again in a moment; if it keeps happening, quit Friday and open it again."
  }
  return error instanceof Error ? error.message : String(error)
}

async function read<T>(response: Response): Promise<T> {
  noteResponse(response)
  if (response.ok) return response.json()
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // not JSON: said from the status
  }
  const field = body && typeof (body as { field?: unknown }).field === "string" ? (body as { field: string }).field : null
  throw new ApiError(messageFrom(response.status, body), response.status, field)
}

/** Reads wait their turn, a few at a time, and what you do goes first (12 Nov: one click had the page ask some 35
 * things again at once, all on this Mac, and the next click waited behind them): commands never wait here. Reads that
 * plan your week (What if, a suggestion's effect, another way, the exact fit check) take seconds, so they have turns
 * of their own: two of them at once used to hold half the page's turns (13 Nov). */
export type Lane = "quick" | "planning"
const AT_ONCE: Record<Lane, number> = { quick: 4, planning: 2 }
const PLANNING = new Set(["whatif", "suggestion_effect", "other_way"])
const reading: Record<Lane, number> = { quick: 0, planning: 0 }
const waitingReads: Record<Lane, (() => void)[]> = { quick: [], planning: [] }

/** Which turns a read takes: the fit check's quick answer is quick, its exact one plans. */
export function laneOf(name: string, body?: unknown): Lane {
  if (name === "fit") return (body as { exact?: boolean } | undefined)?.exact ? "planning" : "quick"
  return PLANNING.has(name) ? "planning" : "quick"
}

async function inTurn<T>(lane: Lane, read: () => Promise<T>): Promise<T> {
  if (reading[lane] >= AT_ONCE[lane]) await new Promise<void>((go) => waitingReads[lane].push(go))
  reading[lane]++
  try {
    return await read()
  } finally {
    reading[lane]--
    waitingReads[lane].shift()?.()
  }
}

export async function command<N extends CommandName>(
  name: N,
  input: CommandInput<N>,
  // "full" adds a warm solve's change list to the preview (DESIGN §9.2).
  // signal: to stop waiting (Ask's Stop, 3 Nov); the server finishes on its own and what it answers is dropped
  options: { preview?: boolean | "full"; signal?: AbortSignal } = {},
): Promise<Output<N>> {
  const response = await fetch(`/api/c/${name}${options.preview ? `?preview=${options.preview}` : ""}`, {
    method: "POST",
    headers: { "content-type": "application/json", "idempotency-key": crypto.randomUUID() },
    body: JSON.stringify(input),
    signal: options.signal,
  })
  const out = await read<Output<N>>(response)
  // done: said to the page, for what listens for something you did (shell/Tour.tsx's quests)
  if (!options.preview && typeof window !== "undefined") window.dispatchEvent(new CustomEvent("friday:command", { detail: { name } }))
  return out
}

export async function queryBody<N extends BodyQueryName>(name: N, body: Json<Body<N>>): Promise<Output<N>> {
  return inTurn(laneOf(name, body), async () => read(await fetch(`/api/q/${name}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })))
}

export async function query<N extends QueryName>(name: N, params?: QueryParams<N>, signal?: AbortSignal): Promise<Output<N>> {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === null || value === undefined) continue
    for (const v of Array.isArray(value) ? value : [value]) search.append(key, String(v))
  }
  const text = search.toString()
  return inTurn(laneOf(name), async () => read(await fetch(`/api/q/${name}${text ? `?${text}` : ""}`, signal ? { signal } : undefined)))
}
