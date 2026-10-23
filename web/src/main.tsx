import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "@fontsource/inter/400.css"
import "@fontsource/inter/500.css"
import "@fontsource/inter/600.css"
import "@fontsource/inter/700.css"
import "@fontsource/inter/800.css"
import "@fontsource/archivo/700.css"
import "@fontsource/archivo/900.css"
import "@fontsource/instrument-sans/700.css"
import "@phosphor-icons/web/regular"
import "@phosphor-icons/web/fill"
import "./index.css"
import "./theme/nocturne.css"
import "./theme/friday.css"
import App from "./App"
import { command } from "./api/client"

// What breaks on screen goes to the daemon's log, next to what the server did (at most a handful a session).
let reported = 0
function report(where: string, message: string, detail?: string): void {
  if (reported++ > 12) return
  command("report", { where, message: message.slice(0, 300), detail: detail?.slice(0, 2000) }).catch(() => undefined)
}
window.addEventListener("error", (e) => report(`window ${location.hash}`, e.message, e.error?.stack))
window.addEventListener("unhandledrejection", (e) => {
  const reason = e.reason as { message?: string; stack?: string } | undefined
  report(`promise ${location.hash}`, String(reason?.message ?? e.reason), reason?.stack)
})

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
