// Review (27 Oct): only what Friday can't tell on its own, by task (DailyReview). Yesterday comes first while it has
// something to answer. The week's look back is in Insights → This week.

import { useEffect, useState } from "react"
import { Seg } from "@/components/fr/controls"
import { addDays } from "@/lib/time"
import { useShell } from "@/shell/ShellContext"
import { DailyReview, useReviewDay } from "./DailyReview"

export function ReviewPage() {
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
      <div className="fr-page-head">
        <span className="fr-h fr-title">Review</span>
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
