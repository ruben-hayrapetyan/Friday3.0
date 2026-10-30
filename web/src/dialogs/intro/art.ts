// The intro's pixel art (29 Oct: "actually have cool game-like animations where an animated sprite is taking you
// through for example a week"): Friday as a little calendar page that walks, sleeps, works and cheers, the props of
// its day, and a 3×5 font for the words in its world. Each sprite is rows of letters, a letter a pixel, in PAL's
// colours; "." is clear. Pure: drawing is draw.ts.

export const PAL: Record<string, string> = {
  k: "#23263a", // ink
  w: "#fdfdf8", // page
  c: "#dfe3d6", // page's shade
  g: "#5fae6e", // Friday's band: work green
  G: "#93d49c",
  d: "#3d7f4e",
  b: "#5b7fd1", // class blue
  B: "#8fabeb",
  n: "#3d5ba6",
  p: "#f29b6b", // peach
  P: "#f9c39f",
  r: "#c46f45",
  y: "#f4c542", // gold
  Y: "#ffe183",
  o: "#c4951a",
  m: "#a9b2e6", // moon
  M: "#7a84c4",
  s: "#7fc8f8", // sweat, screen glow
  e: "#e05a4f", // red
  l: "#b678c9", // lilac
  t: "#8a5a3b", // wood
  T: "#a8744d",
  u: "#5a3a28",
  a: "#9aa0b4", // grey
}

// Friday: its page from the rings down to the bottom edge; faces and legs drawn over and under it.
const TOP = [
  "...kkk....kkk...",
  "...k.k....k.k...",
  ".kkkkkkkkkkkkkk.",
  ".kGGGGGGGGGGGGk.",
  ".kggggggggggggk.",
  ".kddddddddddddk.",
  ".kwwwwwwwwwwwwk.",
  ".kwwwwwwwwwwwwk.",
]
const FACES: Record<string, string[]> = {
  open: [".kwwkkwwwwkkwwk.", ".kwwkkwwwwkkwwk.", ".kwpwwwwwwwwpwk.", ".kwwwwwkkwwwwwk.", ".kwwwwwwwwwwwwk."],
  blink: [".kwwwwwwwwwwwwk.", ".kwwkkwwwwkkwwk.", ".kwpwwwwwwwwpwk.", ".kwwwwwkkwwwwwk.", ".kwwwwwwwwwwwwk."],
  happy: [".kwwkkwwwwkkwwk.", ".kwwkkwwwwkkwwk.", ".kwpwwwwwwwwpwk.", ".kwwwwkkkkwwwwk.", ".kwwwwwkkwwwwwk."],
  yawn: [".kwwwwwwwwwwwwk.", ".kwkkkwwwwkkkwk.", ".kwpwwwkkwwwpwk.", ".kwwwwwkkwwwwwk.", ".kwwwwwkkwwwwwk."],
  look: [".kwwwkkwwwwkkwk.", ".kwwwkkwwwwkkwk.", ".kwpwwwwwwwwpwk.", ".kwwwwwwkkwwwwk.", ".kwwwwwwwwwwwwk."], // eyes to the right: reading
}
const BOTTOM = [".kcccccccccccck.", "..kkkkkkkkkkkk.."]
const LEGS: Record<string, string[]> = {
  stand: ["....kk....kk....", "...kkk....kkk..."],
  apart: ["...kk......kk...", "..kkk......kkk.."],
  together: [".....kk..kk.....", "....kkk..kkk...."],
  none: ["................", "................"],
}

export type Face = keyof typeof FACES
export type Legs = keyof typeof LEGS

/** Friday, 16 × 17: a face and a pair of legs. */
export function friday(face: Face = "open", legs: Legs = "stand"): string[] {
  return [...TOP, ...FACES[face], ...BOTTOM, ...LEGS[legs]]
}

/** Friday's walk, a frame each tenth of a second or so. */
export const WALK: Legs[] = ["apart", "stand", "together", "stand"]

export const ZZZ = ["kkk", "..k", ".k.", "k..", "kkk"]

export const HEART = [".e.e.", "eeeee", "eeeee", ".eee.", "..e.."]

export const SPARKLE = ["..y..", "..y..", "yyYyy", "..y..", "..y.."]

export const DROP = [".s.", "sss", "sss", ".s."]

export const SUN = [
  "......y......",
  "..y...y...y..",
  "...y.....y...",
  ".....yyy.....",
  "....yYYyy....",
  "...yYYyyyy...",
  "yy.yYyyyyo.yy",
  "...yyyyyyo...",
  "....yyyoo....",
  ".....ooo.....",
  "...y.....y...",
  "..y...y...y..",
  "......y......",
]

export const MOON = ["...mmmm..", ".mmmmM...", ".mmmM....", "mmmM.....", "mmmM.....", "mmmM.....", ".mmmM....", ".mmmmM...", "...mmmm.."]

/** The alarm clock on the nightstand: a face, two bells, two feet. */
export const ALARM = [
  ".kk.....kk.",
  "kyyk...kyyk",
  ".kkkkkkkkk.",
  "kkwwwkwwwkk",
  "kwwwwkwwwwk",
  "kwwwwkkkwwk",
  "kwwwwwwwwwk",
  "kkwwwwwwwkk",
  ".kkkkkkkkk.",
  ".k.......k.",
]

export const LAPTOP = [
  "kkkkkkkkkkk.",
  "kssssssssk..",
  "ksBBBssssk..",
  "ksssBBBBsk..",
  "ksBBssssskk.",
  "kkkkkkkkkkk.",
  ".aaaaaaaaaaa",
  "kkkkkkkkkkkk",
]

export const MUG = ["kkkkk.", "kwwwkk", "kwwwk.k", "kwwwkk", ".kkk.."].map((r) => r.padEnd(7, ".").slice(0, 7))

export const PAPER = [
  "kkkkkkkkkkk",
  "kwwwwwwwwwk",
  "kwkkkkkkwwk",
  "kwwwwwwwwwk",
  "kwkkwkkkkwk",
  "kwkkwwwwwwk",
  "kwkkwkkkkwk",
  "kwwwwwwwwwk",
  "kwkkkkwkkwk",
  "kwwwwwwwwwk",
  "kkkkkkkkkkk",
]

export const CONTROLLER = [".kkkkkkk.", "kaaaaaaak", "kakaaaeak", "kkkaaaaYk", "kakaaaaak", ".kk...kk."]

export const CHECK_FLAG = ["kggg", "kgGg", "kggd", "k...", "k...", "k...", "k..."]

export const BAG = [
  "....kkkk....",
  "...k....k...",
  ".kkkkkkkkkk.",
  "kppppppppppk",
  "kpPPPPPPPPpk",
  "kppppppppppk",
  "kprrrrrrrrpk",
  "kpppkkkkpppk",
  "kpppkyykpppk",
  "kpppkkkkpppk",
  "kppppppppppk",
  ".kkkkkkkkkk.",
]

export const CHIP = [".k.k.k.", "kkkkkkk", ".kllllk", "kkllllk", ".kllllk", "kkkkkkk", ".k.k.k."].map((r) => r.padEnd(7, "."))

export const CAL = [".k...k.", "kkkkkkk", "keeeeek", "kwwwwwk", "kwkwkwk", "kwwwwwk", "kkkkkkk"]

/** 3 × 5 letters for the world's signs and clocks. */
const FONT: Record<string, string[]> = {
  A: [".#.", "#.#", "###", "#.#", "#.#"],
  B: ["##.", "#.#", "##.", "#.#", "##."],
  C: [".##", "#..", "#..", "#..", ".##"],
  D: ["##.", "#.#", "#.#", "#.#", "##."],
  E: ["###", "#..", "##.", "#..", "###"],
  F: ["###", "#..", "##.", "#..", "#.."],
  G: [".##", "#..", "#.#", "#.#", ".##"],
  H: ["#.#", "#.#", "###", "#.#", "#.#"],
  I: ["###", ".#.", ".#.", ".#.", "###"],
  J: ["..#", "..#", "..#", "#.#", ".#."],
  K: ["#.#", "#.#", "##.", "#.#", "#.#"],
  L: ["#..", "#..", "#..", "#..", "###"],
  M: ["#.#", "###", "#.#", "#.#", "#.#"],
  N: ["##.", "#.#", "#.#", "#.#", "#.#"],
  O: [".#.", "#.#", "#.#", "#.#", ".#."],
  P: ["##.", "#.#", "##.", "#..", "#.."],
  Q: [".#.", "#.#", "#.#", "##.", ".##"],
  R: ["##.", "#.#", "##.", "#.#", "#.#"],
  S: [".##", "#..", ".#.", "..#", "##."],
  T: ["###", ".#.", ".#.", ".#.", ".#."],
  U: ["#.#", "#.#", "#.#", "#.#", "###"],
  V: ["#.#", "#.#", "#.#", "#.#", ".#."],
  W: ["#.#", "#.#", "#.#", "###", "#.#"],
  X: ["#.#", "#.#", ".#.", "#.#", "#.#"],
  Y: ["#.#", "#.#", ".#.", ".#.", ".#."],
  Z: ["###", "..#", ".#.", "#..", "###"],
  "0": ["###", "#.#", "#.#", "#.#", "###"],
  "1": [".#.", "##.", ".#.", ".#.", "###"],
  "2": ["##.", "..#", ".#.", "#..", "###"],
  "3": ["##.", "..#", ".#.", "..#", "##."],
  "4": ["#.#", "#.#", "###", "..#", "..#"],
  "5": ["###", "#..", "##.", "..#", "##."],
  "6": [".##", "#..", "###", "#.#", "###"],
  "7": ["###", "..#", ".#.", ".#.", ".#."],
  "8": ["###", "#.#", "###", "#.#", "###"],
  "9": ["###", "#.#", "###", "..#", "##."],
  ":": ["...", ".#.", "...", ".#.", "..."],
  "!": [".#.", ".#.", ".#.", "...", ".#."],
  "?": ["##.", "..#", ".#.", "...", ".#."],
  "+": ["...", ".#.", "###", ".#.", "..."],
  "-": ["...", "...", "###", "...", "..."],
  ".": ["...", "...", "...", "...", ".#."],
  ",": ["...", "...", "...", ".#.", "#.."],
  "'": [".#.", ".#.", "...", "...", "..."],
  " ": ["...", "...", "...", "...", "..."],
}

/** A line of text as a sprite in one colour letter: 4 pixels a character. */
export function words(text: string, ink = "k"): string[] {
  const glyphs = [...text.toUpperCase()].map((ch) => FONT[ch] ?? FONT[" "])
  return [0, 1, 2, 3, 4].map((row) =>
    glyphs
      .map((g) => g[row].replace(/#/g, ink))
      .join(".")
  )
}

export function textWidth(text: string): number {
  return text.length * 4 - 1
}
