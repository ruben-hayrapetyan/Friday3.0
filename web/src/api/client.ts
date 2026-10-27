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

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function read<T>(response: Response): Promise<T> {
  noteResponse(response)
  if (response.ok) return response.json()
  let message = `${response.status} ${response.statusText}`
  try {
    const body = await response.json()
    // The server's message names its field already ("end: that's later than now"): said once, not "end: end: …".
    if (body.message) message = body.field && !String(body.message).startsWith(`${body.field}:`) ? `${body.field}: ${body.message}` : body.message
    else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ")
  } catch {
    // not JSON: keep the status line
  }
  throw new ApiError(message, response.status)
}

export async function command<N extends CommandName>(
  name: N,
  input: CommandInput<N>,
  // "full" adds a warm solve's change list to the preview (DESIGN §9.2).
  options: { preview?: boolean | "full" } = {},
): Promise<Output<N>> {
  const response = await fetch(`/api/c/${name}${options.preview ? `?preview=${options.preview}` : ""}`, {
    method: "POST",
    headers: { "content-type": "application/json", "idempotency-key": crypto.randomUUID() },
    body: JSON.stringify(input),
  })
  return read(response)
}

export async function queryBody<N extends BodyQueryName>(name: N, body: Json<Body<N>>): Promise<Output<N>> {
  return read(await fetch(`/api/q/${name}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }))
}

export async function query<N extends QueryName>(name: N, params?: QueryParams<N>): Promise<Output<N>> {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === null || value === undefined) continue
    for (const v of Array.isArray(value) ? value : [value]) search.append(key, String(v))
  }
  const text = search.toString()
  return read(await fetch(`/api/q/${name}${text ? `?${text}` : ""}`))
}
