// The layout for the window's width (any size, from a phone to a wide screen): the sidebar in full, as a rail of
// icons, or behind a menu button; the to-do drawer beside the calendar or over it; a week or a day; the title row's
// controls with words or as icons.

import { useEffect, useState } from "react"

export type Mode = "wide" | "rail" | "narrow"

export interface Layout {
  width: number
  mode: Mode
  side: number // the sidebar's width: in full, a rail, or none (it slides over the page)
  main: number // what's left for the page
  labels: boolean // the title row's buttons say what they do; otherwise icons with tooltips
  tight: boolean // the title row keeps only the essentials; the rest is in menus
  weekFits: boolean // seven columns are wide enough to read; otherwise the week shows as its day
  dayAside: boolean // the day view's panel of the day's numbers beside the grid
}

export const SIDEBAR = 248
export const RAIL = 60
export const WEEK_MIN = 780 // the narrowest a week's seven columns can be read

export function layoutFor(width: number): Layout {
  const mode: Mode = width >= 1180 ? "wide" : width >= 760 ? "rail" : "narrow"
  const side = mode === "wide" ? SIDEBAR : mode === "rail" ? RAIL : 0
  const main = Math.max(0, width - side)
  return { width, mode, side, main, labels: main >= 1080, tight: main < 620, weekFits: main >= WEEK_MIN, dayAside: main >= 980 }
}

/** Whether the drawer slides over the calendar instead of taking room beside it: when what's left couldn't show a
 * readable week. */
export function drawerOver(layout: Layout, drawerWidth: number): boolean {
  return layout.main - drawerWidth < WEEK_MIN
}

export function useWindowWidth(): number {
  const [width, setWidth] = useState(() => (typeof window === "undefined" ? 1440 : window.innerWidth))
  useEffect(() => {
    let frame = 0
    const resize = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => setWidth(window.innerWidth))
    }
    window.addEventListener("resize", resize)
    return () => (cancelAnimationFrame(frame), window.removeEventListener("resize", resize))
  }, [])
  return width
}
