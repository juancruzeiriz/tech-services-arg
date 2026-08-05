/**
 * Revela cada [data-reveal] al entrar en viewport. En navegadores con
 * scroll-driven animations (`animation-timeline: view()`), todo el trabajo
 * lo hace el CSS de global.css -- acá solo se pone .js-reveal para activar
 * esas reglas. Donde no hay soporte, un IntersectionObserver agrega
 * .is-visible a mano, que dispara la misma transición por otro camino.
 *
 * Marca <html> con .js-reveal ANTES de animar -- esa clase es la que activa
 * `opacity: 0` en global.css, así que si este script nunca corre (JS
 * deshabilitado, error de red) el contenido queda visible por defecto.
 */
export function mountReveal(): void {
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const targets = document.querySelectorAll<HTMLElement>("[data-reveal]");
  if (targets.length === 0 || reduceMotion) return;

  document.documentElement.classList.add("js-reveal");

  if (typeof CSS !== "undefined" && CSS.supports("animation-timeline: view()")) {
    return; // el CSS se encarga solo, ver @supports en global.css
  }

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add("is-visible");
        io.unobserve(entry.target);
      }
    },
    { rootMargin: "0px 0px -12% 0px" },
  );
  targets.forEach((el) => io.observe(el));
}
