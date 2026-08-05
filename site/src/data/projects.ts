export type Project = {
  slug: string;
  title: { es: string; en: string };
  summary: { es: string; en: string };
  /** El número que movió. null solo mientras un proyecto no tiene un resultado medido todavía. */
  metric: { es: string; en: string } | null;
  /** Madurez real del proyecto -- nunca "producción" si no hubo un cliente
   * pagando de por medio. Evita que un prototipo se lea como venta hecha. */
  status: { es: string; en: string };
  kind: "client" | "personal";
  /** Etapas reales del pipeline/flujo, cuando se pueden verificar contra el
   * código -- no una lista inventada para "llenar" el diagrama. Opcional:
   * los proyectos personales sin arquitectura documentada no llevan una. */
  stages?: { es: string; en: string }[];
  stack: string[];
  year: number;
  url: string | null;
  repo: string | null;
};

// Para sumar un proyecto nuevo: copiar este bloque, completar con datos reales
// (nunca un número inventado — ver la regla que ya aplica el propio pipeline
// de gtm/factory/outreach.py).
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
    status: { es: "En desarrollo activo", en: "Actively in development" },
    kind: "personal",
    stages: [
      { es: "Descubrir", en: "Discover" },
      { es: "Puntuar", en: "Score" },
      { es: "Generar", en: "Generate" },
      { es: "Publicar", en: "Deploy" },
      { es: "Contactar", en: "Contact" },
      { es: "Enviar", en: "Outreach" },
    ],
    stack: ["Python", "FastAPI", "PostgreSQL", "Jinja2", "Cloudflare Pages"],
    year: 2026,
    url: null,
    repo: null,
  },
  {
    slug: "fluidez",
    title: { es: "Fluidez", en: "Fluidez" },
    summary: {
      es: "PWA que entrena la expresión oral en sesiones de ~10 minutos: recuperación léxica, velocidad al hablar, precisión de vocabulario y confianza bajo presión de tiempo.",
      en: "A PWA that trains spoken fluency in ~10-minute sessions: lexical retrieval, speaking speed, vocabulary precision, and confidence under time pressure.",
    },
    metric: null,
    status: { es: "Proyecto personal", en: "Personal project" },
    kind: "personal",
    stack: ["React", "TypeScript", "Vite", "IndexedDB", "Web Speech API"],
    year: 2025,
    url: null,
    repo: "https://github.com/juancruzeiriz/fluidez-app",
  },
  {
    slug: "bankanalytics",
    title: { es: "BankAnalytics", en: "BankAnalytics" },
    summary: {
      es: "Dashboard local que convierte extractos bancarios exportados en insights de gasto y ahorro.",
      en: "A local dashboard that turns exported bank statements into spend and savings insights.",
    },
    metric: null,
    status: { es: "Proyecto personal", en: "Personal project" },
    kind: "personal",
    stack: ["Python", "Pandas"],
    year: 2025,
    url: null,
    repo: null,
  },
  {
    slug: "quantbot-ar",
    title: { es: "QuantBot-AR", en: "QuantBot-AR" },
    summary: {
      es: "Bot de trading algorítmico, más un bot de IA que monitorea noticias del mercado.",
      en: "An algorithmic trading bot, plus an AI bot that monitors market news.",
    },
    metric: null,
    status: { es: "Proyecto personal", en: "Personal project" },
    kind: "personal",
    stack: ["Python", "Databricks"],
    year: 2025,
    url: null,
    repo: null,
  },
  {
    slug: "selfcheck",
    title: { es: "selfcheck", en: "selfcheck" },
    summary: {
      es: "Herramienta que audita tu propia huella digital pública.",
      en: "A tool that audits your own public digital footprint.",
    },
    metric: null,
    status: { es: "Proyecto personal", en: "Personal project" },
    kind: "personal",
    stack: ["Python"],
    year: 2025,
    url: null,
    repo: null,
  },
];
