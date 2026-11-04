// The To-do drawer's Due view (3 Nov: "in one quick look, i want to gague what i really need to get done today, even
// if friday says that it is going to be late"): what's due in the next seven days, day by day, under what is already
// overdue and still matters. Overdue work that stopped mattering at its due (a soft deadline, a reading that fades,
// work that's pointless once late) is left off: it's on the To-do page.

import type { Item } from "@/api/client"
import { addDays, fromMin, toMin } from "./time"

export type Late = { item_id: number; hours: number; planned?: boolean }
export type DueRow = { item: Item; late?: Late }
export type DueDay = { day: string; rows: DueRow[] }
export type DueSoon = { overdue: DueRow[]; days: DueDay[] }

export const DAYS = 7

/** Overdue work that still has to be done: a hard deadline that doesn't fade or stop mattering once passed. */
export function stillMatters(item: Item): boolean {
  return item.firmness === "hard" && !item.pointless_late && !item.fading_late
}

/** Where a soft repeat's window ends (lunch by 2:30, laundry's week) isn't a deadline, as in the calendar's dues. */
export function isDeadline(item: Item): boolean {
  return item.series_id == null || item.firmness === "hard"
}

/** `now` is local minutes (useClock); `late` is the plan's late and slipping work, so a row can say Friday has it late. */
export function dueSoon(items: Item[], now: number, late: Late[] = []): DueSoon {
  const today = fromMin(now).slice(0, 10)
  const end = `${addDays(today, DAYS)}T00:00`
  const lateOf = new Map(late.map((l) => [l.item_id, l]))
  const row = (item: Item): DueRow => ({ item, late: lateOf.get(item.id) })
  const open = items.filter((i) => i.status === "todo" && i.due && isDeadline(i)).sort(byDue)
  const overdue = open.filter((i) => toMin(i.due!) < now && stillMatters(i)).map(row)
  const days: DueDay[] = []
  for (const item of open.filter((i) => toMin(i.due!) >= now && i.due! < end)) {
    const day = item.due!.slice(0, 10)
    if (days.at(-1)?.day !== day) days.push({ day, rows: [] })
    days.at(-1)!.rows.push(row(item))
  }
  return { overdue, days }
}

/** A list's groups, as the to-do drawer shows them: Overdue (red) first, then a group per day named as you'd say it. */
export type DueGroup = { name: string; items: Item[]; red?: boolean; late?: Map<number, Late>; overdue?: boolean }

export function dueGroups(items: Item[], now: number, late: Late[] = []): DueGroup[] {
  const { overdue, days } = dueSoon(items, now, late)
  const lateOf = new Map(late.map((l) => [l.item_id, l]))
  const today = fromMin(now).slice(0, 10)
  const first: DueGroup[] = overdue.length ? [{ name: "Overdue", items: overdue.map((r) => r.item), red: true, late: lateOf, overdue: true }] : []
  return [...first, ...days.map((d) => ({ name: dayLabel(d.day, today), items: d.rows.map((r) => r.item), late: lateOf }))]
}

/** "Today", "Tomorrow", else the weekday and date: "Thu 6". */
export function dayLabel(day: string, today: string): string {
  if (day === today) return "Today"
  if (day === addDays(today, 1)) return "Tomorrow"
  const name = new Date(toMin(day) * 60000).toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" })
  return `${name} ${Number(day.slice(8, 10))}`
}

/** How long past its due: "3h overdue", "2 days overdue". */
export function overdueBy(due: string, now: number): string {
  const minutes = now - toMin(due)
  if (minutes < 60) return "just overdue"
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h overdue`
  const days = Math.floor(minutes / 1440)
  return `${days} day${days === 1 ? "" : "s"} overdue`
}

/** What a row says of Friday's plan for it, when the plan has it late: you decide whether to find the time. */
export function lateWarning(late: Late | undefined): string | null {
  if (!late) return null
  return late.planned === false || !late.hours ? "Friday has no time for it" : `Friday has it ${hoursText(late.hours)} late`
}

function hoursText(hours: number): string {
  const minutes = Math.round(hours * 60)
  if (minutes < 60) return `${minutes}m`
  if (minutes >= 600) return `${Math.round(minutes / 60)}h` // past ten hours, minutes are noise
  const h = Math.floor(minutes / 60)
  return minutes % 60 ? `${h}h ${minutes % 60}m` : `${h}h`
}

function byDue(a: Item, b: Item): number {
  return a.due!.localeCompare(b.due!) || a.id - b.id
}
