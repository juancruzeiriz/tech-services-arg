/** Parte un título en palabras para el enmascarado con [data-split] (ver
 * global.css). Reemplaza a SplitText de GSAP: acá el split pasa a build
 * time, en el propio template de Astro, en vez de manipular el DOM en el
 * cliente. */
export function splitWords(text: string): string[] {
  return text.split(" ").filter(Boolean);
}
