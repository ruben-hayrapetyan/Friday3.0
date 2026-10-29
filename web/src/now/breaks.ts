// Taking a nap or having a snack from wherever you are (29 Oct: "add functionality for adding naps (same with snacks
// in the meal section)"): the Now bar's More and free time, Search, Sleep & meals. A nap pauses the timer first, since
// you aren't working while you sleep; a snack doesn't (you might eat at your desk). Either keeps the plan clear while
// it lasts. Null when its tracking is off, or you're already napping or eating.

import { useCommand } from "@/hooks/useCommand"
import { useMeals, useSleep, useStatus } from "@/hooks/queries"

export function useBreaks(): { nap: (() => Promise<unknown>) | null; snack: (() => Promise<unknown>) | null } {
  const timer = useStatus().data?.timer ?? null
  const sleep = useSleep().data
  const meals = useMeals().data
  const pause = useCommand("stop", { quiet: true })
  const nap = useCommand("nap_start", { label: (o) => o.result.message ?? "Saved" })
  const snack = useCommand("meal_start", { label: (o) => o.result.message ?? "Saved" })
  return {
    nap: sleep?.on && !sleep.napping ? async () => (timer && (await pause({})), nap({})) : null,
    snack: meals?.on && !meals.eating ? () => snack({ kind: "snack" }) : null,
  }
}
