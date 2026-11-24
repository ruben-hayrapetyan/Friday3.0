// Gmail with an app password (tests/features.toml: gmail_app; 8 Nov: users "can add their own gmails - right now it
// just errors out for them"). Settings → Integrations' Gmail box, opened as a person would: Connect waits for both
// boxes, a usual password is refused in words that say where to make an app password, and nothing is kept. Gmail
// itself isn't reached from a test, so a right password isn't sent; the headless test covers what's kept and removed.

const limit = (ms, run) => async (t) => {
  let timer
  const late = new Promise((_, fail) => (timer = setTimeout(() => fail(new Error(`the test took over ${ms / 1000}s`)), ms)))
  try {
    return await Promise.race([run(t), late])
  } finally {
    clearTimeout(timer)
  }
}

const dialog = '[role=dialog][aria-label="Gmail"]'
const connect = `[...document.querySelectorAll('${dialog} form button[type=submit]')].find((b) => b.textContent.trim() === "Connect")`

async function openGmail({ open, until, has }) {
  await open("/settings/integrations")
  await until(`(() => { const b = document.querySelector('[data-integration="gmail"]'); if (!b) return false; b.click(); return true })()`, 15_000, "the Gmail box")
  await until(`!!document.querySelector('${dialog}')`, 10_000, "the Gmail panel")
  await has("Make an app password at", dialog)
}

export default [
  {
    name: "the Gmail box opens its panel: how to make an app password, the two boxes, and Connect waiting for both",
    run: limit(90_000, async (t) => {
      const { until, type, text, q, expect } = t
      await openGmail(t)
      const said = await text(dialog)
      expect(said.includes("myaccount.google.com/apppasswords"), `no link to make an app password: ${said}`)
      expect(await until(`${connect}?.disabled === true`, 5_000, "Connect disabled while empty"), "Connect isn't disabled while empty")
      await type("Gmail address", "pat.e2e@gmail.com")
      expect(await until(`${connect}?.disabled === true`, 5_000, "Connect disabled without a password"), "Connect is on without a password")
      await type("App password", "abcd")
      await until(`${connect}?.disabled === false`, 5_000, "Connect on once both are typed")
      expect((await q("gmail_app_accounts")).length === 0, "an account is kept before Connect")
    }),
  },
  {
    name: "a usual password is refused with where to make an app password, and nothing is kept",
    run: limit(90_000, async (t) => {
      const { until, type, has, q, expect } = t
      const before = (await q("settings")).gmail
      await openGmail(t)
      await type("Gmail address", "pat.e2e@gmail.com")
      await type("App password", "hunter2hunter2")
      await until(`(() => { const b = ${connect}; if (!b || b.disabled) return false; b.click(); return true })()`, 5_000, "Connect")
      await has("16 letters")
      await has("myaccount.google.com/apppasswords")
      expect((await q("gmail_app_accounts")).length === 0, "the server kept an account it refused")
      expect(JSON.stringify((await q("settings")).gmail) === JSON.stringify(before), "a refused password changed the Gmail settings")
      // what you typed stays, to fix
      const kept = await until(`document.querySelector('${dialog} input[aria-label="Gmail address"]')?.value`, 5_000, "the address still typed")
      expect(kept === "pat.e2e@gmail.com", `the address box was emptied: "${kept}"`)
    }),
  },
  {
    name: "Escape closes the panel and gives the focus back to the Gmail box",
    run: limit(90_000, async (t) => {
      const { until, press, q, expect } = t
      await openGmail(t)
      await press("Escape")
      await until(`!document.querySelector('${dialog}')`, 5_000, "the panel closed")
      await until(`document.activeElement?.getAttribute("data-integration") === "gmail"`, 5_000, "the focus back on the Gmail box")
      expect((await q("gmail_app_accounts")).length === 0, "an account was kept")
    }),
  },
]
