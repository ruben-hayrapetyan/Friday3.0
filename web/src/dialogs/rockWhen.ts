// What the brief says beside one of today's things: when it's planned next ("14:15–14:45"), or that it isn't planned
// today. A break day is a list, not times (core/vacations.py): nothing, or "done" once ticked off the day's list
// (Friday Notes-3, 26 Nov: "remove the scheduled times to complete tasks ("14:15-14:45" and other instances) bc
// friday doesn't plan when u do them on break").

import { clock } from "@/lib/format"

export function rockWhen(onBreak: boolean, rock: { ticked?: boolean }, next: { start: string; end: string } | undefined): string {
  if (onBreak) return rock.ticked ? "done" : ""
  return next ? `${clock(next.start)}–${clock(next.end)}` : "not today"
}
