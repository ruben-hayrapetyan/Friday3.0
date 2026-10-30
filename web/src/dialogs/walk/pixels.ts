// Pixel art from a 3D scene: drawn small with dark edges where something stands in front of what's behind it, then a
// few shades fewer with an ordered dither, scaled up crisp. The walk through your week (World.ts) and the guide who
// shows you round Friday afterwards (shell/guide/Guide.ts) are both drawn this way.

import * as THREE from "three"
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js"
import { FullScreenQuad, Pass } from "three/examples/jsm/postprocessing/Pass.js"

/** The town drawn small, with dark edges where something stands in front of what's behind it, the way pixel art is
 * outlined. (Its own target, for its own depth: the composer's two share one depth texture.) */
export class Pixels extends Pass {
  private quad: FullScreenQuad
  private material: THREE.ShaderMaterial
  private camera: THREE.PerspectiveCamera
  private scene: THREE.Scene
  private beauty = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthTexture: new THREE.DepthTexture(1, 1) })

  constructor(scene: THREE.Scene, camera: THREE.PerspectiveCamera) {
    super()
    this.scene = scene
    this.camera = camera
    this.material = new THREE.ShaderMaterial({
      uniforms: { tDiffuse: { value: null }, tDepth: { value: null }, texel: { value: new THREE.Vector2() }, near: { value: 0.1 }, far: { value: 1600 } },
      vertexShader: "varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
      fragmentShader: `
        #include <packing>
        uniform sampler2D tDiffuse;
        uniform sampler2D tDepth;
        uniform vec2 texel;
        uniform float near;
        uniform float far;
        varying vec2 vUv;
        float away(vec2 uv) { return -perspectiveDepthToViewZ(texture2D(tDepth, uv).x, near, far); }
        void main() {
          vec4 c = texture2D(tDiffuse, vUv);
          float z = away(vUv);
          float gap = max(0.22, z * 0.045);
          float edge = 0.0;
          edge = max(edge, step(gap, away(vUv + vec2(texel.x, 0.0)) - z));
          edge = max(edge, step(gap, away(vUv - vec2(texel.x, 0.0)) - z));
          edge = max(edge, step(gap, away(vUv + vec2(0.0, texel.y)) - z));
          edge = max(edge, step(gap, away(vUv - vec2(0.0, texel.y)) - z));
          edge *= 1.0 - smoothstep(60.0, 160.0, z);
          gl_FragColor = vec4(mix(c.rgb, c.rgb * vec3(0.32, 0.3, 0.38), edge * 0.9), c.a);
        }`,
    })
    this.quad = new FullScreenQuad(this.material)
  }

  setSize(width: number, height: number): void {
    this.beauty.setSize(width, height)
    ;(this.material.uniforms.texel.value as THREE.Vector2).set(1 / width, 1 / height)
  }

  render(renderer: THREE.WebGLRenderer, writeBuffer: THREE.WebGLRenderTarget): void {
    renderer.setRenderTarget(this.beauty)
    renderer.clear()
    renderer.render(this.scene, this.camera)
    const u = this.material.uniforms
    u.tDiffuse.value = this.beauty.texture
    u.tDepth.value = this.beauty.depthTexture
    u.near.value = this.camera.near
    u.far.value = this.camera.far
    renderer.setRenderTarget(this.renderToScreen ? null : writeBuffer)
    this.quad.render(renderer)
  }
}

/** The film curve and colour, then fewer shades with an ordered dither, at the pixels' own size. `clear`: over the
 * page, nothing drawn where there's nothing (the dither would tint it). */
export class PixelOut extends OutputPass {
  readonly low: THREE.Vector2
  readonly iris = { value: 1 } // the wipe between places: 1 open, 0 shut
  readonly irisAt = { value: new THREE.Vector2(0.5, 0.5) } // its middle, on them
  constructor(clear = false) {
    super()
    const self = this as unknown as { uniforms: Record<string, THREE.IUniform>; material: THREE.RawShaderMaterial }
    this.low = new THREE.Vector2(1, 1)
    self.uniforms.uLow = { value: this.low }
    self.uniforms.uIris = this.iris
    self.uniforms.uIrisAt = this.irisAt
    self.material.fragmentShader = self.material.fragmentShader.replace("varying vec2 vUv;", "varying vec2 vUv;\nuniform vec2 uLow;\nuniform float uIris;\nuniform vec2 uIrisAt;\nfloat bayer2(vec2 a) { a = floor(a); return fract(a.x / 2.0 + a.y * a.y * 0.75); }\nfloat bayer4(vec2 a) { return bayer2(0.5 * a) * 0.25 + bayer2(a); }").replace(
      /}\s*$/,
      `  float levels = 22.0;
        float d = bayer4(floor(vUv * uLow)) - 0.5;
        gl_FragColor.rgb = floor(gl_FragColor.rgb * levels + 0.5 + d * 0.9) / levels;
        // the iris: a circle closing on them, as a game moves between scenes, in whole pixels
        if (uIris < 1.0) {
          vec2 off = (floor(vUv * uLow) - floor(uIrisAt * uLow)) / uLow.y;
          if (length(off) > uIris * 2.2) gl_FragColor.rgb = vec3(0.106, 0.102, 0.169);
        }${clear ? "\n        gl_FragColor = gl_FragColor.a < 0.5 ? vec4(0.0) : vec4(gl_FragColor.rgb, 1.0);" : ""}
      }`,
    )
  }
}
