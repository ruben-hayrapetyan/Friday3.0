// Settings → Updates: the version you have, when Friday last looked, Check now, and when a
// downloaded update goes in (H146). Friday Test and a server run from the code never look, and say so (H169).
// Test user (H224): the code you were given, typed here; then which name the site knows it by, and a way to stop.

import { useState } from "react"
import { useToast } from "@/components/Toasts"
import { useShell } from "@/shell/ShellContext"
import { Seg } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings } from "@/hooks/queries"
import { headline, lookedAgo, newest, testCode, testUserLine, type UpdateStatus, useUpdateAct, useUpdates } from "@/updates/updates"
import { Field, SectionHead } from "./SettingsPage"

const RESTART = [
  { value: "now" as const, label: "Right away" },
  { value: "quit" as const, label: "When I quit Friday" },
]

export function UpdatesSection() {
  const status = useUpdates().data
  const act = useUpdateAct()
  const { setDialog } = useShell()
  const updates = (useSettings().data as Record<string, unknown> | undefined)?.updates as { restart: "now" | "quit" } | undefined
  const save = useCommand("settings_set", { label: () => "Saved" })
  const busy = status?.state === "checking" || status?.state === "downloading"
  return (
    <>
      <SectionHead title="Updates" note="Friday looks for a new version when it opens, when you come back to it after six hours or more, and once a day, and asks before updating." />
      <Field name="Version" note={status?.checks ? undefined : "This copy doesn't check for updates; Friday Test and copies run from code never do."}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          {status?.checks && (
            <button className="btn btn-secondary" onClick={() => act("update_check")} disabled={busy}>
              Check now
            </button>
          )}
          {status?.checks && newest(status) && !busy && (
            <button className="btn btn-primary" onClick={() => setDialog("update")}>
              See what's new
            </button>
          )}
          <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ fontWeight: 500 }}>{status ? headline(status) : "…"}</span>
            <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
              You have {status?.have ?? "a build from here"}
              {status?.checks ? ` · ${lookedAgo(status.last_checked, new Date())}` : ""}
            </span>
          </span>
        </div>
        {status?.message && <span style={{ color: "var(--fr-warn)" }}>{status.message}</span>}
      </Field>
      {status?.checks && <TestUserField status={status} />}
      <Field name="After updating" note="Restart into a downloaded update right away, or install it when you quit.">
        <Seg options={RESTART} value={updates?.restart ?? "now"} onPick={(restart) => save({ key: "updates", value: { restart } })} label="When an update goes in" />
      </Field>
    </>
  )
}

function TestUserField({ status }: { status: UpdateStatus }) {
  const act = useUpdateAct()
  const toast = useToast()
  const [typed, setTyped] = useState("")
  const user = status.test_user
  const code = testCode(typed)
  const join = async (given: string) => {
    if (await act("update_test_join", { code: given })) setTyped("")
  }
  const leave = async () => {
    const had = user?.code
    if (!(await act("update_test_leave"))) return
    toast({ message: "You're no longer a test user. You keep the version you have.", action: had ? { label: "Undo", run: () => void act("update_test_join", { code: had }) } : undefined })
  }
  return (
    <Field name="Test user" note="Test users get new versions before everyone else, with a code they were given.">
      {user ? (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <button className="btn btn-secondary" onClick={leave}>
              Stop being a test user
            </button>
            <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ fontWeight: 500 }}>{testUserLine(user, status.state)}</span>
              <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>Code {user.code}</span>
            </span>
          </div>
          {user.known === false && <span style={{ color: "var(--fr-warn)" }}>Check the code with whoever gave it to you: they may have removed it. Until then Friday gets the versions everyone gets.</span>}
        </>
      ) : (
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <input className="input" value={typed} onChange={(e) => setTyped(e.target.value)} onKeyDown={(e) => e.key === "Enter" && code && join(code)} placeholder="Code, e.g. K7QF-29XM" aria-label="Test user code" spellCheck={false} autoComplete="off" style={{ width: 200, padding: "5px 8px", minHeight: 0 }} />
          <button className="btn btn-secondary" disabled={!code} onClick={() => code && join(code)}>
            Join
          </button>
        </div>
      )}
    </Field>
  )
}
