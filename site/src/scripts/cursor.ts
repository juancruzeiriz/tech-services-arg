/**
 * Cursor a medida con lerp e imán en [data-magnetic]. Solo en dispositivos
 * con puntero fino (mouse/trackpad) — nunca en táctil, donde no hay cursor
 * que mostrar y el "imán" no tiene sentido sin hover.
 */
export function mountCursor(): (() => void) | null {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return null;
  if (!matchMedia("(pointer: fine)").matches) return null;

  const dot = document.createElement("div");
  dot.className = "cursor-dot";
  document.body.appendChild(dot);
  document.documentElement.classList.add("has-cursor-dot");

  let mouseX = innerWidth / 2;
  let mouseY = innerHeight / 2;
  let dotX = mouseX;
  let dotY = mouseY;
  let magnetTarget: HTMLElement | null = null;

  const onMove = (e: MouseEvent) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
  };
  addEventListener("mousemove", onMove);

  const magnets = Array.from(document.querySelectorAll<HTMLElement>("[data-magnetic]"));
  const onEnter = (el: HTMLElement) => () => {
    magnetTarget = el;
  };
  // Cierra sobre el elemento que se abandona -- la versión anterior anulaba
  // magnetTarget y DESPUÉS testeaba si era null (siempre verdadero) y
  // limpiaba el transform de TODOS los imanes en cada mouseleave, no solo
  // del que se estaba abandonando.
  const onLeave = (el: HTMLElement) => () => {
    if (magnetTarget === el) magnetTarget = null;
    el.style.transform = "";
  };
  const cleanups = magnets.map((el) => {
    const enter = onEnter(el);
    const leave = onLeave(el);
    el.addEventListener("mouseenter", enter);
    el.addEventListener("mouseleave", leave);
    return () => {
      el.removeEventListener("mouseenter", enter);
      el.removeEventListener("mouseleave", leave);
    };
  });

  let raf = 0;
  const loop = () => {
    dotX += (mouseX - dotX) * 0.18;
    dotY += (mouseY - dotY) * 0.18;
    dot.style.transform = `translate3d(${dotX}px, ${dotY}px, 0)`;

    if (magnetTarget) {
      const rect = magnetTarget.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const pull = 0.35;
      magnetTarget.style.transform = `translate(${(mouseX - cx) * pull}px, ${(mouseY - cy) * pull}px)`;
    }

    raf = requestAnimationFrame(loop);
  };
  raf = requestAnimationFrame(loop);

  return () => {
    cancelAnimationFrame(raf);
    removeEventListener("mousemove", onMove);
    cleanups.forEach((fn) => fn());
    dot.remove();
    document.documentElement.classList.remove("has-cursor-dot");
  };
}
