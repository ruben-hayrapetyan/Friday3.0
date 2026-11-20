// A calendar as Friday's dropdowns list it: the color its events wear, and its name.

import { pigment, UNMARKED } from "@/lib/pigments"

/** A calendar's color dot (its events' paint, else the Unmarked slate) and name; `hollow` for no calendar at all
 * ("Only Friday"). */
export function CalendarName({ name, color, light, hollow }: { name: string; color?: string | null; light: boolean; hollow?: boolean }) {
  return (
    <span style={{ display: "inline-flex", gap: 8, alignItems: "center", minWidth: 0 }}>
      <span style={{ width: 9, height: 9, flex: "none", borderRadius: "50%", background: hollow ? "transparent" : (pigment(color, light) ?? UNMARKED), boxShadow: hollow ? "inset 0 0 0 1px var(--color-neutral-400)" : undefined }} />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{name}</span>
    </span>
  )
}
