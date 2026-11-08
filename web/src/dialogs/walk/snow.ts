// Snow falling round the camera in winter (walk/season.ts): a box of flakes that follows the camera, each falling
// and drifting, wrapping round when it leaves the box, so the street always has snow in the air and never runs out.

import * as THREE from "three"
import { random } from "./textures"

const BOX = { x: 44, y: 22, z: 44 } // metres round the camera
const COUNT = 1800
const FALL = 1.1 // metres a second, as light snow falls

export class Snowfall {
  readonly points: THREE.Points
  private drift: Float32Array

  constructor() {
    const rnd = random(7171)
    const at = new Float32Array(COUNT * 3)
    this.drift = new Float32Array(COUNT)
    for (let i = 0; i < COUNT; i++) {
      at[i * 3] = (rnd() - 0.5) * BOX.x
      at[i * 3 + 1] = rnd() * BOX.y
      at[i * 3 + 2] = (rnd() - 0.5) * BOX.z
      this.drift[i] = rnd() * Math.PI * 2
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute("position", new THREE.BufferAttribute(at, 3))
    const mat = new THREE.PointsMaterial({ color: 0xf4f7fb, size: 0.035, transparent: true, opacity: 0.75, depthWrite: false })
    this.points = new THREE.Points(geo, mat)
    this.points.frustumCulled = false
    this.points.userData.noAO = true
  }

  /** Move the flakes on by `dt` seconds and keep the box round `camera`. */
  update(dt: number, seconds: number, camera: THREE.Vector3): void {
    this.points.position.set(camera.x, 0, camera.z)
    const pos = this.points.geometry.attributes.position as THREE.BufferAttribute
    const at = pos.array as Float32Array
    for (let i = 0; i < COUNT; i++) {
      const sway = Math.sin(seconds * 0.7 + this.drift[i]) * 0.35
      at[i * 3] += sway * dt
      at[i * 3 + 1] -= FALL * dt * (0.75 + (this.drift[i] % 1) * 0.5)
      if (at[i * 3 + 1] < 0) at[i * 3 + 1] += BOX.y
      if (at[i * 3] > BOX.x / 2) at[i * 3] -= BOX.x
      if (at[i * 3] < -BOX.x / 2) at[i * 3] += BOX.x
    }
    pos.needsUpdate = true
  }
}
