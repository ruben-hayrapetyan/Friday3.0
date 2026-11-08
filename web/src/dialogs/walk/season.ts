// The season the walk is drawn in (8 Nov: "make sure the intro scene matches the weather outside so make it winter
// during the winter months (in the northern hemisphere) fall during fall months, summer during summer months"): from
// today's month, December to February winter, March to May spring, June to August summer, September to November fall.
// `?season=winter` in the page's address draws another, to look at each.

export type Season = "winter" | "spring" | "summer" | "fall"
export const SEASONS: readonly Season[] = ["winter", "spring", "summer", "fall"]

export function seasonOf(day: Date): Season {
  const month = day.getMonth()
  if (month === 11 || month <= 1) return "winter"
  if (month <= 4) return "spring"
  if (month <= 7) return "summer"
  return "fall"
}

/** Today's season, or the one the address asks for. */
export function chosenSeason(search: string, today: Date): Season {
  const asked = new URLSearchParams(search).get("season")
  return (SEASONS as readonly string[]).includes(asked ?? "") ? (asked as Season) : seasonOf(today)
}

export const SEASON: Season = chosenSeason(typeof location === "undefined" ? "" : location.search, new Date())

/** Sunrise and sunset (hours) and the sun's height at noon (radians), as a college town in the north has them. */
export const DAYLIGHT: Record<Season, { rise: number; set: number; noon: number }> = {
  winter: { rise: 7.25, set: 16.75, noon: 0.47 }, // 7:15am to 4:45pm, about 27° at noon
  spring: { rise: 6.5, set: 19.5, noon: 0.95 },
  summer: { rise: 5.6, set: 20.6, noon: 1.2 }, // the long days, the sun near 70°
  fall: { rise: 6.25, set: 19.25, noon: 0.82 }, // as it was drawn first: a long autumn day
}

/** The far woods' crowns and the hills round the valley. */
export const FAR: Record<Season, { crowns: number[]; hills: number }> = {
  winter: { crowns: [0x5f5852, 0x6e655c, 0x2f4636, 0x3a5240, 0x7a7068, 0xd9dee4, 0x544d47], hills: 0xdfe3e8 },
  spring: { crowns: [0x7fae4e, 0x9cc45a, 0x6a9a44, 0xe8bccb, 0x8bb85a, 0xf1d6de, 0x5f8f3e], hills: 0x6f8f3a },
  summer: { crowns: [0x3d6b2c, 0x4f7d34, 0x2f5a26, 0x5f8a3a, 0x46702f, 0x365f2a, 0x55803a], hills: 0x4f6a2a },
  fall: { crowns: [0x9c3b1e, 0xb8641e, 0xc99a2a, 0x6d6a24, 0x8a4a1c, 0x5f6b2c, 0xa8501c], hills: 0x5d5a2e },
}

/** Leaves on the trees, by kind of tree: none on a maple or birch in winter, a few dry ones left on an oak. */
export const LEAVES: Record<Season, Record<"maple" | "birch" | "oak", string[]>> = {
  winter: { maple: [], birch: [], oak: ["#8a6a44", "#7a5a38", "#9b7a50", "#6e5236"] },
  spring: {
    maple: ["#f2b8c6", "#e89ab0", "#f7d3dc", "#9ccc5a", "#b3d66e", "#e9a6ba", "#8fc24e"], // in blossom
    birch: ["#a8d468", "#9ccc5a", "#bfe07c", "#8fc24e", "#b3d66e", "#c8e68a", "#94c652"],
    oak: ["#8fbf4a", "#7fb03e", "#9fca58", "#76a83a", "#a6cf62", "#86b846", "#6f9e36"],
  },
  summer: {
    maple: ["#3f7a2e", "#4d8a35", "#356b28", "#5a9440", "#2f5f24", "#447f31", "#3a7029"],
    birch: ["#5f9a3c", "#6fa846", "#558f35", "#7ab250", "#4f8732", "#68a242", "#5a9538"],
    oak: ["#33612a", "#2c5624", "#3c6c2f", "#28501f", "#416f32", "#305b27", "#386629"],
  },
  fall: {
    maple: ["#b8321e", "#cf4a1f", "#e0681f", "#a2261c", "#d9532a", "#8e2a1c", "#e88a2a"],
    birch: ["#e2b42c", "#d39b1c", "#f0c94a", "#c98c18", "#e7bf3a", "#b5862a", "#d6a832"],
    oak: ["#a8742a", "#8a5a22", "#c48a2c", "#6f7a2a", "#9c6a1e", "#b77d34", "#7e8c32"],
  },
}

/** Leaves fallen on the lawns: only in fall. */
export const hasFallenLeaves = (season: Season) => season === "fall"
/** Snow on the ground and falling: only in winter. */
export const snows = (season: Season) => season === "winter"
