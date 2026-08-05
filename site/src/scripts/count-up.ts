/**
 * Cuenta hacia arriba los números de StatsBand al entrar en viewport, una
 * sola vez. Parsea el texto ya renderizado ("~400", "95+", "6") en vez de
 * pedirle a StatsBand.astro un dato numérico aparte -- así el HTML sigue
 * siendo la fuente de verdad y esto solo lo anima.
 *
 * Bajo reduced-motion no anima: el valor final ya está en el DOM (esto es
 * progreso, no decoración -- si no corre, el usuario simplemente ve el
 * número quieto, nunca "0" pegado ahí).
 */
export function mountCountUp(): void {
  const targets = document.querySelectorAll<HTMLElement>(".stats-value");
  if (targets.length === 0) return;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        io.unobserve(entry.target);
        animate(entry.target as HTMLElement);
      }
    },
    { threshold: 0.4 },
  );
  targets.forEach((el) => io.observe(el));
}

function animate(el: HTMLElement): void {
  const raw = el.textContent?.trim() ?? "";
  const match = raw.match(/^(\D*)(\d+)(\D*)$/);
  if (!match) return; // sin dígitos (no debería pasar hoy) -- se deja como está

  const [, prefix, digits, suffix] = match;
  const target = parseInt(digits, 10);
  const duration = 1100;
  const start = performance.now();

  function frame(now: number) {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - (1 - t) ** 3; // ease-out cúbico: arranca rápido, frena en el valor final
    el.textContent = `${prefix}${Math.round(target * eased)}${suffix}`;
    if (t < 1) requestAnimationFrame(frame);
    else el.textContent = raw; // el valor exacto, sin drift de redondeo
  }
  requestAnimationFrame(frame);
}
