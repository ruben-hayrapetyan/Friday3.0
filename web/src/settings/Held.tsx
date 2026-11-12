// A slider and a number box that hold what you're setting until you let go, then save it once (audit, 12 Nov: a drag
// of the daily limit sent a save, a replan and a toast for every step it passed, and the thumb jumped back between
// them; a number box saved 0 the moment it was emptied, and "8" typed over "10" became "108"). What's saved shows
// again once you've let go, as Undo or another window changes it.

import { type InputHTMLAttributes, useRef, useState } from "react"

type Box = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "defaultValue" | "onChange" | "type">

/** A range input showing where you drag it, saved when you let go (pointer, key or leaving it), if it changed. */
export function HeldRange({ value, onSave, ...rest }: Box & { value: number; onSave: (v: number) => void }) {
  const [held, setHeld] = useState<number | null>(null)
  const done = () => {
    if (held !== null && held !== value) onSave(held)
    setHeld(null)
  }
  return <input {...rest} type="range" value={held ?? value} onChange={(e) => setHeld(Number(e.target.value))} onPointerUp={done} onKeyUp={done} onBlur={done} />
}

/** The number a box holds, or null when it can't be saved: empty, not a number, or outside `min`–`max`. */
export function heldNumber(text: string, min?: number, max?: number): number | null {
  if (!text.trim()) return null
  const n = Number(text)
  if (!Number.isFinite(n) || (min !== undefined && n < min) || (max !== undefined && n > max)) return null
  return n
}

/** A number box: typed freely, saved on Enter or leaving it when it reads as a number in range, else back as it was. */
export function HeldNumber({ value, onSave, min, max, ...rest }: Box & { value: number; onSave: (v: number) => void; min?: number; max?: number }) {
  const [text, setText] = useState<string | null>(null)
  const done = () => {
    const n = text === null ? null : heldNumber(text, min, max)
    if (n !== null && n !== value) onSave(n)
    setText(null)
  }
  return (
    <input
      {...rest}
      type="number"
      min={min}
      max={max}
      value={text ?? String(value)}
      aria-invalid={text !== null && heldNumber(text, min, max) === null}
      onChange={(e) => setText(e.target.value)}
      onBlur={done}
      onKeyDown={(e) => e.key === "Enter" && done()}
    />
  )
}

/** One at a time: `run` does nothing while the last is on its way, and `busy` says so (audit, 12 Nov: Connect pressed
 * twice during a slow check connected the account twice). */
export function useOnce(): [boolean, (act: () => Promise<unknown>) => Promise<void>] {
  const sending = useRef(false)
  const [busy, setBusy] = useState(false)
  const run = async (act: () => Promise<unknown>) => {
    if (sending.current) return
    sending.current = true
    setBusy(true)
    try {
      await act()
    } finally {
      sending.current = false
      setBusy(false)
    }
  }
  return [busy, run]
}
