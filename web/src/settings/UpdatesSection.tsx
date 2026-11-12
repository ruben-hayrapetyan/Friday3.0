// Settings → Updates (HOSTED.md H147): the version you have, when Friday last looked, Check now, and when a
// downloaded update goes in (H146). Friday Test and a server run from the code never look, and say so (H169).

import { useShell } from "@/shell/ShellContext"
import { Seg } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings } from "@/hooks/queries"
import { headline, lookedAgo, newest, useUpdateAct, useUpdates } from "@/updates/updates"
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
      <SectionHead title="Updates" note="Friday looks for a new version when it opens and once a month, and asks before updating." />
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
      <Field name="After updating" note="Restart into a downloaded update right away, or install it when you quit.">
        <Seg options={RESTART} value={updates?.restart ?? "now"} onPick={(restart) => save({ key: "updates", value: { restart } })} label="When an update goes in" />
      </Field>
    </>
  )
}
