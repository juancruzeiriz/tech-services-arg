export type ExperienceEntry = {
  id: string;
  role: { es: string; en: string };
  org: string;
  from: string; // "2024" o "2024-03"
  to: string | null; // null = presente
  bullets: { es: string[]; en: string[] };
};

// PENDIENTE DEL DUEÑO: reemplazar con la trayectoria real, transcripta del CV.
// El HTML de esta sección es lo que indexa Google (el PDF en /cv/ es solo la
// descarga) — por eso el contenido vive acá como datos, no solo en el PDF.
export const experience: ExperienceEntry[] = [
  {
    id: "placeholder",
    role: { es: "Rol — pendiente de cargar", en: "Role — pending" },
    org: "Organización — pendiente",
    from: "2024",
    to: null,
    bullets: {
      es: ["Reemplazar con logros reales del CV, uno por viñeta."],
      en: ["Replace with real achievements from the CV, one per bullet."],
    },
  },
];
