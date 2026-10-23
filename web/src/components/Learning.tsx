// What Friday learned (DESIGN §21.2, §21.8): the weekly digest with Approve / Reject for suggested weights, and
// the learning settings (modes per module, the multipliers in use, reset).

import { useQuery } from "@tanstack/react-query"
import { query } from "@/api/client"
import { Button } from "@/components/ui/button"
import { useCommand } from "@/hooks/useCommand"
import { useSettings } from "@/hooks/queries"

const useLearning = () => useQuery({ queryKey: ["learning"], queryFn: () => query("learning") })

function words(rule: string): string {
  return rule.replace(/^learned:/, "").replaceAll("_", " ").replaceAll(":", " ")
}

export function LearnedDigest() {
  const learned = useLearning().data
  const apply = useCommand("learn_apply", { label: (o) => o.result.message ?? "Applied" })
  const reject = useCommand("learn_reject", { label: (o) => o.result.message ?? "Kept" })
  const useModule = useCommand("learn_module", { label: (o) => o.result.message ?? "Saved" })
  if (!learned) return null
  const durations = learned.durations as { in_use: boolean; better: boolean | null; error: number; error_before: number } | null
  const energy = learned.energy as { in_use: boolean; worst: { day: string; time: string }[] } | null
  if (learned.mode === "off") return <p className="text-muted-foreground">Learning is off (Settings).</p>
  return (
    <div className="space-y-2">
      <p className="text-muted-foreground">
        From {learned.comparisons} answers and {learned.drags} moves you made.
      </p>
      {durations?.better && !durations.in_use && (
        <Offer onUse={() => useModule({ module: "durations", use: true })}>
          Learned lengths are typically {Math.round(100 * durations.error)}% off, against{" "}
          {Math.round(100 * durations.error_before)}% now.
        </Offer>
      )}
      {energy && energy.worst.length > 0 && !energy.in_use && (
        <Offer onUse={() => useModule({ module: "energy", use: true })}>
          Planned work often slips around {energy.worst.slice(0, 3).map((w) => `${w.day} ${w.time}`).join(", ")}: plan
          less deep work there.
        </Offer>
      )}
      {learned.suggested ? (
        <div className="space-y-2 rounded-lg border p-3">
          <p>Friday suggests:</p>
          <ul className="list-disc pl-5">
            {learned.digest.filter((line) => !line.endsWith("?")).map((line) => (
              <li key={line}>{line}</li>
            ))}
            {!learned.digest.length && <li>Small changes only.</li>}
          </ul>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => apply({ version: learned.suggested?.version as number })}>
              Approve
            </Button>
            <Button size="sm" variant="outline" onClick={() => reject({ version: learned.suggested?.version as number })}>
              Reject
            </Button>
          </div>
        </div>
      ) : (
        <p>Nothing new to approve.</p>
      )}
    </div>
  )
}

function Offer({ children, onUse }: { children: React.ReactNode; onUse: () => void }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border p-3">
      <p className="flex-1">{children}</p>
      <Button size="sm" onClick={onUse}>
        Use
      </Button>
    </div>
  )
}

interface Learn {
  weights: "off" | "suggest" | "auto"
  state_inference: "off" | "on"
  proposals: "off" | "ask"
  durations: "off" | "suggest" | "auto"
  energy: "off" | "suggest" | "auto"
  [key: string]: unknown
}

export function LearningSettings() {
  const learned = useLearning().data
  const learn = useSettings().data?.learn as Learn | undefined
  const set = useCommand("settings_set", { label: () => "Learning saved" })
  const reset = useCommand("learn_reset", { label: (o) => o.result.message ?? "Reset" })
  if (!learn || !learned) return null
  const change = (key: keyof Learn, value: string) => set({ key: "learn", value: { ...learn, [key]: value } })
  const select = "h-8 rounded-md border bg-transparent px-2 text-sm"
  const multipliers = Object.entries(learned.multipliers).filter(([, v]) => Math.abs(v - 1) > 0.05)
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-[12rem_1fr] items-center gap-2">
        <span>Learned weights</span>
        <select className={select} value={learn.weights} onChange={(e) => change("weights", e.target.value)}>
          <option value="off">Off</option>
          <option value="suggest">Suggest, I approve</option>
          <option value="auto">Apply by itself (small steps)</option>
        </select>
        <span>Learned lengths</span>
        <select className={select} value={learn.durations} onChange={(e) => change("durations", e.target.value)}>
          <option value="off">Off</option>
          <option value="suggest">Suggest, I approve</option>
          <option value="auto">Use when better</option>
        </select>
        <span>Good and bad hours</span>
        <select className={select} value={learn.energy} onChange={(e) => change("energy", e.target.value)}>
          <option value="off">Off</option>
          <option value="suggest">Suggest, I approve</option>
          <option value="auto">Use</option>
        </select>
        <span>Missing rules</span>
        <select className={select} value={learn.proposals} onChange={(e) => change("proposals", e.target.value)}>
          <option value="off">Don't propose</option>
          <option value="ask">Propose, I decide</option>
        </select>
        <span>Read my state (experimental)</span>
        <select className={select} value={learn.state_inference} onChange={(e) => change("state_inference", e.target.value)}>
          <option value="off">Off</option>
          <option value="on">On, with a daily check-in</option>
        </select>
      </div>
      <p className="text-muted-foreground">
        {learned.comparisons} answers, {learned.drags} moves · answer noise {learned.answer_noise}
        {learned.state && ` · state ${learned.state.on ? "in use" : "not proven yet"}`}
      </p>
      {multipliers.length > 0 && (
        <ul className="text-xs">
          {multipliers.map(([rule, v]) => (
            <li key={rule}>
              {words(rule)} ×{v.toFixed(2)}
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-2">
        {(["weights", "durations", "energy", "state", "proposals", "all"] as const).map((module) => (
          <Button key={module} size="xs" variant="outline" onClick={() => reset({ module })}>
            Reset {module === "all" ? "everything" : module}
          </Button>
        ))}
      </div>
    </div>
  )
}
