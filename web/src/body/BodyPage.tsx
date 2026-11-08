// Sleep and Meals, now tabs of Insights (8 Nov: "integrate the sleep and meals with the current insights page to make a
// much more cohesive insights page"): what you tell Friday about your nights and your meals, each with its own switch
// (off until you turn it on), and what Friday makes of them. Each tab shows what's learned first (usual times, the
// last two weeks, what to change with one click), then a tap you missed, one to log after the fact, and the last two
// weeks to put right. The old address, /body, goes to the same tab.

import { Navigate, useSearchParams } from "react-router"
import { MealsSection } from "@/insights/Meals"
import { SleepSection } from "@/insights/Sleep"
import { MealLog } from "./MealLog"
import { SleepLog } from "./SleepLog"

/** Sleep or Meals, as Insights shows it. */
export function BodyTab({ tab }: { tab: "sleep" | "meals" }) {
  return (
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
  )
}

/** Where Sleep & meals was: its tab in Insights. */
export function BodyPage() {
  const [params] = useSearchParams()
  return <Navigate to={insightsTab(params.get("tab") === "meals" ? "meals" : "sleep")} replace />
}

/** The address of one of Insights' tabs. */
export function insightsTab(tab: "trends" | "sleep" | "meals" | "week"): string {
  return `/insights?tab=${tab}`
}
