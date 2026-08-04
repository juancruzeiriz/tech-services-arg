import { Mesh, Program, Renderer, Triangle } from "ogl";

const VERTEX = `
  attribute vec2 uv;
  attribute vec2 position;
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position, 0.0, 1.0);
  }
`;

const FRAGMENT = `
  precision highp float;
  varying vec2 vUv;
  uniform float uTime;
  uniform vec2 uResolution;

  void main() {
    vec2 p = (vUv - 0.5) * vec2(uResolution.x / uResolution.y, 1.0) * 2.0;
    float wobble = 0.12 * sin(uTime * 0.4 + p.x * 3.0) + 0.06 * cos(uTime * 0.6 - p.y * 2.0);
    float d = length(p) - 0.42 + wobble;

    vec3 accent = vec3(1.0, 0.302, 0.094); /* #ff4d18 */
    vec3 ink = vec3(0.031, 0.035, 0.039);  /* #08090a */
    vec3 col = mix(accent, ink, smoothstep(0.0, 0.75, d));

    float alpha = 1.0 - smoothstep(0.15, 0.95, d);
    gl_FragColor = vec4(col, alpha * 0.85);
  }
`;

/**
 * Monta el shader del hero. Devuelve una función de limpieza, o null si no
 * corresponde animar (prefers-reduced-motion, o el navegador no da WebGL) —
 * en ese caso el gradiente CSS de fallback en HeroCanvas.astro queda visible.
 */
export function mountHeroGL(canvas: HTMLCanvasElement): (() => void) | null {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return null;

  let renderer: Renderer;
  try {
    renderer = new Renderer({ canvas, alpha: true, dpr: Math.min(devicePixelRatio, 2) });
  } catch {
    return null;
  }

  const gl = renderer.gl;
  if (!gl) return null;

  const program = new Program(gl, {
    vertex: VERTEX,
    fragment: FRAGMENT,
    uniforms: {
      uTime: { value: 0 },
      uResolution: { value: [canvas.clientWidth, canvas.clientHeight] },
    },
    transparent: true,
  });
  const mesh = new Mesh(gl, { geometry: new Triangle(gl), program });

  const resize = () => {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    renderer.setSize(width, height);
    program.uniforms.uResolution.value = [width, height];
  };
  resize();
  addEventListener("resize", resize);

  let raf = 0;
  let running = true;
  const loop = (t: number) => {
    if (!running) return;
    program.uniforms.uTime.value = t * 0.001;
    renderer.render({ scene: mesh });
    raf = requestAnimationFrame(loop);
  };

  // Pausar fuera de vista: un rAF corriendo abajo del fold quema batería sin
  // que nadie lo vea, y es lo que mantiene el INP bajo mientras se scrollea.
  const io = new IntersectionObserver(([entry]) => {
    running = entry.isIntersecting;
    if (running) raf = requestAnimationFrame(loop);
    else cancelAnimationFrame(raf);
  });
  io.observe(canvas);

  return () => {
    running = false;
    cancelAnimationFrame(raf);
    io.disconnect();
    removeEventListener("resize", resize);
  };
}
