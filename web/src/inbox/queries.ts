// What the Inbox reads, and the messages it makes of them (messages.ts): what only you can decide, the day's planned
// time to account for, sleep taps you missed, what came in from mail and calendars, copies, a go-over and repeating
// events to import. One list, and one count everywhere the Inbox is counted (29 Oct: "there are too many
// subcategories of inbox, simplify it and make everything just a message the user needs to deal with").

import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"
import { query, type Schemas } from "@/api/client"
import { useStatus } from "@/hooks/queries"
import { addDays } from "@/lib/time"
import { useShell } from "@/shell/ShellContext"
import { useAsks } from "./asks"
import { type Message, messagesOf, waitingCount } from "./messages"

export const useInbox = () => useQuery({ queryKey: ["inbox"], queryFn: () => query("inbox") })
export const useDuplicates = () => useQuery({ queryKey: ["duplicates"], queryFn: () => query("duplicates") })
export const useToReview = () => useQuery({ queryKey: ["to_review"], queryFn: () => query("to_review") })
export const useReview = (date: string) => useQuery({ queryKey: ["review", date], queryFn: () => query("review", { date }) }).data
export const useDecisions = (): Schemas["Decision"][] => useStatus().data?.decisions ?? []
export const useCalendarRepeats = () => useQuery({ queryKey: ["calendar_repeats"], queryFn: () => query("calendar_repeats") })

const NONE: Schemas["SuggestionOut"][] = []

/** Everything waiting in the Inbox, in order; `answered` are suggestions dealt with here, kept (greyed) after the
 * ones still to answer. */
export function useInboxMessages(answered: Schemas["SuggestionOut"][] = NONE): Message[] {
  const { today } = useShell()
  const yesterday = addDays(today, -1)
  const decisions = useDecisions()
  const before = useReview(yesterday)
  const now = useReview(today)
  const inbox = useInbox().data
  const copies = useDuplicates().data
  const again = useToReview().data
  const repeats = useCalendarRepeats().data
  const asks = useAsks()
  return useMemo(
    () =>
      messagesOf({
        decisions,
        days: [before, now].filter((d) => !!d).map((d) => ({ date: d.date, gaps: d.gaps ?? [], sleep: d.sleep ?? [] })),
        suggestions: inbox?.suggestions ?? [],
        answered,
        copies: copies?.groups ?? [],
        copySources: copies?.sources ?? {},
        again: again?.items ?? [],
        againSources: again?.sources ?? {},
        repeats: repeats ?? [],
        asks,
      }),
    [decisions, before, now, inbox, copies, again, repeats, answered, asks],
  )
}

/** How many things wait in the Inbox: its badge in the sidebar, the window's title and the Plan's tray. */
export function useInboxCount(): number {
  return waitingCount(useInboxMessages())
}
