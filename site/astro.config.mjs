// @ts-check
import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

// PENDIENTE DEL DUEÑO: reemplazar por el dominio real una vez comprado (ver
// docs/CHANNELS.md y la Tarea 0.2 del plan). Mientras tanto, canonical/OG/
// hreflang usan este placeholder — el sitio funciona igual, pero esas
// etiquetas apuntan a una URL que todavía no existe.
const SITE_URL = "https://tudominio.dev";

export default defineConfig({
  site: SITE_URL,
  output: "static",
  i18n: {
    locales: ["es", "en"],
    defaultLocale: "es",
    routing: { prefixDefaultLocale: true },
  },
  vite: {
    plugins: [tailwindcss()],
  },
  build: {
    inlineStylesheets: "always",
  },
});
