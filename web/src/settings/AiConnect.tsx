// The AI Friday reads with (28 Oct: connect it "during the initial setup or through settings later"): Claude, OpenAI,
// Gemini, Grok, Muse, another service that speaks OpenAI's API, or an open model run on this Mac by Ollama. Shown in
// Settings → Integrations and as a step of the first setup. A key is kept in secrets.toml beside friday.toml and never
// shown again; a model is chosen from the service's own list once its key is in. An open model says what it costs
// first (downloaded here, slow), downloads with its progress shown, and the one it replaces is removed only if Friday
// downloaded it: one you had is never.
//
// 29 Oct, "friday should use the cli whenever it can to not use the API... pasting in the api key seems pointless
// for some things": Claude, OpenAI and Gemini are asked through their command when it's on this Mac (claude, codex,
// agy or gemini), signed in as you, and then no key is asked for. Claude Code reads photos and scans itself; OpenAI's
// and Google's commands can't be handed those, so a key for them is offered, quietly, for that alone.

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { query, type Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { Card } from "@/dialogs/SetupParts"
import { useCommand } from "@/hooks/useCommand"
import { useSettings, useStatus } from "@/hooks/queries"
import { useInbox } from "@/inbox/InboxPage"

export type Provider = "claude" | "openai" | "gemini" | "grok" | "muse" | "compatible" | "local"

export interface AiState {
  provider: Provider
  name: string // what the app calls it: "Claude", "GPT", "Gemini", "Grok", "Muse", "AI"
  ready: boolean
  key: boolean
  cli: boolean
  command: string | null // the command it's asked through ("claude", "codex", "agy", "gemini"), when installed
  why: string | null
  note: string | null
  base_url: string | null
  model?: string
}

/** The AI as the server describes it, with its name for labels ("Ask Claude", "Ask Gemini"). */
export function useAi(): AiState {
  const llm = useInbox().data?.llm as Partial<AiState> | undefined
  return {
    provider: (llm?.provider as Provider) ?? "claude",
    name: llm?.name ?? "Claude",
    ready: !!llm?.ready,
    key: !!llm?.key,
    cli: !!llm?.cli,
    command: llm?.command ?? null,
    why: llm?.why ?? null,
    note: llm?.note ?? null,
    base_url: llm?.base_url ?? null,
    model: llm?.model,
  }
}

export const CHOICES: { id: Provider; title: string; note: string; keyFrom?: string }[] = [
  { id: "claude", title: "Claude", note: "Anthropic's. Uses Claude Code on this Mac: no key needed. Else an API key.", keyFrom: "console.anthropic.com" },
  { id: "openai", title: "OpenAI", note: "GPT. Uses the codex command if it's installed (signed in with ChatGPT), else an API key.", keyFrom: "platform.openai.com" },
  { id: "gemini", title: "Gemini", note: "Google's. Uses Google's agy or gemini command if installed (signed in with Google), else an API key.", keyFrom: "aistudio.google.com" },
  { id: "grok", title: "Grok", note: "xAI's, with an API key.", keyFrom: "console.x.ai" },
  { id: "muse", title: "Muse", note: "Meta's, in preview, with an API key from Meta." },
  { id: "compatible", title: "Another service", note: "Anything that speaks OpenAI's API: OpenRouter, Groq, Together, LM Studio…" },
  { id: "local", title: "On this Mac", note: "An open model, downloaded here and run by Ollama: free and private, but slow." },
]

/** Each service's mark and colour, on its card in setup. */
const MARKS: Record<Provider, [string, string]> = {
  claude: ["asterisk", "#e8a07a"],
  openai: ["open-ai-logo", "var(--st-paper)"],
  gemini: ["star-four", "var(--st-class)"],
  grok: ["x-logo", "var(--st-paper)"],
  muse: ["meta-logo", "var(--st-class)"],
  compatible: ["plugs-connected", "var(--st-free)"],
  local: ["laptop", "var(--st-work)"],
}

type Llm = { provider: Provider; model: string; small_model: string; base_url: string | null; daily_calls: number; daily_tokens: number }
type Local = Schemas["LocalModelsOut"]

function useRefresh() {
  const client = useQueryClient()
  return () => ["inbox", "settings", "local_models", "ai_models"].forEach((key) => client.invalidateQueries({ queryKey: [key] }))
}

/** Choose the AI, give its key, choose its model, check it. */
export function AiConnect({ compact = false }: { compact?: boolean }) {
  const ai = useAi()
  const llm = (useSettings().data as { llm?: Llm } | undefined)?.llm
  const demo = !!useStatus().data?.demo
  const save = useCommand("settings_set", { label: () => "Saved" })
  const refresh = useRefresh()
  const local = useLocal(ai.provider === "local")
  const [leaving, setLeaving] = useState<Provider | null>(null) // asked first: Friday's own download goes
  if (!llm) return null
  const choose = async (provider: Provider) => {
    if (provider === llm.provider) return
    const going = friday(local.data, llm)
    if (going && provider !== "local") return setLeaving(provider)
    await save({ key: "llm", value: { provider } })
    refresh()
  }
  const leave = async () => {
    if (leaving) await save({ key: "llm", value: { provider: leaving } })
    setLeaving(null)
    refresh()
  }
  const chosen = CHOICES.find((c) => c.id === llm.provider) ?? CHOICES[0]
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {demo && <span className="fr-kicker">The demo uses a stand-in AI; nothing you choose here is asked.</span>}
      {compact ? (
        // In setup (29 Oct): its cards, each service's mark on it
        <div className="st-cards" role="radiogroup" aria-label="Which AI">
          {CHOICES.map((c, i) => (
            <Card key={c.id} on={c.id === llm.provider} glyph={<Icon name={MARKS[c.id][0]} fill size={22} />} hue={MARKS[c.id][1]} title={c.title} badge={c.id === "muse" ? "preview" : undefined} note={c.note} onPick={() => choose(c.id)} i={i} />
          ))}
        </div>
      ) : (
        <div role="radiogroup" aria-label="Which AI" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))", gap: 8 }}>
          {CHOICES.map((c) => {
            const on = c.id === llm.provider
            return (
              <button
                key={c.id}
                role="radio"
                aria-checked={on}
                className="fr-plain"
                onClick={() => choose(c.id)}
                style={{
                  textAlign: "left",
                  display: "flex",
                  flexDirection: "column",
                  gap: 3,
                  padding: "10px 12px",
                  borderRadius: "var(--radius-md)",
                  background: on ? "color-mix(in srgb, var(--color-accent) 14%, var(--color-surface))" : "var(--color-surface)",
                  boxShadow: on ? "inset 0 0 0 1.5px var(--color-accent)" : "inset 0 0 0 1px color-mix(in srgb, var(--color-text) 8%, transparent)",
                }}
              >
                <span style={{ fontWeight: 500, display: "flex", gap: 6, alignItems: "center" }}>
                  {c.title}
                  {c.id === "muse" && <span className="fr-kicker">preview</span>}
                </span>
                <span className="fr-kicker" style={{ textWrap: "pretty", lineHeight: 1.35 }}>
                  {c.note}
                </span>
              </button>
            )
          })}
        </div>
      )}
      {leaving && (
        <Confirm
          text={`Friday will remove ${llm.model}, which it downloaded to this Mac, and read with ${CHOICES.find((c) => c.id === leaving)?.title}. Models you had before are kept. Downloading it again later takes a while.`}
          yes="Switch and remove it"
          onYes={leave}
          onNo={() => setLeaving(null)}
        />
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {llm.provider === "claude" && <ClaudeSetup ai={ai} />}
        {["openai", "gemini", "grok", "muse"].includes(llm.provider) && <ServiceSetup llm={llm} ai={ai} keyFrom={chosen.keyFrom} />}
        {llm.provider === "compatible" && <OtherSetup llm={llm} ai={ai} />}
        {llm.provider === "local" && <LocalSetup llm={llm} local={local.data} />}
        {!(llm.provider === "local" && local.data?.download?.status === "downloading") && <Status ai={ai} />}
        {ai.ready && <AiCheck />}
      </div>
    </div>
  )
}

/** Whether the local model in use is one Friday downloaded (so it would be removed on leaving it). */
function friday(local: Local | undefined, llm: Llm): Schemas["LocalModel"] | undefined {
  if (llm.provider !== "local" || !local) return undefined
  return [...local.catalog, ...local.others].find((m) => m.friday && full(m.name) === full(llm.model))
}

const full = (name: string) => {
  const n = name.trim().toLowerCase()
  return n.split("/").pop()?.includes(":") ? n : `${n}:latest`
}

function Status({ ai }: { ai: AiState }) {
  return (
    <span style={{ display: "flex", gap: 6, alignItems: "baseline", fontSize: 12, color: ai.ready ? "var(--color-accent-300)" : "var(--fr-warn)" }}>
      <Icon name={ai.ready ? "check-circle" : "warning-circle"} size={13} style={{ flex: "none", position: "relative", top: 2 }} />
      {ai.ready ? `Friday reads with ${ai.name === "AI" ? "it" : ai.name}.` : ai.why?.replace(/ (in|to) Settings → Integrations → AI\.?$/, "")}
    </span>
  )
}

function ClaudeSetup({ ai }: { ai: AiState }) {
  if (ai.cli)
    return <span style={{ fontSize: 13 }}>Uses Claude Code on this Mac, signed in as you: no key needed, photos and scanned PDFs included.</span>
  return (
    <>
      <span style={{ fontSize: 13 }}>Claude Code isn’t installed here: install it (then no key is needed), or add an Anthropic API key.</span>
      <KeyField provider="claude" label="Anthropic API key" has={ai.key} from="console.anthropic.com" />
    </>
  )
}

/** What each command is signed in with, said plainly. */
const SIGNED_IN: Record<string, string> = { codex: "signed in with ChatGPT", agy: "signed in with your Google account", gemini: "signed in with your Google account" }
const TO_INSTALL: Partial<Record<Provider, string>> = {
  openai: "Or install OpenAI’s codex command and sign in with ChatGPT: then no key is needed.",
  gemini: "Or install Google’s agy command and sign in with your Google account: then no key is needed.",
}

function ServiceSetup({ llm, ai, keyFrom }: { llm: Llm; ai: AiState; keyFrom?: string }) {
  const [moved, setMoved] = useState(!!llm.base_url)
  const [withKey, setWithKey] = useState(ai.key)
  const label = `${CHOICES.find((c) => c.id === llm.provider)?.title} API key`
  // Its command on this Mac: no key, and no model to choose (the command picks its own). Photos and scanned PDFs are
  // what it can't be handed, so a key for those alone is offered, out of the way.
  if (ai.command)
    return (
      <>
        <span style={{ fontSize: 13 }}>
          Uses the {ai.command} command on this Mac{SIGNED_IN[ai.command] ? `, ${SIGNED_IN[ai.command]}` : ""}: no key needed.
        </span>
        {withKey ? (
          <KeyField provider={llm.provider} label={label} has={ai.key} optional from={keyFrom} note="Only for photos and scanned PDFs, which the command can't be handed." />
        ) : (
          <button className="fr-link" onClick={() => setWithKey(true)} style={{ alignSelf: "flex-start", fontSize: 12 }}>
            Photos and scanned PDFs need a key: add one
          </button>
        )}
      </>
    )
  return (
    <>
      {ai.note && <span className="fr-kicker">{ai.note}.</span>}
      <KeyField provider={llm.provider} label={label} has={ai.key} from={keyFrom} />
      {TO_INSTALL[llm.provider] && <span className="fr-kicker">{TO_INSTALL[llm.provider]}</span>}
      {ai.key && <ModelPicker llm={llm} />}
      {llm.provider === "muse" &&
        (moved ? <AddressField llm={llm} label="Meta's API address, if it moved" /> : (
          <button className="fr-link" onClick={() => setMoved(true)} style={{ alignSelf: "flex-start", fontSize: 12 }}>
            Use another address
          </button>
        ))}
    </>
  )
}

function OtherSetup({ llm, ai }: { llm: Llm; ai: AiState }) {
  return (
    <>
      <AddressField llm={llm} label="Its address" />
      <span className="fr-kicker">
        For example https://openrouter.ai/api/v1, https://api.groq.com/openai/v1, or http://localhost:1234/v1 for LM Studio.
      </span>
      <KeyField provider="compatible" label="Its API key" has={ai.key} optional note="Leave it empty if the service needs none." />
      {llm.base_url && <ModelPicker llm={llm} free />}
    </>
  )
}

function KeyField(props: { provider: Provider; label: string; has: boolean; optional?: boolean; from?: string; note?: string }) {
  const [key, setKey] = useState("")
  const [editing, setEditing] = useState(!props.has)
  const saveKey = useCommand("ai_key_set", { label: (o) => o.result.message })
  const refresh = useRefresh()
  const submit = async () => {
    if (!key.trim()) return
    if (await saveKey({ provider: props.provider as Schemas["AiKeyInput"]["provider"], key })) {
      setKey("")
      setEditing(false)
      refresh()
    }
  }
  const forget = async () => {
    if (await saveKey({ provider: props.provider as Schemas["AiKeyInput"]["provider"], key: "" })) refresh()
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span className="fr-kicker">
        {props.label}
        {props.optional ? " (optional)" : ""}
        {props.from ? ` · from ${props.from}` : ""}
      </span>
      {props.has && !editing ? (
        <span style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 13 }}>
          <Icon name="key" size={14} />
          A key is saved (kept in secrets.toml, never shown again).
          <button className="fr-link" onClick={() => setEditing(true)} style={{ fontSize: 12 }}>
            Replace
          </button>
          <button className="fr-link" onClick={forget} style={{ fontSize: 12, color: "var(--fr-due)" }}>
            Remove
          </button>
        </span>
      ) : (
        <span style={{ display: "flex", gap: 8, alignItems: "center", maxWidth: 520 }}>
          <input
            id={`ai-key-${props.provider}`}
            className="input"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Paste the key"
            aria-label={props.label}
            style={{ flex: 1, minWidth: 0, padding: "5px 8px", minHeight: 0, fontSize: 13 }}
          />
          <button className="btn btn-primary" onClick={submit} disabled={!key.trim()} style={{ fontSize: 12 }}>
            Save key
          </button>
        </span>
      )}
      {props.note && <span className="fr-kicker">{props.note}</span>}
    </div>
  )
}

function AddressField({ llm, label }: { llm: Llm; label: string }) {
  const [text, setText] = useState(llm.base_url ?? "")
  const save = useCommand("settings_set", { label: () => "Address saved" })
  const refresh = useRefresh()
  const submit = async () => {
    if (text.trim() === (llm.base_url ?? "")) return
    if (await save({ key: "llm", value: { base_url: text.trim() || null } })) refresh()
  }
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span className="fr-kicker">{label}</span>
      <input id="ai-address" className="input" value={text} onChange={(e) => setText(e.target.value)} onBlur={submit} onKeyDown={(e) => e.key === "Enter" && submit()} placeholder="https://…/v1" spellCheck={false} style={{ maxWidth: 520, padding: "5px 8px", minHeight: 0, fontSize: 13 }} />
    </label>
  )
}

/** The service's own models to choose from (names change too often to guess), or a name typed in. */
function ModelPicker({ llm, free = false }: { llm: Llm; free?: boolean }) {
  const listed = useQuery({
    queryKey: ["ai_models", llm.provider, llm.base_url],
    queryFn: () => query("ai_models", { provider: llm.provider, base_url: llm.base_url }),
    staleTime: 60_000,
  })
  const [typed, setTyped] = useState("")
  const save = useCommand("settings_set", { label: () => "Model saved" })
  const refresh = useRefresh()
  const pick = async (model: string) => {
    if (model && (await save({ key: "llm", value: { model, small_model: model } }))) refresh()
  }
  const models = listed.data?.models ?? []
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span className="fr-kicker">Model{llm.model ? `: ${llm.model}` : " (choose one)"}</span>
      {listed.isLoading && <span className="fr-kicker">Asking the service for its models…</span>}
      {listed.data?.error && <span style={{ fontSize: 12, color: "var(--fr-due)" }}>Couldn't list its models: {listed.data.error}</span>}
      {models.length > 0 && (
        <select id="ai-model" className="input" value={models.includes(llm.model) ? llm.model : ""} onChange={(e) => pick(e.target.value)} aria-label="Model" style={{ maxWidth: 520, padding: "5px 8px", minHeight: 0, fontSize: 13 }}>
          <option value="">Choose a model…</option>
          {models.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      )}
      {(free || models.length === 0) && (
        <span style={{ display: "flex", gap: 8, maxWidth: 520 }}>
          <input id="ai-model-name" className="input" value={typed} onChange={(e) => setTyped(e.target.value)} onKeyDown={(e) => e.key === "Enter" && pick(typed.trim())} placeholder="Or type its name" spellCheck={false} style={{ flex: 1, minWidth: 0, padding: "5px 8px", minHeight: 0, fontSize: 13 }} />
          <button className="btn btn-secondary" onClick={() => pick(typed.trim())} disabled={!typed.trim()} style={{ fontSize: 12 }}>
            Use
          </button>
        </span>
      )}
    </div>
  )
}

function useLocal(on: boolean) {
  const [fast, setFast] = useState(false)
  const out = useQuery({
    queryKey: ["local_models"],
    queryFn: async () => {
      const found = await query("local_models")
      setFast(found.download?.status === "downloading" || !found.running)
      return found
    },
    enabled: on,
    refetchInterval: on ? (fast ? 1000 : 10_000) : false,
  })
  return out
}

/** Open models on this Mac: what each costs, which are here, the download, and the switch. */
function LocalSetup({ llm, local }: { llm: Llm; local: Local | undefined }) {
  const use = useCommand("local_model_use", { label: (o) => o.result.message })
  const stop = useCommand("local_model_cancel", { label: (o) => o.result.message })
  const refresh = useRefresh()
  const [typed, setTyped] = useState("")
  const [asking, setAsking] = useState<string | null>(null) // the model to change to, while Friday's own is asked about
  if (!local) return <span className="fr-kicker">Looking for Ollama…</span>
  const going = friday(local, llm)
  const choose = async (name: string) => {
    if (going && full(going.name) !== full(name) && asking !== name) return setAsking(name)
    setAsking(null)
    await use({ name })
    refresh()
  }
  const download = local.download
  const share = download && download.total ? Math.round((100 * download.completed) / download.total) : 0
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div role="note" style={{ display: "flex", gap: 10, padding: "10px 12px", borderRadius: "var(--radius-md)", background: "color-mix(in srgb, var(--fr-warn) 10%, var(--color-surface))", fontSize: 13, textWrap: "pretty" }}>
        <Icon name="hard-drives" size={16} style={{ flex: "none", position: "relative", top: 2 }} />
        <span>{local.warning}</span>
      </div>
      {!local.running ? (
        <span style={{ fontSize: 13, textWrap: "pretty" }}>
          Ollama runs the models. It isn't running here: install it from <b>ollama.com</b> (free), open it, and Friday finds it within a few seconds.
        </span>
      ) : (
        <>
          <span className="fr-kicker">Choose the model to run. You can change it any time; one Friday downloaded is removed when you do, and one you had is kept.</span>
          <div style={{ display: "flex", flexDirection: "column" }}>
            {[...local.catalog, ...local.others].map((m) => (
              <ModelRow key={m.name} m={m} active={!!local.active && full(local.active) === full(m.name)} busy={download?.status === "downloading"} onUse={() => choose(m.name)} />
            ))}
          </div>
          <span style={{ display: "flex", gap: 8, maxWidth: 520 }}>
            <input id="local-model-name" className="input" value={typed} onChange={(e) => setTyped(e.target.value)} onKeyDown={(e) => e.key === "Enter" && typed.trim() && choose(typed.trim())} placeholder="Another model Ollama has, e.g. llama3.1:8b" spellCheck={false} style={{ flex: 1, minWidth: 0, padding: "5px 8px", minHeight: 0, fontSize: 13 }} />
            <button className="btn btn-secondary" onClick={() => choose(typed.trim())} disabled={!typed.trim() || download?.status === "downloading"} style={{ fontSize: 12 }}>
              Use
            </button>
          </span>
        </>
      )}
      {asking && going && (
        <Confirm
          text={`When ${asking} is ready, Friday will remove ${going.name}${going.size_gb ? ` (${going.size_gb} GB)` : ""}, which it downloaded. Models you had before are kept.`}
          yes="Change and remove it"
          onYes={() => choose(asking)}
          onNo={() => setAsking(null)}
        />
      )}
      {download && download.status !== "done" && (
        <div aria-live="polite" style={{ display: "flex", flexDirection: "column", gap: 6, maxWidth: 520 }}>
          {download.status === "downloading" && (
            <>
              <span style={{ fontSize: 13 }}>
                Downloading <b>{download.name}</b>
                {download.total ? ` · ${share}% of ${(download.total / 1e9).toFixed(1)} GB` : ""}. Friday switches to it when it's done; until then the AI you had stays.
              </span>
              <div style={{ height: 6, borderRadius: 3, background: "color-mix(in srgb, var(--color-text) 8%, transparent)", overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${share}%`, background: "var(--color-accent)", transition: "width 0.4s" }} />
              </div>
              <button className="btn btn-ghost" onClick={async () => (await stop({}), refresh())} style={{ alignSelf: "flex-start", fontSize: 12 }}>
                Stop the download
              </button>
            </>
          )}
          {download.status === "failed" && <span style={{ fontSize: 13, color: "var(--fr-due)" }}>Downloading {download.name} failed: {download.error}. The AI you had stays.</span>}
          {download.status === "cancelled" && <span className="fr-kicker">The download of {download.name} was stopped. The AI you had stays.</span>}
        </div>
      )}
    </div>
  )
}

function ModelRow({ m, active, busy, onUse }: { m: Schemas["LocalModel"]; active: boolean; busy: boolean; onUse: () => void }) {
  const size = m.size_gb ? `${m.here ? "" : "about "}${m.size_gb} GB` : ""
  return (
    <div className="fr-row" style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: 12, alignItems: "center", padding: "8px 0" }}>
      <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
          <span style={{ fontWeight: 500 }}>{m.label}</span>
          <span className="fr-kicker mono">{m.name}</span>
          {size && <span className="fr-kicker">{size}</span>}
          {m.here && <span className="fr-kicker" style={{ color: "var(--color-accent-300)" }}>{m.friday ? "on this Mac, downloaded by Friday" : "on this Mac, yours: never removed"}</span>}
        </span>
        {m.note && <span className="fr-kicker">{m.note}</span>}
      </span>
      {active ? (
        <span style={{ fontSize: 12, color: "var(--color-accent-300)", display: "flex", gap: 4, alignItems: "center" }}>
          <Icon name="check" size={12} />
          In use
        </span>
      ) : (
        <button className="btn btn-secondary" onClick={onUse} disabled={busy} style={{ fontSize: 12 }}>
          {m.here ? "Use" : `Download${m.size_gb ? ` · ${m.size_gb} GB` : ""}`}
        </button>
      )}
    </div>
  )
}

function Confirm({ text, yes, onYes, onNo }: { text: string; yes: string; onYes: () => void; onNo: () => void }) {
  return (
    <div role="alertdialog" aria-label="Before you change" style={{ display: "flex", flexDirection: "column", gap: 8, padding: "10px 12px", borderRadius: "var(--radius-md)", background: "var(--color-surface)", boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--fr-warn) 50%, transparent)" }}>
      <span style={{ fontSize: 13, textWrap: "pretty" }}>{text}</span>
      <span style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-primary" onClick={onYes} style={{ fontSize: 12 }}>
          {yes}
        </button>
        <button className="btn btn-ghost" onClick={onNo} style={{ fontSize: 12 }}>
          Cancel
        </button>
      </span>
    </div>
  )
}

/** One tiny question to each model Friday uses, the way Friday asks: a refused key or a retired model shows here. */
export function AiCheck() {
  const [checks, setChecks] = useState<Schemas["ModelCheck"][] | null>(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true)
    setChecks(await query("ai_check").catch((e) => [{ model: "", job: "", ok: false, said: String(e) }]))
    setBusy(false)
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {checks?.map((c) => (
        <span key={c.model + c.job} style={{ display: "flex", gap: 8, fontSize: 12, alignItems: "baseline" }}>
          <Icon name={c.ok ? "check-circle" : "x-circle"} size={14} style={{ color: c.ok ? "var(--color-accent-300)" : "var(--fr-due)", flex: "none" }} />
          <span>
            <b style={{ fontWeight: 500 }}>{c.model}</b> <span className="fr-kicker">({c.job.toLowerCase()})</span>: {c.ok ? "works" : c.said}
          </span>
        </span>
      ))}
      <button className="btn btn-secondary" onClick={run} disabled={busy} style={{ alignSelf: "flex-start", fontSize: 12 }}>
        <Icon name="plugs-connected" />
        {busy ? "Asking…" : "Check it works"}
      </button>
    </div>
  )
}
