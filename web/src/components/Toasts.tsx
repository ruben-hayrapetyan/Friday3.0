import { createContext, type ReactNode, useCallback, useContext, useState } from "react"
import { Icon } from "@/components/fr/controls"

export interface Toast {
  message: string
  tone?: "error"
  action?: { label: string; run: () => void }
}

const ToastContext = createContext<(toast: Toast) => void>(() => {})

export function useToast(): (toast: Toast) => void {
  return useContext(ToastContext)
}

export function Toasts({ children }: { children: ReactNode }) {
  const [shown, setShown] = useState<(Toast & { id: number })[]>([])
  const show = useCallback((toast: Toast) => {
    const id = Math.random()
    setShown((all) => [...all.slice(-2), { ...toast, id }])
    // Errors stay longer: they are the one place a failed command is reported.
    setTimeout(() => setShown((all) => all.filter((t) => t.id !== id)), toast.tone === "error" ? 8000 : 5000)
  }, [])
  const close = (id: number) => setShown((all) => all.filter((t) => t.id !== id))
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div role="status" className="fr-toasts" style={{ position: "fixed", right: 24, top: 68, zIndex: 50, display: "flex", flexDirection: "column", gap: 8, alignItems: "flex-end" }}>
        {shown.map((t) => (
          <div
            key={t.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
              padding: "10px 10px 10px 14px",
              borderRadius: "var(--radius-lg)",
              background: "var(--color-neutral-900)",
              boxShadow: `var(--shadow-md), inset 0 1px 0 color-mix(in srgb, var(--color-text) 8%, transparent)${
                t.tone === "error" ? ", inset 3px 0 0 var(--fr-now)" : ""
              }`,
              maxWidth: 460,
            }}
          >
            {t.tone === "error" && <Icon name="warning-circle" size={18} style={{ color: "var(--fr-due)" }} />}
            <span>{t.message}</span>
            {t.action && (
              <button
                className="btn btn-ghost"
                onClick={() => {
                  t.action?.run()
                  close(t.id)
                }}
              >
                <Icon name="arrow-u-up-left" />
                {t.action.label}
              </button>
            )}
            {!t.action && t.tone === "error" && (
              <button className="btn btn-ghost" onClick={() => close(t.id)} style={{ fontSize: 12 }}>
                Dismiss
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
