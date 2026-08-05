// @ts-check
import { defineConfig, fontProviders } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

const SITE_URL = "https://juancruzeiriz.com";

export default defineConfig({
  site: SITE_URL,
  output: "static",
  i18n: {
    locales: ["es", "en"],
    defaultLocale: "es",
    // redirectToDefaultLocale:false es el fix del bug real de producción del
    // 2026-08-05: sin esto, Astro pisa src/pages/index.astro con SU PROPIO
    // redirect automático (un HTML desnudo, "Redirecting from / to /es/",
    // con 2 segundos de <meta refresh> antes de saltar) -- nuestro
    // index.astro, que hace detección real de idioma del navegador y
    // redirige al instante (content="0;..."), nunca llegaba a compilarse.
    routing: { prefixDefaultLocale: true, redirectToDefaultLocale: false },
  },
  vite: {
    plugins: [tailwindcss()],
  },
  build: {
    inlineStylesheets: "always",
  },
  experimental: {
    // Self-hosteadas (provider "local", no "google"): los bytes quedan
    // revisables en git y el build no depende de la red. El archivo latin
    // (Latin-1 Supplement, U+00-FF) ya cubre á/é/í/ó/ú/ñ/ü/¿/¡ -- no hace
    // falta el subset latin-ext.
    fonts: [
      {
        name: "Instrument Sans",
        cssVariable: "--font-display",
        provider: fontProviders.local(),
        options: {
          variants: [
            {
              weight: "400 700",
              style: "normal",
              src: ["./src/assets/fonts/InstrumentSans-latin.woff2"],
            },
          ],
        },
        fallbacks: ["system-ui", "sans-serif"],
        optimizedFallbacks: true,
      },
      {
        name: "Instrument Serif",
        cssVariable: "--font-editorial",
        provider: fontProviders.local(),
        options: {
          variants: [
            {
              weight: "400",
              style: "italic",
              src: ["./src/assets/fonts/InstrumentSerif-Italic-latin.woff2"],
            },
          ],
        },
        fallbacks: ["Georgia", "serif"],
        optimizedFallbacks: true,
      },
    ],
  },
});
