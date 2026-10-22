// Notifications (v22): which ones fire and when, where they go (this browser, ntfy), quiet hours, a daily limit and
// holding them while you work; a preview of the selected one with its actions, and a test.

import { useEffect, useState } from "react"
import { query } from "@/api/client"
import { H, Icon, Seg, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings } from "@/hooks/queries"


interface Notify {
  channels: ("webpush" | "ntfy")[]
  ntfy_url: string | null
  app_url: string | null
  brief_at: string | null
  review_at: string | null
  max_per_day: number
  types: Record<string, boolean>
  quiet: [string, string] | null
  hold_while_timing: boolean
  contact: string
}

const KINDS: { kind: string; name: string; desc: string; time?: "brief_at" | "review_at"; preview: [string, string, string[]] }[] = [
  { kind: "morning_brief", name: "Morning brief", desc: "What matters today, half an hour after you wake", time: "brief_at", preview: ["Today", "PS5 09:00–12:00, Project draft 14:00. 6.5 h in all.", ["Open", "Start PS5"]] },
  { kind: "block_start", name: "A block starts", desc: "When planned work begins", preview: ["PS5 starts now", "Until 12:00, then lunch.", ["Start", "Snooze 15 min", "Skip"]] },
  { kind: "slack_low", name: "Deadline warning", desc: "When hard work must start soon to be on time", preview: ["Start the project draft by 10:30", "Due Thu 23:59 and 5 h are left.", ["Start now", "Options"]] },
  { kind: "overload", name: "Too much to fit", desc: "When work won’t fit before its deadlines", preview: ["Wednesday is 2.5 h over", "Friday found ways to make it fit.", ["See options"]] },
  { kind: "conflict", name: "A lock gets in the way", desc: "When something you locked makes work late", preview: ["A lock makes PS6 late", "Unlock it, or accept the lateness.", ["Decide"]] },
  { kind: "check", name: "Did you finish it?", desc: "After a hard item’s last planned block", preview: ["Did you finish PS5?", "Its last block ended at 12:00.", ["Yes, done", "Not yet"]] },
  { kind: "evening_review", name: "Evening review", desc: "Look back on the day, an hour before bed", time: "review_at", preview: ["How did today go?", "4 blocks to look back on. About a minute.", ["Review"]] },
  { kind: "weekly_review", name: "Weekly review", desc: "On the week’s last evening", preview: ["Your week", "See how the week went and plan the next.", ["Review"]] },
]

export function Notifications() {
  const saved = (useSettings().data as Record<string, unknown> | undefined)?.notify as Notify | undefined
  const set = useCommand("settings_set", { label: () => "Saved" })
  const test = useCommand("notify_test", { label: (o) => o.result.message ?? "Test sent" })
  const [selected, setSelected] = useState("morning_brief")
  if (!saved) return null
  const save = (change: Partial<Notify>) => set({ key: "notify", value: { ...saved, ...change } })
  const shown = KINDS.find((k) => k.kind === selected) ?? KINDS[0]
  const where = saved.channels.includes("ntfy") ? "ntfy" : saved.channels.includes("webpush") ? "push" : "app"
  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, paddingBottom: 14 }}>
        <H size={30}>Notifications</H>
        <span style={{ color: "var(--color-neutral-400)" }}>Each one has an action you can take right from it. Choose which ones fire, when, and where.</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 300px", gap: 28, alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column" }}>
          {KINDS.map((k) => {
            const on = saved.types[k.kind] ?? true
            return (
              <div key={k.kind} onClick={() => setSelected(k.kind)} className="fr-row" style={{ display: "grid", gridTemplateColumns: "36px minmax(0,1fr)", gap: "8px 14px", alignItems: "center", padding: "12px 10px", margin: "0 -10px", borderRadius: "var(--radius-md)", background: selected === k.kind ? "color-mix(in srgb, var(--color-accent) 8%, transparent)" : undefined, cursor: "pointer", opacity: on ? 1 : 0.55 }}>
                <Switch on={on} onToggle={() => save({ types: { ...saved.types, [k.kind]: !on } })} label={`${on ? "Turn off" : "Turn on"} ${k.name}`} />
                <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                  <span style={{ fontWeight: 500 }}>{k.name}</span>
                  <span className="fr-kicker">{k.desc}</span>
                </span>
                {k.time && selected === k.kind && on && (
                  <>
                    <span />
                    <label style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }}>
                      At
                      <input type="time" step={900} className="input" value={saved[k.time] ?? ""} onChange={(e) => save({ [k.time as string]: e.target.value || null })} style={{ width: 110, padding: "3px 8px", minHeight: 0 }} />
                      <span className="fr-kicker">Empty: {k.time === "brief_at" ? "30 min after you wake" : "an hour before bed"}</span>
                    </label>
                  </>
                )}
              </div>
            )
          })}
          <div className="fr-row" style={{ display: "flex", flexDirection: "column", gap: 14, paddingTop: 22, marginTop: 6 }}>
            <H size={18}>Delivery</H>
            <Line label="Where">
              <Seg
                options={[
                  { value: "app", label: "In the app" },
                  { value: "push", label: "Push" },
                  { value: "ntfy", label: "Push and ntfy" },
                ]}
                value={where}
                onPick={(v) => save({ channels: v === "app" ? [] : v === "push" ? ["webpush"] : ["webpush", "ntfy"] })}
              />
            </Line>
            {where !== "app" && <ThisBrowser />}
            {where === "ntfy" && (
              <Line label="ntfy topic">
                <input className="input" placeholder="https://ntfy.sh/your-topic" defaultValue={saved.ntfy_url ?? ""} onBlur={(e) => save({ ntfy_url: e.target.value || null })} style={{ maxWidth: 320, padding: "3px 8px", minHeight: 0 }} />
              </Line>
            )}
            <Line label="Quiet hours">
              <Switch on={!!saved.quiet} onToggle={() => save({ quiet: saved.quiet ? null : ["22:00", "08:00"] })} label="Quiet hours" />
              {saved.quiet ? (
                <>
                  <input type="time" step={900} className="input" value={saved.quiet[0]} onChange={(e) => save({ quiet: [e.target.value, saved.quiet?.[1] ?? "08:00"] })} style={{ width: 100, padding: "3px 8px", minHeight: 0 }} />
                  <span className="fr-kicker">to</span>
                  <input type="time" step={900} className="input" value={saved.quiet[1]} onChange={(e) => save({ quiet: [saved.quiet?.[0] ?? "22:00", e.target.value] })} style={{ width: 100, padding: "3px 8px", minHeight: 0 }} />
                </>
              ) : (
                <span className="fr-kicker">From bedtime until you wake</span>
              )}
            </Line>
            <Line label="Daily limit">
              <button className="btn btn-icon btn-secondary" onClick={() => save({ max_per_day: Math.max(0, saved.max_per_day - 1) })} aria-label="Fewer" style={{ width: 26, height: 26 }}>
                <Icon name="minus" />
              </button>
              <span className="tnum" style={{ minWidth: 110, textAlign: "center" }}>
                {saved.max_per_day} a day
              </span>
              <button className="btn btn-icon btn-secondary" onClick={() => save({ max_per_day: saved.max_per_day + 1 })} aria-label="More" style={{ width: 26, height: 26 }}>
                <Icon name="plus" />
              </button>
              <span className="fr-kicker">Deadline warnings always get through</span>
            </Line>
            <Line label="While working">
              <Switch on={saved.hold_while_timing} onToggle={() => save({ hold_while_timing: !saved.hold_while_timing })} label="Hold while working" />
              <span style={{ fontSize: 12, color: "var(--color-neutral-300)" }}>Hold everything except deadline warnings while a block’s timer is running</span>
            </Line>
          </div>
        </div>
        <div style={{ position: "sticky", top: 0, display: "flex", flexDirection: "column", gap: 10 }}>
          <span className="fr-kicker">Preview: {shown.name}</span>
          <div className="fr-float" style={{ display: "flex", flexDirection: "column", gap: 10, padding: "12px 14px", borderRadius: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "var(--color-neutral-400)" }}>
              <span style={{ width: 16, height: 16, background: "var(--color-accent)", borderRadius: 4 }} />
              <span style={{ flex: 1 }}>Friday</span>
              <span className="tnum">now</span>
            </div>
            <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ fontWeight: 600 }}>{shown.preview[0]}</span>
              <span style={{ fontSize: 13, color: "var(--color-neutral-300)" }}>{shown.preview[1]}</span>
            </span>
            <div className="fr-row" style={{ display: "grid", gridAutoFlow: "column", gridAutoColumns: "1fr", gap: 1, margin: "2px -14px -12px" }}>
              {shown.preview[2].map((a, i) => (
                <span key={a} style={{ padding: "9px 4px", textAlign: "center", fontSize: 12, fontWeight: 500, color: i === 0 ? "var(--color-accent-300)" : "var(--color-text)" }}>
                  {a}
                </span>
              ))}
            </div>
          </div>
          <span className="fr-kicker" style={{ textWrap: "pretty" }}>
            Tapping it opens Friday where you can act; the buttons work right from the notification.
          </span>
          <button className="btn btn-secondary" onClick={() => test({})} style={{ alignSelf: "flex-start", fontSize: 12 }}>
            <Icon name="paper-plane-tilt" />
            Send a test
          </button>
        </div>
      </div>
    </>
  )
}

function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
      <span style={{ width: 110, fontSize: 12, color: "var(--color-neutral-400)" }}>{label}</span>
      {children}
    </div>
  )
}

/** Web Push on this browser: ask permission, subscribe with the server's key, tell the server. */
function ThisBrowser() {
  const [state, setState] = useState<"unknown" | "on" | "off" | "unsupported">("unknown")
  const [error, setError] = useState<string | null>(null)
  const subscribe = useCommand("push_subscribe")
  const unsubscribe = useCommand("push_unsubscribe")
  useEffect(() => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !window.isSecureContext) return setState("unsupported")
    navigator.serviceWorker.ready.then((r) => r.pushManager.getSubscription()).then((s) => setState(s ? "on" : "off"))
  }, [])
  const turnOn = async () => {
    setError(null)
    try {
      if ((await Notification.requestPermission()) !== "granted") throw new Error("notifications aren't allowed for this site")
      const { key } = await query("push_key")
      if (!key) throw new Error("fridayd has no push key yet; restart it")
      const registration = await navigator.serviceWorker.ready
      const sub = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: fromBase64(String(key)) })
      const json = sub.toJSON()
      if (await subscribe({ endpoint: json.endpoint ?? "", keys: json.keys ?? {} })) setState("on")
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  const turnOff = async () => {
    const sub = await (await navigator.serviceWorker.ready).pushManager.getSubscription()
    if (sub) {
      await unsubscribe({ endpoint: sub.endpoint })
      await sub.unsubscribe()
    }
    setState("off")
  }
  return (
    <Line label="This browser">
      {state === "unsupported" ? (
        <span className="fr-kicker">Push needs the installed app over HTTPS (localhost works; on a phone use `tailscale serve`). ntfy works without.</span>
      ) : (
        <>
          <span style={{ fontSize: 12 }}>{state === "on" ? "Notifications on" : "Notifications off"}</span>
          <button className="btn btn-secondary" onClick={state === "on" ? turnOff : turnOn} disabled={state === "unknown"} style={{ fontSize: 12, padding: "3px 10px" }}>
            {state === "on" ? "Turn off" : "Turn on"}
          </button>
          {error && <span style={{ fontSize: 12, color: "var(--fr-due)" }}>{error}</span>}
        </>
      )}
    </Line>
  )
}

function fromBase64(text: string): Uint8Array<ArrayBuffer> {
  const raw = atob((text + "=".repeat((4 - (text.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/"))
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

