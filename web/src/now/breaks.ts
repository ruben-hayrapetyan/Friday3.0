// Taking a nap or having a snack from wherever you are (29 Oct: "add functionality for adding naps (same with snacks
// in the meal section)"): the Now bar's More and free time, Search, Insights → Sleep. A nap with something being timed
// asks first whether to stop timing it (NapAsk, 16 Nov); a snack doesn't (you might eat at your desk). Either keeps the plan clear while
// it lasts. Null when its tracking is off, or you're already napping or eating. `again` is another of the meal you
// last had today (5 Nov: "sometimes i have 4 meals (2 dinners)"), so a second dinner isn't tapped as a snack.

import { useCommand } from "@/hooks/useCommand"
import { useMeals, useSleep, useStatus } from "@/hooks/queries"
import { ask } from "./NapAsk"

type Again = { kind: "breakfast" | "lunch" | "dinner"; run: () => Promise<unknown> }

export function useBreaks(): { nap: (() => Promise<unknown>) | null; snack: (() => Promise<unknown>) | null; again: Again | null } {
  const status = useStatus().data
  // what's being timed, in the order you started it
  const timed = [...(status?.alongside ?? []), status?.timer].filter((t) => t?.item_id != null) as { item_id: number; title?: string | null }[]
  const sleep = useSleep().data
  const meals = useMeals().data
  const pause = useCommand("stop", { quiet: true })
  const nap = useCommand("nap_start", { label: (o) => o.result.message ?? "Saved" })
  const snack = useCommand("meal_start", { label: (o) => o.result.message ?? "Saved" })
  return {
    nap: sleep?.on && !sleep.napping ? () => napping(timed, (id) => pause({ id }), () => nap({})) : null,
    snack: meals?.on && !meals.eating ? () => snack({ kind: "snack" }) : null,
    again: meals?.on && !meals.eating && meals.again ? again(meals.again as Again["kind"], (kind) => snack({ kind })) : null,
  }
}

function again(kind: Again["kind"], start: (kind: Again["kind"]) => Promise<unknown>): Again {
  return { kind, run: () => start(kind) }
}

/** A nap: asked first, when something is being timed, whether to stop timing it (every one, when you say so). */
function napping(timed: { item_id: number; title?: string | null }[], stop: (id: number) => Promise<unknown>, nap: () => Promise<unknown>): Promise<unknown> {
  if (!timed.length) return nap()
  return new Promise((done) =>
    ask(timed, async (stopping) => {
      if (stopping === null) return done(undefined) // called off: nothing stops, no nap
      if (stopping) for (const t of timed) await stop(t.item_id)
      done(await nap())
    }),
  )
}
