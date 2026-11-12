// Settings → Phone (C61, 8 Nov: your phone's browser over Tailscale, everything Friday does; paired by scanning a QR
// code; paired until you remove it). The switch makes Friday answer on this Mac's Tailscale address too; a phone
// opens Friday only once paired. Everything stays on this Mac: the phone is a window onto it, so the Mac must be on
// and awake for the phone to reach it.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query, type Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import { SectionHead } from "./SettingsPage"

export function Phone() {
  const { today } = useShell()
  const status = useQuery({ queryKey: ["phone_status"], queryFn: () => query("phone_status"), refetchInterval: 10_000 }).data
  const set = useCommand("phone_set", { label: (o) => o.result.message ?? "Saved" })
  const forget = useCommand("phone_forget", { label: (o) => o.result.message ?? "Removed" })
  const pairing = useCommand("phone_pair", { quiet: true })
  const [code, setCode] = useState<Schemas["PairCode"] | null>(null)
  if (!status) return null
  const where = status.name ?? status.address
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <SectionHead title="Phone" note="Use Friday in your phone’s browser over Tailscale. Your data stays on this Mac." />
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Switch on={status.on} onToggle={() => (setCode(null), set({ on: !status.on }))} label="Use Friday on my phone" />
        <span style={{ fontWeight: 500 }}>Use Friday on my phone</span>
      </div>
      <span className="fr-kicker" style={{ color: status.on && !where ? "var(--fr-warn)" : undefined }}>
        {!status.on
          ? "Off: Friday answers on this Mac alone."
          : where
            ? `On at ${where}. Your Mac must be awake for your phone to reach it.`
            : "This Mac isn't on Tailscale. Open Tailscale and sign in; Friday is reachable within seconds."}
      </span>
      {status.on && where && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {code ? (
            <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
              {/* the server's own SVG (segno), never anything typed in */}
              <span aria-label="Pairing code to scan" role="img" style={{ width: 180, lineHeight: 0, borderRadius: 8, overflow: "hidden" }} dangerouslySetInnerHTML={{ __html: code.svg.replace("<svg ", '<svg width="180" height="180" ') }} />
              <span style={{ display: "flex", flexDirection: "column", gap: 6, maxWidth: 320 }}>
                <span>Point your phone's camera at the code and open the link. That phone is then paired until you remove it here.</span>
                <span className="fr-kicker">Works once, for {code.minutes} minutes. Your phone needs Tailscale on, with the same account.</span>
                <button className="btn btn-ghost" onClick={() => setCode(null)} style={{ alignSelf: "flex-start", fontSize: 12 }}>
                  Hide the code
                </button>
              </span>
            </div>
          ) : (
            <button className="btn btn-primary" onClick={async () => setCode((await pairing({}))?.result ?? null)} style={{ alignSelf: "flex-start" }}>
              <Icon name="qr-code" />
              Pair a phone
            </button>
          )}
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column" }}>
        <span className="fr-eyebrow">Paired</span>
        {status.phones.length === 0 && <span className="fr-kicker">No phone yet.</span>}
        {status.phones.map((p) => (
          <div key={p.id} className="fr-row" style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: 12, alignItems: "center", padding: "10px 0" }}>
            <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ fontWeight: 500 }}>{p.name}</span>
              <span className="fr-kicker">
                Paired {when(p.paired, today)}
                {p.last_used ? ` · last opened ${when(p.last_used, today)}` : " · not opened yet"}
              </span>
            </span>
            <button className="btn btn-ghost" onClick={() => forget({ id: p.id })} title="It can't open Friday until it's paired again" style={{ fontSize: 12, color: "var(--fr-due)" }}>
              Remove
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
