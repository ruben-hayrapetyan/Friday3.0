// The update popup at launch (H124: "a popup that shows up the next time it launches") with every newer version's
// notes, Later and Update; then the download with its seconds counting and Stop, which you can close and keep
// working; and once the new version first opens, what changed in it, shown once (H118). Settings → Updates opens
// the same popup (`dialog === "update"`).

import { useEffect, useState } from "react"
import { H, Icon } from "@/components/fr/controls"
import { Modal } from "@/dialogs/Dialogs"
import { useShell } from "@/shell/ShellContext"
import { headline, newest, progressLine, type UpdateStatus, type UpdateVersion, useSwapWhenReady, useUpdateAct, useUpdates } from "./updates"

const SECTIONS = [["new", "New"], ["changed", "Changed"], ["fixed", "Fixed"]] as const

/** One version's notes: its sentence, then New, Changed and Fixed (a heading only when it has lines; H143). */
export function Notes({ version, titled }: { version: UpdateVersion; titled: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {titled && <H size={18}>Friday {version.version}</H>}
      <span style={{ textWrap: "pretty" }}>{version.summary}</span>
      {SECTIONS.map(([key, title]) =>
        version[key]?.length ? (
          <div key={key} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span className="fr-kicker">{title}</span>
            <ul style={{ margin: 0, paddingLeft: 18, listStyle: "disc", display: "flex", flexDirection: "column", gap: 2 }}>
              {version[key]?.map((line) => <li key={line}>{line}</li>)}
            </ul>
          </div>
        ) : null,
      )}
    </div>
  )
}

function useSeconds(running: boolean): number {
  const [began, setBegan] = useState<number | null>(null)
  const [, tick] = useState(0)
  useEffect(() => {
    if (!running) return setBegan(null)
    setBegan((b) => b ?? Date.now())
    const timer = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(timer)
  }, [running])
  return began === null ? 0 : (Date.now() - began) / 1000
}

function Progress({ status, onStop, onClose }: { status: UpdateStatus; onStop: () => void; onClose: () => void }) {
  const seconds = useSeconds(status.state === "downloading")
  const done = status.state === "ready"
  const quitting = status.restart === "quit"
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ height: 6, borderRadius: 3, background: "color-mix(in srgb, var(--color-text) 10%, transparent)", overflow: "hidden" }}>
        <div style={{ width: `${Math.round((done ? 1 : (status.progress ?? 0)) * 100)}%`, height: "100%", background: "var(--color-accent)", transition: "width .4s" }} />
      </div>
      {done ? (
        <span>{quitting ? "It goes in when you quit Friday, and opens the next time you do." : "Friday is restarting into it…"}</span>
      ) : (
        <>
          <span className="tnum" style={{ color: "var(--color-neutral-400)" }}>{progressLine(status.progress ?? 0, seconds)}</span>
          <span style={{ fontSize: 13, color: "var(--color-neutral-400)" }}>You can close this and keep working; Friday carries on.</span>
        </>
      )}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        {!done && (
          <button className="btn btn-secondary" onClick={onStop} title="Stop downloading; nothing changes">
            Stop
          </button>
        )}
        <button className="btn btn-primary" onClick={onClose}>
          {done ? "OK" : "Close"}
        </button>
      </div>
    </div>
  )
}

export function UpdateDialogs() {
  const { dialog, setDialog } = useShell()
  const status = useUpdates().data
  const act = useUpdateAct()
  const [closed, setClosed] = useState(false)
  useSwapWhenReady(status)
  if (!status) return null
  const asked = dialog === "update"
  const working = status.state === "downloading" || status.state === "ready"
  const open = asked || (!closed && (status.popup || working))
  if (status.whats_new?.length && !open) return <WhatsNew status={status} onSeen={() => act("whats_new_seen")} />
  if (!open || !newest(status)) return null
  const close = () => {
    setClosed(true)
    if (asked) setDialog(null)
  }
  const later = () => {
    if (!working) void act("update_later")
    close()
  }
  const versions = status.versions ?? []
  return (
    <Modal onClose={later} width={560} label="Update Friday">
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
          <H size={24}>{working ? headline(status) : `Friday ${newest(status)?.version} is ready`}</H>
          <span style={{ fontSize: 13, color: "var(--color-neutral-400)" }}>You have {status.have}</span>
        </div>
        <button className="btn btn-icon btn-ghost" onClick={later} aria-label="Close" style={{ width: 28, height: 28 }}>
          <Icon name="x" />
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 18, maxHeight: "50vh", overflowY: "auto" }}>
        {versions.map((v) => (
          <Notes key={v.version} version={v} titled={versions.length > 1} />
        ))}
      </div>
      {status.message && <span style={{ color: "var(--fr-warn)" }}>{status.message}</span>}
      {working ? (
        <Progress status={status} onStop={() => act("update_stop")} onClose={close} />
      ) : (
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn btn-secondary" onClick={later} title="Ask again the next time Friday opens">
            Later
          </button>
          <button className="btn btn-primary" onClick={() => (setClosed(false), act("update_start"))}>
            Update
          </button>
        </div>
      )}
    </Modal>
  )
}

/** The first time a new version opens: what changed since the one you had, once (H118). */
function WhatsNew({ status, onSeen }: { status: UpdateStatus; onSeen: () => void }) {
  const versions = status.whats_new ?? []
  return (
    <Modal onClose={onSeen} width={560} label={`What's new in Friday ${status.have}`}>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span className="fr-kicker">Updated</span>
        <H size={24}>What's new in Friday {status.have}</H>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 18, maxHeight: "55vh", overflowY: "auto" }}>
        {versions.map((v) => (
          <Notes key={v.version} version={v} titled={versions.length > 1} />
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button className="btn btn-primary" onClick={onSeen}>
          Got it
        </button>
      </div>
    </Modal>
  )
}
