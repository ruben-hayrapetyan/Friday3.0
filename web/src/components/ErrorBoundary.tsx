// What shows when something on screen breaks (27 Oct: "sometimes i click something and friday just goes black": a
// render error unmounted everything and left the dark background). The page says so and offers to try again, the
// sidebar stays, and the error is reported as main.tsx reports the rest; going to another page tries again by itself.

import { Component, type ReactNode } from "react"
import { command } from "@/api/client"

interface Props {
  children: ReactNode
  resetKey?: string // a new one (another page) clears the error
  whole?: boolean // the whole window, not one page
}

export class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    const detail = `${error.stack ?? ""}\n${info.componentStack ?? ""}`.slice(0, 2000)
    command("report", { where: `render ${location.hash}`, message: String(error.message).slice(0, 300), detail }).catch(() => undefined)
  }

  componentDidUpdate(previous: Props) {
    if (this.state.error && previous.resetKey !== this.props.resetKey) this.setState({ error: null })
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    return (
      <div role="alert" style={{ display: "grid", placeItems: "center", height: this.props.whole ? "100vh" : "100%", padding: 24, gridRow: "1 / -1" }}>
        <div style={{ maxWidth: 460, display: "flex", flexDirection: "column", alignItems: "center", gap: 10, textAlign: "center" }}>
          <span className="fr-h" style={{ fontSize: 22 }}>
            Something on this page broke
          </span>
          <span className="fr-kicker" style={{ textWrap: "pretty" }}>
            Nothing you saved is lost. Friday noted what happened so it can be fixed.
          </span>
          <code style={{ fontSize: 11, color: "var(--color-neutral-500)", wordBreak: "break-word" }}>{error.message}</code>
          <div style={{ display: "flex", gap: 8, paddingTop: 4 }}>
            <button className="btn btn-primary" onClick={() => this.setState({ error: null })}>
              Try again
            </button>
            <button className="btn btn-secondary" onClick={() => location.reload()}>
              Reload
            </button>
            {!this.props.whole && (
              <button className="btn btn-ghost" onClick={() => ((location.hash = "#/"), this.setState({ error: null }))}>
                Back to the plan
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }
}
