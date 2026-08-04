import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";

gsap.registerPlugin(ScrollTrigger);

let lenisInstance: Lenis | null = null;

/** Arranca el scroll suave y lo sincroniza con GSAP. No hace nada si el
 * usuario pidió prefers-reduced-motion — el scroll nativo del navegador
 * queda como está, que es exactamente lo que esa preferencia pide. */
export function mountScroll(): Lenis | null {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return null;
  if (lenisInstance) return lenisInstance;

  const lenis = new Lenis({ duration: 1.1, smoothWheel: true });

  // Un solo rAF para Lenis y GSAP: dos loops de animación independientes
  // desincronizan el pin de ScrollTrigger y producen jitter visible en
  // cualquier sección pineada.
  lenis.on("scroll", ScrollTrigger.update);
  gsap.ticker.add((time) => {
    lenis.raf(time * 1000);
  });
  gsap.ticker.lagSmoothing(0);

  lenisInstance = lenis;
  return lenis;
}

export function getLenis(): Lenis | null {
  return lenisInstance;
}
