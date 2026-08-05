/**
 * Los blobs del hero reaccionan a la posición del mouse, además de su propia
 * flotación por CSS (ver HeroCanvas.astro). Solo en punteros finos -- igual
 * que cursor.ts, "seguir al mouse" no significa nada en táctil.
 *
 * Cada blob tiene una "profundidad" distinta (índice × un paso fijo) para
 * que el efecto lea como paralaje real y no como los tres moviéndose en
 * bloque, que se percibe como un solo objeto grande en vez de tres capas.
 */
export function mountHeroParallax(): (() => void) | null {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return null;
  if (!matchMedia("(pointer: fine)").matches) return null;

  const blobs = Array.from(document.querySelectorAll<HTMLElement>("[data-blob]"));
  if (blobs.length === 0) return null;

  let mouseX = innerWidth / 2;
  let mouseY = innerHeight / 2;
  let curX = mouseX;
  let curY = mouseY;

  const onMove = (e: MouseEvent) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
  };
  addEventListener("mousemove", onMove);

  let raf = 0;
  const loop = () => {
    curX += (mouseX - curX) * 0.06;
    curY += (mouseY - curY) * 0.06;
    const dx = (curX - innerWidth / 2) / innerWidth;
    const dy = (curY - innerHeight / 2) / innerHeight;

    blobs.forEach((el, i) => {
      const depth = 18 + i * 14;
      el.style.transform = `translate(${dx * depth}px, ${dy * depth}px)`;
    });

    raf = requestAnimationFrame(loop);
  };
  raf = requestAnimationFrame(loop);

  return () => {
    cancelAnimationFrame(raf);
    removeEventListener("mousemove", onMove);
    blobs.forEach((el) => {
      el.style.transform = "";
    });
  };
}
