// Sleep & meals: what you tell Friday about your nights and your meals, each with its own switch (off until you turn
// it on), and what Friday makes of them. The Now bar asks at the right moments; each tab shows what's learned first
// (usual times, the last two weeks, what to change with one click), then a tap you missed, one to log after the fact,
// and the last two weeks to put right.

import { useSearchParams } from "react-router"
import { Seg } from "@/components/fr/controls"
import { MealsSection } from "@/insights/Meals"
import { SleepSection } from "@/insights/Sleep"
import { MealLog } from "./MealLog"
import { SleepLog } from "./SleepLog"

const TABS = [
  { value: "sleep", label: "Sleep" },
  { value: "meals", label: "Meals" },
] as const

export function BodyPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get("tab") === "meals" ? "meals" : "sleep"
  return (
    <>
      <div className="fr-page-head">
        <span className="fr-h fr-title">Sleep &amp; meals</span>
        <Seg options={TABS} value={tab} onPick={(t) => setParams({ tab: t }, { replace: true })} />
      </div>
      <div className="fr-panel" style={{ overflowY: "auto" }}>
        <div className="fr-gutter" data-tour="tracking" style={{ maxWidth: 1080, padding: "12px 40px 120px", display: "flex", flexDirection: "column", gap: 28 }}>
          {tab === "sleep" ? (
            <>
              <SleepSection here />
              <SleepLog />
            </>
          ) : (
            <>
              <MealsSection here />
              <MealLog />
            </>
          )}
        </div>
      </div>
    </>
  )
}
