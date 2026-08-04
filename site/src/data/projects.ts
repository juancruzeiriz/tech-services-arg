export type Project = {
  slug: string;
  title: { es: string; en: string };
  summary: { es: string; en: string };
  /** El número que movió. null solo mientras un proyecto no tiene un resultado medido todavía. */
  metric: { es: string; en: string } | null;
  stack: string[];
  year: number;
  image: string;
  url: string | null;
  repo: string | null;
};

// Para sumar un proyecto nuevo: copiar este bloque, completar con datos reales
// (nunca un número inventado — ver la regla que ya aplica el propio pipeline
// de gtm/factory/outreach.py) y agregar la imagen a public/img/projects/.
export const projects: Project[] = [
  {
    slug: "gtm-factory",
    title: {
      es: "Fábrica de demos de prospección",
      en: "Prospecting demo factory",
    },
    summary: {
      es: "Pipeline en Python que descubre negocios de oficio en Google Places, mide su sitio actual con las mismas APIs públicas de Google (PageSpeed, Chrome UX Report), genera una demo con los datos reales del negocio y la publica antes del primer contacto.",
      en: "A Python pipeline that discovers trade businesses via Google Places, audits their current site with Google's own public APIs (PageSpeed, Chrome UX Report), generates a demo from the business's real data, and publishes it before first contact.",
    },
    metric: {
      es: "~400 tests automatizados, 6 etapas encadenadas, cero dependencias externas en cada sitio generado",
      en: "~400 automated tests, 6 chained stages, zero external dependencies in each generated site",
    },
    stack: ["Python", "FastAPI", "PostgreSQL", "Jinja2", "Cloudflare Pages"],
    year: 2026,
    image: "/img/projects/gtm-factory.svg",
    url: null,
    repo: null,
  },
];
