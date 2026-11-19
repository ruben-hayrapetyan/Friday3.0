// When a to-do is next planned, said everywhere a row says it (To-do, the drawer, search, a project's step): on a break
// day the day's list, since a break day has no times (breaks/).

import { useQuery } from "@tanstack/react-query"
import { query } from "@/api/client"
import { when } from "@/lib/format"
import { plannedWords } from "./words"

export function usePlannedWhen(): (start: string, today: string) => string {
  const breaks = useQuery({ queryKey: ["vacations"], queryFn: () => query("vacations") }).data?.vacations ?? []
  return (start, today) => plannedWords(start, today, breaks, (at) => when(at, today))
}
