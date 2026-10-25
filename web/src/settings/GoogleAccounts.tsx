// The Google accounts Friday reads (your own and your school's, say), on the Google Calendar card: each with the
// calendars it reads and whether Friday reads its mail, a button to sign that one in again when Google asks, and
// Remove, which asks first. Setup's last step lists them in a line each.

import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { command, type Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useSettings } from "@/hooks/queries"
import { accountName, ConnectGoogle, type GoogleAccount, KEY, refreshAfterGoogle, said, wantsSignIn } from "./GoogleConnect"

type GoogleCalendar = Schemas["GoogleCalendarOut"]

/** A calendar read through this account (one listed before Friday kept several has none, as the one from before). */
export const inAccount = (c: GoogleCalendar, email: string) => (c.account ?? "") === email

/** Why an account needs signing in again, if it does: Google turned it away, or it signed in before "Edit here". */
export function signInAgain(account: GoogleAccount, calendars: GoogleCalendar[]): string | null {
  const its = calendars.filter((c) => inAccount(c, account.email))
  if (its.some((c) => c.on && wantsSignIn(c.error)) || (account.gmail && wantsSignIn(account.mail_error))) return "Google stopped letting Friday into this account (the sign-in expired or was removed). Connect again to carry on."
  if (!account.events && its.some((c) => c.on && c.editable)) return "Saving your changes back to its calendars needs Google's OK once more."
  return null
}

/** The accounts; the demo's stand-in Google can't be removed or signed in again. */
export function AccountList({ accounts, calendars, demo = false }: { accounts: GoogleAccount[]; calendars: GoogleCalendar[]; demo?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {accounts.map((a) => (
        <Account key={a.email} account={a} calendars={calendars.filter((c) => inAccount(c, a.email))} why={demo ? null : signInAgain(a, calendars)} removable={!demo} />
      ))}
    </div>
  )
}

function Account({ account, calendars, why, removable }: { account: GoogleAccount; calendars: GoogleCalendar[]; why: string | null; removable: boolean }) {
  const mail = ((useSettings().data as Record<string, unknown> | undefined)?.gmail as { enabled: boolean } | undefined)?.enabled
  const reading = calendars.filter((c) => c.on).map((c) => c.name)
  const what = !calendars.length ? "Its calendars list below after the first sync." : !reading.length ? "No calendars read yet: switch them on below." : reading.length <= 3 ? `Reads ${listed(reading)}.` : `Reads ${reading.length} of its ${calendars.length} calendars.`
  return (
    <div className="fr-row" style={{ display: "grid", gridTemplateColumns: "28px minmax(0,1fr) auto", gap: 12, alignItems: "start", padding: "10px 0" }}>
      <span aria-hidden style={{ width: 28, height: 28, borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 500, background: "color-mix(in srgb, var(--color-accent) 18%, transparent)", color: "var(--color-accent-200)" }}>
        {account.email ? account.email[0].toUpperCase() : <Icon name="google-logo" size={14} />}
      </span>
      <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span style={{ fontWeight: 500, overflowWrap: "anywhere" }}>{accountName(account.email)}</span>
        <span className="fr-kicker" style={{ textWrap: "pretty" }}>
          {what}
          {mail && (account.gmail ? " Its mail is read." : " Its mail isn't allowed yet (Allow Gmail, under Gmail).")}
        </span>
        {why && (
          <span style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: 4 }}>
            <span style={{ fontSize: 12, color: "var(--fr-warn)", textWrap: "pretty" }}>{why}</span>
            <ConnectGoogle account={account.email} again small />
          </span>
        )}
      </span>
      {removable ? <Remove email={account.email} /> : <span />}
    </div>
  )
}

/** "A", "A and B", "A, B and C". */
const listed = (names: string[]) => (names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`)

/** Remove, then "Remove this account?" with what it means, and Remove or Keep. */
function Remove({ email }: { email: string }) {
  const client = useQueryClient()
  const [asking, setAsking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const remove = async () => {
    setBusy(true)
    setProblem(null)
    try {
      client.setQueryData(KEY, (await command("google_remove", { account: email })).result)
      refreshAfterGoogle(client)
    } catch (error) {
      setProblem(said(error))
      setBusy(false)
    }
  }
  if (!asking)
    return (
      <button className="btn btn-ghost" onClick={() => setAsking(true)} aria-label={`Remove ${accountName(email)}`} style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
        Remove
      </button>
    )
  return ( // a row of its own under the account, so the question has room
    <span style={{ gridColumn: "1 / -1", display: "flex", flexWrap: "wrap", alignItems: "center", gap: "4px 10px", paddingLeft: 40 }}>
      <span style={{ fontSize: 12, color: "var(--color-neutral-300)", textWrap: "pretty", flex: "1 1 240px" }}>
        Remove {accountName(email)}? Friday stops reading its calendars and mail. What it already brought in stays, and connecting it again picks up where it left off.
      </span>
      <span style={{ display: "flex", gap: 6 }}>
        <button className="btn btn-ghost" onClick={remove} disabled={busy} style={{ fontSize: 12, color: "var(--fr-due)" }}>
          {busy ? "Removing…" : "Remove"}
        </button>
        <button className="btn btn-ghost" onClick={() => setAsking(false)} disabled={busy} style={{ fontSize: 12 }}>
          Keep
        </button>
      </span>
      {problem && <span style={{ fontSize: 12, color: "var(--fr-due)", flexBasis: "100%" }}>{problem}</span>}
    </span>
  )
}

/** Setup's line for each connected account: a tick and its address. */
export function ConnectedAccounts({ accounts }: { accounts: GoogleAccount[] }) {
  if (!accounts.length) return null
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {accounts.map((a) => (
        <span key={a.email} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, color: "var(--color-accent-300)" }}>
          <Icon name="check-circle" size={15} fill />
          Connected: {accountName(a.email)}
        </span>
      ))}
    </div>
  )
}
