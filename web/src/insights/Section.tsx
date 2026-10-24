// One Insights section: a title, a note beside it, something on the right, then the content.

import { H } from "@/components/fr/controls"

export function Section({ title, note, right, children }: { title: string; note: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="fr-row" style={{ display: "flex", flexDirection: "column", gap: 14, paddingTop: 24, minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <H size={20}>{title}</H>
        <span className="fr-kicker">{note}</span>
        <span style={{ flex: 1 }} />
        {right}
      </div>
      {children}
    </section>
  )
}
