// The little of picomatch its patch test uses (src/picomatchPatch.test.ts); picomatch ships no types.
declare module "picomatch" {
  interface Picomatch {
    makeRe(glob: string): RegExp
    isMatch(input: string, glob: string): boolean
  }
  const picomatch: Picomatch
  export default picomatch
}
