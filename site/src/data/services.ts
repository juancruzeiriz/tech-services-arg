export type Service = {
  id: string;
  title: { es: string; en: string };
  /** Una oración en lenguaje llano, sin jerga -- lo que lee un dueño de
   * negocio que no sabe de programación. Es lo único que aparece en la home. */
  plain: { es: string; en: string };
  /** Detalle técnico -- vive en /servicios, no en la home. */
  detail: { es: string; en: string };
  stack: string[];
};

// Las cinco áreas reales de trabajo, no solo "desarrollo web" -- eso era un
// recorte del posicionamiento original que dejaba afuera IA/automatización,
// datos y cloud, que es la mitad de lo que el dueño factura.
export const services: Service[] = [
  {
    id: "ai-automation",
    title: { es: "Automatizaciones e IA", en: "Automation & AI" },
    plain: {
      es: "Un bot que atiende por WhatsApp con la información real de tu empresa, y procesos que hoy hacés a mano y pasan a correr solos.",
      en: "A bot that handles WhatsApp using your business's real data, and manual processes that start running on their own.",
    },
    detail: {
      es: "Agentes y bots de IA (WhatsApp, Discord, web) entrenados con la información propia del negocio, más dashboards generados por IA directo desde tus datos.",
      en: "AI agents and bots (WhatsApp, Discord, web) trained on your own business data, plus AI-generated dashboards straight from your data.",
    },
    stack: ["Python", "LLMs", "RAG", "WhatsApp Business API"],
  },
  {
    id: "data",
    title: { es: "Datos y tableros", en: "Data & dashboards" },
    plain: {
      es: "Tus planillas y sistemas convertidos en un tablero que contesta preguntas: qué se vende, qué cuesta, dónde se escapa la plata.",
      en: "Your spreadsheets and systems turned into a dashboard that answers questions: what sells, what it costs, where the money leaks.",
    },
    detail: {
      es: "Procesos ETL, análisis de insights sobre datos propios, y bots de trading algorítmico cuando el dominio es financiero.",
      en: "ETL pipelines, insight analysis on your own data, and algorithmic trading bots when the domain is financial.",
    },
    stack: ["Databricks", "Pandas", "PostgreSQL", "ETL"],
  },
  {
    id: "backend",
    title: { es: "Sistemas y APIs a medida", en: "Custom systems & APIs" },
    plain: {
      es: "El software interno que tu operación necesita, y las integraciones para que tus sistemas se hablen entre sí.",
      en: "The internal software your operation needs, and the integrations that get your systems talking to each other.",
    },
    detail: {
      es: "APIs RESTful y microservicios en Python (Django, Django REST Framework, Flask), con bases de datos relacionales y no relacionales según el caso.",
      en: "RESTful APIs and microservices in Python (Django, Django REST Framework, Flask), with relational and non-relational databases as needed.",
    },
    stack: ["Django", "DRF", "Flask", "PostgreSQL", "MongoDB"],
  },
  {
    id: "cloud",
    title: { es: "Infraestructura y nube", en: "Cloud & infrastructure" },
    plain: {
      es: "Que corra siempre, que no dependa de una computadora prendida, y que se pueda volver atrás si algo sale mal.",
      en: "Something that always runs, doesn't depend on a machine staying on, and can be rolled back if something breaks.",
    },
    detail: {
      es: "Despliegue y mantenimiento en Azure, Google Cloud y AWS, con Docker e Infraestructura como Código para que un ambiente se pueda recrear igual, siempre.",
      en: "Deployment and maintenance on Azure, Google Cloud and AWS, with Docker and Infrastructure as Code so an environment can always be recreated identically.",
    },
    stack: ["Azure", "Google Cloud", "AWS", "Docker", "IaC"],
  },
  {
    id: "web",
    title: { es: "Sitios y presencia web", en: "Websites & web presence" },
    plain: {
      es: "Sitios rápidos y medibles. El que estás viendo puntúa 95+ en las métricas públicas de Google, verificable en el momento.",
      en: "Fast, measurable websites. The one you're looking at scores 95+ on Google's own public metrics, verifiable on the spot.",
    },
    detail: {
      es: "Sitios estáticos de alto rendimiento (Astro), sin humo: la prueba es este mismo sitio, no una captura de pantalla.",
      en: "High-performance static sites (Astro), no smoke: the proof is this very site, not a screenshot.",
    },
    stack: ["Astro", "Lighthouse", "SEO"],
  },
];
