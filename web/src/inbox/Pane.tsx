// A message opened beside the Inbox's list: what it is in a line, its title, what it says and how to deal with it
// (29 Oct: every kind of thing waiting is a message, opened the same way).

import type { ReactNode } from "react"
import { H, Icon } from "@/components/fr/controls"

export function Pane({ icon, kicker, title, warn, children }: { icon: string; kicker: ReactNode; title: ReactNode; warn?: boolean; children: ReactNode }) {
  return (
    <div className="fr-gutter" style={{ overflowY: "auto", minHeight: 0, padding: "24px 28px 80px" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 680 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: warn ? "var(--fr-warn)" : "var(--color-neutral-400)" }}>
            <Icon name={icon} size={14} style={{ color: warn ? "var(--fr-warn)" : "var(--color-accent-300)" }} />
            {kicker}
          </span>
          <H size={30}>{title}</H>
        </div>
        {children}
      </div>
    </div>
  )
}

/** The buttons that deal with a message. */
export function Actions({ children }: { children: ReactNode }) {
  return <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", paddingTop: 2 }}>{children}</div>
}

/** A quieter line under the actions: what happens, or the same for all of its kind. */
export function After({ children }: { children: ReactNode }) {
  return <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)", textWrap: "pretty" }}>{children}</div>
}
