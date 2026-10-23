// Review (v22): the day's cards, or the week. The week is suggested on the week's last day.

import { useState } from "react"
import { Seg } from "@/components/fr/controls"
import { useSettings } from "@/hooks/queries"
import { weekday } from "@/lib/format"
import { addDays } from "@/lib/time"
import { useShell } from "@/shell/ShellContext"
import { DailyReview, useReviewDay } from "./DailyReview"
import { WeeklyReview } from "./WeeklyReview"

export function ReviewPage() {
  const { today } = useShell()
  const settings = useSettings().data as Record<string, { week_start?: string }> | undefined
  const weekStart = settings?.time?.week_start ?? "mon"
  const lastDay = weekday(addDays(today, 1)).toLowerCase() === weekStart
  const [mode, setMode] = useState<"Day" | "Week">(lastDay ? "Week" : "Day")
  const date = useReviewDay()
  const suggested = lastDay ? "Week" : "Day"
  return (
    <>
      <div className="fr-page-head">
        <span className="fr-h fr-title">Review</span>
        <Seg
          options={(["Day", "Week"] as const).map((m) => ({
            value: m,
            label: (
              <>
                {m}
                {m === suggested && <span style={{ fontSize: 10, color: "var(--color-accent-300)" }}>suggested</span>}
              </>
            ),
          }))}
          value={mode}
          onPick={setMode}
        />
        <div style={{ flex: 1 }} />
        <span className="fr-kicker">{mode === "Day" ? "1–4 to answer, ← to go back" : "Choices apply when you finish"}</span>
      </div>
      {mode === "Day" ? <DailyReview key={date} date={date} onWeek={() => setMode("Week")} /> : <WeeklyReview />}
    </>
  )
}
