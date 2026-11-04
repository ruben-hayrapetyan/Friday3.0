// "I worked on this": time spent without the timer, on a task's page (3 Nov: `log` had no button). It counts as done
// and as how long that kind of work takes, as a timed sitting does.

import { useState } from "react"
import { TimeInput } from "@/components/fr/TimeInput"
import { Icon, Menu } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { spanOn } from "@/lib/ampm"
import { dur } from "@/lib/format"
import { lastHour, recentDays } from "./workedTimes"

export function LogWork({ itemId, title, today, now, onDone }: { itemId: number; title: string; today: string; now: string; onDone: () => void }) {
  const guess = lastHour(now)
  const [day, setDay] = useState(today)
  const [from, setFrom] = useState(guess.from)
  const [to, setTo] = useState(guess.to)
  const log = useCommand("log", { label: () => `Logged time on ${title}` })
  const span = spanOn(day, from, to)
  const minutes = Math.max(0, (Date.parse(`${span.end}:00Z`) - Date.parse(`${span.start}:00Z`)) / 60000)
  const save = async () => {
    if (await log({ id: itemId, start: span.start, end: span.end })) onDone()
  }
  return (
    <div role="group" aria-label="Time you worked" onKeyDown={(e) => e.key === "Enter" && save()} className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 8, padding: 12 }}>
      <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>Time you worked on it without the timer:</span>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <Menu label="Day" value={day} onPick={setDay} options={recentDays(today)} />
        <TimeInput value={from} onChange={(t) => t && setFrom(t)} label="Started" expect={{ near: from }} style={{ width: 96, padding: "4px 8px", minHeight: 0, fontSize: 13 }} />
        <span style={{ color: "var(--color-neutral-500)" }}>–</span>
        <TimeInput value={to} onChange={(t) => t && setTo(t)} label="Stopped" expect={{ after: from }} style={{ width: 96, padding: "4px 8px", minHeight: 0, fontSize: 13 }} />
        <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>{dur(minutes)}</span>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-primary fr-press" onClick={save} style={{ fontSize: 12 }}>
          <Icon name="check" />
          Log it
        </button>
        <button className="btn btn-ghost" onClick={onDone} style={{ fontSize: 12 }}>
          Cancel
        </button>
      </div>
    </div>
  )
}
