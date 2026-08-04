export type Certification = {
  id: string;
  issuer: string;
  name: { es: string; en: string };
  year: number;
  /** Imagen del badge bajada del perfil público de Credly a public/badges/. */
  badge: string;
  /** URL pública de verificación de esa credencial en Credly. */
  verifyUrl: string;
};

// PENDIENTE DEL DUEÑO: reemplazar cada entrada con las certificaciones reales.
// Pasos para cada una:
//   1. Entrar a tu perfil público de Credly (credly.com/users/<usuario>).
//   2. Bajar la imagen del badge y guardarla en site/public/badges/<archivo>.png
//   3. Copiar la URL pública de verificación de esa credencial ("Ver credencial").
//   4. Reemplazar el placeholder correspondiente acá abajo.
// No se muestra ninguna certificación sin su link de verificación: un logo
// suelto sin prueba es peor que no mostrar nada.
export const certifications: Certification[] = [
  {
    id: "google-placeholder",
    issuer: "Google",
    name: { es: "Certificación de Google — pendiente de cargar", en: "Google Certificate — pending" },
    year: new Date().getFullYear(),
    badge: "/badges/placeholder-google.svg",
    verifyUrl: "https://www.credly.com/users/PENDIENTE",
  },
  {
    id: "cisco-placeholder",
    issuer: "Cisco",
    name: { es: "Certificación de Cisco — pendiente de cargar", en: "Cisco Certificate — pending" },
    year: new Date().getFullYear(),
    badge: "/badges/placeholder-cisco.svg",
    verifyUrl: "https://www.credly.com/users/PENDIENTE",
  },
];
