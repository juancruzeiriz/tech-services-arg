import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SplitText } from "gsap/SplitText";

gsap.registerPlugin(ScrollTrigger, SplitText);

/**
 * Anima cada [data-reveal] al entrar en viewport, y separa los títulos
 * (h1/h2 con [data-split]) en líneas para un efecto más editorial. Marca
 * <html> con .js-reveal ANTES de animar — esa clase es la que activa
 * `opacity: 0` en global.css, así que si este script nunca corre (JS
 * deshabilitado, error de red) el contenido queda visible por defecto.
 */
export function mountReveal(): void {
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const targets = document.querySelectorAll<HTMLElement>("[data-reveal]");
  if (targets.length === 0) return;

  if (reduceMotion) return; // el contenido ya es visible por defecto sin .js-reveal

  document.documentElement.classList.add("js-reveal");

  ScrollTrigger.batch("[data-reveal]", {
    start: "top 88%",
    onEnter: (batch) =>
      gsap.to(batch, {
        opacity: 1,
        y: 0,
        duration: 0.9,
        ease: "expo.out",
        stagger: 0.08,
        overwrite: true,
      }),
    once: true,
  });

  document.querySelectorAll<HTMLElement>("[data-split]").forEach((el) => {
    const split = new SplitText(el, { type: "lines", linesClass: "split-line" });
    gsap.set(split.lines, { overflow: "hidden" });
    gsap.from(split.lines, {
      yPercent: 110,
      duration: 0.8,
      ease: "expo.out",
      stagger: 0.06,
      scrollTrigger: { trigger: el, start: "top 90%" },
    });
  });
}
