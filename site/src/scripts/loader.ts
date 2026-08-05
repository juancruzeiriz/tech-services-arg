/**
 * Loader de intro: una grilla de bits (0/1) que arranca en ruido y colapsa
 * de izquierda a derecha hasta formar "JCE", con un contador 00->100.
 *
 * Deliberadamente NO se muestra vía un script pre-paint en <head> (como el
 * anti-flash de tema): eso invertiría la garantía de seguridad que ya usa
 * reveal.ts en este mismo proyecto -- "si el script no corre, el contenido
 * queda visible por defecto". Acá el default (sin JS, o si este módulo
 * nunca llega a correr) es exactamente lo opuesto de lo que hay que evitar:
 * el overlay tiene `display: none` en su CSS scoped y nada lo cambia salvo
 * esta función. Un loader que se muestra 30ms después del primer paint en
 * vez de antes es imperceptible; un overlay que se queda trabado para
 * siempre porque el script que lo iba a sacar nunca cargó, no lo es.
 *
 * Reglas: piso de 1.2s (para que se aprecie), techo de 2.5s (para no
 * castigar), atado a document.fonts.ready entre medio, sessionStorage para
 * que corra una vez por sesión, salteable con click o cualquier tecla, y
 * nunca corre bajo prefers-reduced-motion (es la definición misma de
 * movimiento ambiental que esa preferencia pide evitar).
 */

const SESSION_KEY = "loader-shown";
const FLOOR_MS = 1200;
const CEIL_MS = 2500;
const FADE_MS = 400;

// Dot-matrix 5x7 a mano, no una fuente -- el wordmark es la pieza de marca,
// así que se dibuja con la misma precisión con la que se diseñaría un logo.
const GLYPH_J = ["XXXXX", "..X..", "..X..", "..X..", "X.X..", "X.X..", ".X..."];
const GLYPH_C = [".XXX.", "X...X", "X....", "X....", "X....", "X...X", ".XXX."];
const GLYPH_E = ["XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "XXXXX"];

const ROWS = 7;
const GAP_COLS = 1;

function buildGlyphGrid(): boolean[][] {
  const letters = [GLYPH_J, GLYPH_C, GLYPH_E];
  const grid: boolean[][] = Array.from({ length: ROWS }, () => []);
  letters.forEach((letter, li) => {
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < letter[r].length; c++) grid[r].push(letter[r][c] === "X");
    }
    if (li < letters.length - 1) {
      for (let r = 0; r < ROWS; r++) for (let g = 0; g < GAP_COLS; g++) grid[r].push(false);
    }
  });
  return grid;
}

export function mountLoader(): void {
  let alreadyShown = true;
  try {
    alreadyShown = sessionStorage.getItem(SESSION_KEY) === "1";
  } catch {
    /* sessionStorage bloqueado (modo privado estricto): tratamos como ya
       mostrado -- de nuevo, el default seguro es NO mostrar, no mostrar
       siempre. */
  }
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (alreadyShown || reduceMotion) return;

  const overlay = document.querySelector<HTMLDivElement>("[data-loader]");
  const canvas = document.querySelector<HTMLCanvasElement>("[data-loader-canvas]");
  const countEl = document.querySelector<HTMLElement>("[data-loader-count]");
  if (!overlay || !canvas || !countEl) return;

  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const glyphs = buildGlyphGrid();
  const cols = glyphs[0].length;
  const cell = 15;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  canvas.width = cols * cell * dpr;
  canvas.height = ROWS * cell * dpr;
  canvas.style.width = `${cols * cell}px`;
  canvas.style.height = `${ROWS * cell}px`;
  ctx.scale(dpr, dpr);
  ctx.font = `${cell - 3}px "Cascadia Code", "SFMono-Regular", Consolas, monospace`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  overlay.classList.add("is-active");
  document.documentElement.classList.add("loader-active");

  let fontsReady = false;
  document.fonts.ready.then(() => {
    fontsReady = true;
  });

  const start = performance.now();
  let done = false;
  let raf = 0;

  function draw(progress: number) {
    const styles = getComputedStyle(document.documentElement);
    const accent = styles.getPropertyValue("--color-accent").trim() || "#ff4d18";
    const muted = styles.getPropertyValue("--fg-muted").trim() || "#8a8f98";
    ctx!.clearRect(0, 0, cols * cell, ROWS * cell);
    const resolvedCols = Math.floor(progress * cols);

    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < cols; c++) {
        const x = c * cell + cell / 2;
        const y = r * cell + cell / 2;
        if (c < resolvedCols) {
          if (glyphs[r][c]) {
            ctx!.globalAlpha = 1;
            ctx!.fillStyle = accent;
            ctx!.fillText("1", x, y);
          }
        } else {
          ctx!.globalAlpha = 0.5;
          ctx!.fillStyle = muted;
          ctx!.fillText(Math.random() < 0.5 ? "0" : "1", x, y);
        }
      }
    }
    ctx!.globalAlpha = 1;
  }

  function finish() {
    if (done) return;
    done = true;
    cancelAnimationFrame(raf);
    window.removeEventListener("keydown", finish);
    overlay!.removeEventListener("click", finish);
    overlay!.classList.add("is-leaving");
    try {
      sessionStorage.setItem(SESSION_KEY, "1");
    } catch {
      /* no persiste entre sesiones si sessionStorage está bloqueado -- el
         loader vuelve a correr la próxima carga, degradación aceptable. */
    }
    setTimeout(() => {
      document.documentElement.classList.remove("loader-active");
      overlay!.remove();
    }, FADE_MS);
  }

  window.addEventListener("keydown", finish, { once: true });
  overlay.addEventListener("click", finish, { once: true });

  function frame(now: number) {
    if (done) return;
    const elapsed = now - start;
    const floorProgress = Math.min(1, elapsed / FLOOR_MS);
    const pastFloor = elapsed >= FLOOR_MS;
    const pastCeil = elapsed >= CEIL_MS;

    const progress = pastCeil ? 1 : floorProgress;
    countEl!.textContent = String(Math.round(progress * 100)).padStart(2, "0");
    draw(progress);

    if (pastCeil || (pastFloor && fontsReady)) {
      finish();
      return;
    }
    raf = requestAnimationFrame(frame);
  }
  raf = requestAnimationFrame(frame);
}
