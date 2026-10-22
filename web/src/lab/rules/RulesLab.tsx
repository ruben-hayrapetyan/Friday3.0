// The rules lab (/lab/rules): prototypes of other ways to understand and steer the planner's rules, all on your real
// plan. They preview with warm solves that save nothing; only a button that names its command changes anything.

import { Link, useParams } from "react-router"
import { Icon } from "@/components/fr/controls"
import { DialsPage } from "./DialsPage"
import { ImpactPage } from "./ImpactPage"
import { RankingPage } from "./RankingPage"
import { SentencesPage } from "./SentencesPage"
import { TeachPage } from "./TeachPage"
import { WeekPage } from "./WeekPage"
import { Page } from "./shared"

const DIRECTIONS = [
  {
    slug: "impact",
    title: "Impact",
    icon: "chart-bar-horizontal",
    page: <ImpactPage />,
    idea: "Each rule judged by what it does to your plan: how much it is being bent now, on which blocks, and (one solve per rule, on click) what moves if it were gone, said as “2 h less late-night work”.",
    tradeoff: "Answers “what does this rule actually do?” directly, but it is a report, not a control, and each answer costs a solve (1–5 s). On a light week most rules do nothing visible, which is honest but can look empty.",
  },
  {
    slug: "dials",
    title: "Dials",
    icon: "faders",
    page: <DialsPage />,
    idea: "Five plain controls (protect sleep, when to start, sitting length, free evenings and weekends, spread or batch), each a few stops that write named weights and params, with the week replanned beside them.",
    tradeoff: "The quickest to understand and use, and closest to how people talk. It hides the rules it doesn’t cover and can only reach the combinations its stops define; the mapping is a design decision someone has to keep right.",
  },
  {
    slug: "sentences",
    title: "Sentences",
    icon: "text-aa",
    page: <SentencesPage />,
    idea: "Every rule, built-ins included, as a sentence whose values you edit in place (“Keep 2 h free between 18:00 and 23:00 on weekdays”), split into walls that never bend and preferences with a strength.",
    tradeoff: "Full control and full honesty with no new concepts: the page is the rules. It is still twenty sentences, and strength remains a number in disguise; it needs a template per rule type.",
  },
  {
    slug: "ranking",
    title: "Priorities",
    icon: "list-numbers",
    page: <RankingPage />,
    idea: "Drag what matters into order, with a line between what Friday protects and what it merely prefers. The line is the engine’s real stage boundary; moving a place up doubles a weight.",
    tradeoff: "Matches how the engine actually decides (stages are strict) and gives one mental model. Weights between unlike rules (an hour of sleep against a free evening) are not really comparable, so “twice as much” is approximate.",
  },
  {
    slug: "week",
    title: "Week with toggles",
    icon: "calendar-dots",
    page: <WeekPage />,
    idea: "Your week now beside the week with some rules switched off or turned up or down. You learn a rule by watching blocks move.",
    tradeoff: "The most concrete; no reading needed. It explains only through examples in the current week, and big weeks move a lot at once, which can blur cause and effect.",
  },
  {
    slug: "teach",
    title: "Teach by example",
    icon: "hand-pointing",
    page: <TeachPage />,
    idea: "Pick a block, click where you would rather have it: Friday names the rules in the way and how much each objects (or the wall), and offers the one change that would let it move.",
    tradeoff: "Rules are met only when they matter to you, in your own disagreement. It is reactive (you only learn rules you bump into) and a one-off move is better handled by a pin than by changing a rule.",
  },
]

export function RulesLab() {
  const { slug } = useParams()
  const found = DIRECTIONS.find((d) => d.slug === slug)
  if (found) return found.page
  return (
    <Page title="Directions" idea="Six prototypes of a different Rules page, each on your real plan. They preview changes with a solve that saves nothing; a button that saves says which command it runs. Pick one, try it, and compare.">
      <div style={{ display: "flex", flexDirection: "column" }}>
        {DIRECTIONS.map((d) => (
          <Link key={d.slug} to={`/lab/rules/${d.slug}`} className="fr-row fr-hover" style={{ display: "grid", gridTemplateColumns: "28px minmax(0,1fr)", gap: "4px 12px", padding: "16px 8px", color: "inherit", textDecoration: "none" }}>
            <Icon name={d.icon} size={20} style={{ color: "var(--color-accent-300)" }} />
            <span className="fr-h" style={{ fontSize: 18 }}>
              {d.title}
            </span>
            <span />
            <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>{d.idea}</span>
            <span />
            <span style={{ color: "var(--color-neutral-500)", fontSize: 13, textWrap: "pretty" }}>{d.tradeoff}</span>
          </Link>
        ))}
      </div>
    </Page>
  )
}
