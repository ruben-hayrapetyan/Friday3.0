// Room at the foot of a page for the Now dock floating over it (15 Nov: with the sleep and the meal rows both up,
// the dock stood taller than the Inbox's 80px of room, and Accept and Decline sat under it where no scroll could
// bring them out). The dock says how much of the window's foot it covers in --fr-dock, as it grows and shrinks; a
// page's scrolling column ends that far down, and never less than its own room.

export const DOCK_VAR = "--fr-dock"

/** A scrolling column's bottom padding: `least` px, or more while the dock is taller than that. */
export function dockRoom(least: number): string {
  return `max(${least}px, calc(var(${DOCK_VAR}, 0px) + 24px))`
}

/** What the dock covers of the window's foot, from its box: its top to the window's bottom (0 when it's gone). */
export function covered(top: number | null, windowHeight: number): number {
  return top === null ? 0 : Math.max(0, Math.round(windowHeight - top))
}
