// Sleep & meals: what you tell Friday about your nights and your meals, each with its own switch (off until you turn
// it on). The Now bar asks at the right moments; this page is for a tap you missed, one to log after the fact, and the
// last two weeks to put right. What Friday makes of them is in Insights.

import { useNavigate, useSearchParams } from "react-router"
import { Seg } from "@/components/fr/controls"
import { MealLog } from "./MealLog"
import { SleepLog } from "./SleepLog"

const TABS = [
  { value: "sleep", label: "Sleep" },
  { value: "meals", label: "Meals" },
] as const

export function BodyPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const tab = params.get("tab") === "meals" ? "meals" : "sleep"
  return (
    <>
      <div className="fr-page-head">
        <span className="fr-h fr-title">Sleep &amp; meals</span>
        <Seg options={TABS} value={tab} onPick={(t) => setParams({ tab: t }, { replace: true })} />
        <div style={{ flex: 1 }} />
        <button className="fr-link fr-head-note" onClick={() => navigate("/insights")} style={{ fontSize: 12, whiteSpace: "nowrap" }}>
          What Friday learned is in Insights
        </button>
      </div>
      <div className="fr-panel" style={{ overflowY: "auto" }}>
        <div className="fr-gutter" style={{ maxWidth: 1080, padding: "12px 40px 120px", display: "flex", flexDirection: "column", gap: 28 }}>
          {tab === "sleep" ? <SleepLog /> : <MealLog />}
        </div>
      </div>
    </>
  )
}
