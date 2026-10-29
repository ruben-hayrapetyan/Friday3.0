// Your day, in the Inbox (29 Oct: "merge the "review" section into inbox because I don't want a review section
// anymore"): what Review was, unchanged. Only what Friday can't tell on its own, by task (DailyReview). Yesterday
// comes first while it has something to answer. The week's look back is in Insights → This week.

import { useEffect, useState } from "react"
import { NavLink } from "react-router"
import { Icon, Seg } from "@/components/fr/controls"
import { addDays } from "@/lib/time"
import { useShell } from "@/shell/ShellContext"
import { DailyReview, useReviewDay, useReviewOpen } from "./DailyReview"

/** What the Inbox's link to Your day says: the day with something to answer, and how many. */
export function dayCard({ yesterday, today }: { yesterday: number; today: number }): { title: string; note: string } {
  const note = "Planned time you didn't time or mark, and sleep taps you missed"
  if (yesterday && today) return { title: `Yesterday and today: ${yesterday + today} to answer`, note }
  if (yesterday) return { title: `Yesterday: ${yesterday} to answer`, note }
  if (today) return { title: `Today: ${today} to answer`, note }
  return { title: "Your day: all answered", note: "Change an answer, or say how today went" }
}

/** The Inbox's way to Your day, with what's left to answer (the dot that was on Review). */
export function YourDayLink() {
  const left = useReviewOpen()
  const said = dayCard(left)
  return (
    <NavLink to="/inbox/day" className="fr-well fr-hover" style={{ display: "flex", gap: 10, alignItems: "center", padding: "10px 12px", color: "var(--color-text)", textDecoration: "none" }}>
      <Icon name="cards" size={16} style={{ color: "var(--color-accent-300)" }} />
      <span style={{ flex: 1, display: "flex", flexDirection: "column", gap: 1, fontSize: 12 }}>
        <span>{said.title}</span>
        <span style={{ color: "var(--color-neutral-500)" }}>{said.note}</span>
      </span>
      {left.yesterday + left.today > 0 && <span aria-hidden style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--color-accent)" }} />}
      <Icon name="caret-right" size={13} />
    </NavLink>
  )
}

export function YourDay() {
  const { today } = useShell()
  const first = useReviewDay()
  // The day stays put once chosen: answering yesterday's last row shows it answered, not today.
  const [date, setDate] = useState<string | null>(null)
  useEffect(() => {
    if (first && date === null) setDate(first)
  }, [first, date])
  const shown = date ?? first ?? today
  const yesterday = addDays(today, -1)
  return (
    <>
      <div className="fr-page-head" style={{ gap: 12 }}>
        <NavLink to="/inbox" className="fr-link" style={{ fontSize: 13 }}>
          ← Inbox
        </NavLink>
        <span className="fr-h fr-title">Your day</span>
        <Seg
          options={[
            { value: yesterday, label: "Yesterday" },
            { value: today, label: "Today" },
          ]}
          value={shown}
          onPick={setDate}
        />
        <div style={{ flex: 1 }} />
        <span className="fr-kicker fr-head-note">1–4 answer the first row</span>
      </div>
      <DailyReview key={shown} date={shown} />
    </>
  )
}
