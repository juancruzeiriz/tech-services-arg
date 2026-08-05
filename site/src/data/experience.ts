export type ExperienceEntry = {
  id: string;
  role: { es: string; en: string };
  org: string;
  /** Aclaración opcional del org (ej. el producto/cliente detrás del
   * empleador). Separada de `org` para que el timeline pueda mostrarla en una
   * línea aparte, más chica -- "Market One" cabe en la columna angosta de
   * mobile, "PHI (Cost-to-Serve & Profit Management Software)" no. */
  orgDetail?: string;
  from: string; // "2024" o "2024-03"
  to: string | null; // null = presente
  bullets: { es: string[]; en: string[] };
};

// El HTML de esta sección es lo que indexa Google (el PDF en /cv/ es solo la
// descarga) — por eso el contenido vive acá como datos, no solo en el PDF.
// Transcripto de LinkedIn (fuente de las fechas, siempre actualizada) y del
// CV en inglés (detalle de stack por rol).
export const experience: ExperienceEntry[] = [
  {
    id: "market-one",
    role: {
      es: "Software Developer — Django REST Framework (Python)",
      en: "Software Developer — Django REST Framework (Python)",
    },
    org: "Market One",
    orgDetail: "PHI (Cost-to-Serve & Profit Management Software)",
    from: "2021-12",
    to: null,
    bullets: {
      es: [
        "Backend en Django REST Framework para un producto de gestión de costos y rentabilidad.",
        "Stack: Python (Django, Flask, Pandas), Docker, Azure, Google App Engine, Databricks, React.",
        "Persistencia en PostgreSQL, SQL Server, MySQL y MongoDB según el proyecto.",
      ],
      en: [
        "Django REST Framework backend for a cost-to-serve and profitability management product.",
        "Stack: Python (Django, Flask, Pandas), Docker, Azure, Google App Engine, Databricks, React.",
        "Persistence across PostgreSQL, SQL Server, MySQL and MongoDB depending on the project.",
      ],
    },
  },
  {
    id: "freelance",
    role: { es: "Desarrollador full-stack Python", en: "Full-stack Python developer" },
    org: "Freelance",
    from: "2020-02",
    to: "2022-01",
    bullets: {
      es: ["Desarrollo de aplicaciones web y mantenimiento de scripts con Flask y Django para distintos clientes."],
      en: ["Web application development and script maintenance with Flask and Django for various clients."],
    },
  },
  {
    id: "utn-fullstack",
    role: { es: "Desarrollador full-stack PHP y React", en: "Full-stack PHP and React developer" },
    org: "UTN — Buenos Aires",
    from: "2021-05",
    to: "2021-12",
    bullets: {
      es: ["Desarrollo y mantenimiento de sistemas internos de la facultad con Symfony, CakePHP y React.", "POO, metodología ágil, Docker."],
      en: ["Development and maintenance of internal university systems with Symfony, CakePHP and React.", "OOP, agile methodology, Docker."],
    },
  },
  {
    id: "utn-soporte",
    role: { es: "Analista y soporte de aplicaciones", en: "Application analyst and support" },
    org: "UTN — Buenos Aires",
    from: "2018-09",
    to: "2021-08",
    bullets: {
      es: [
        "Soporte a trabajadores y alumnos por ticket, teléfono y presencial.",
        "Gestión de bases de datos: inserts, updates, stored procedures, triggers y reportes con joins.",
        "Análisis, implementación y mantenimiento de proyectos internos; scripts en Python.",
      ],
      en: [
        "Support for staff and students via ticket, phone and in person.",
        "Database management: inserts, updates, stored procedures, triggers and join-based reports.",
        "Analysis, implementation and maintenance of internal projects; Python scripts.",
      ],
    },
  },
  {
    id: "stefanini",
    role: { es: "Soporte técnico", en: "Technical support" },
    org: "Stefanini Argentina",
    from: "2017-06",
    to: "2018-07",
    bullets: {
      es: ["Atención telefónica; análisis, seguimiento y resolución de incidentes; asistencia remota y troubleshooting."],
      en: ["Phone support; incident analysis, tracking and resolution; remote assistance and troubleshooting."],
    },
  },
];
