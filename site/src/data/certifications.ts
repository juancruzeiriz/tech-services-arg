export type Certification = {
  id: string;
  issuer: string;
  /** 2-4 letras para el sello circular — no hay badges de Credly acá, así que
   * no se reproduce ningún logo de marca ajena; es un sello propio. */
  mark: string;
  name: { es: string; en: string };
  year: number;
  hours?: number;
  /** URL pública de verificación, o ruta a la constancia hosteada en
   * public/certs/ (solo para constancias sin datos personales sensibles).
   * `null` cuando no hay verificación pública disponible -- no se muestra un
   * link falso. */
  verifyUrl: string | null;
};

// Certificados reales, transcriptos de los PDF que el dueño pasó. Dos de los
// PDF originales (Certificado webmaster.pdf, Certificado CIBERSEGURIDAD...)
// tienen el DNI impreso en el propio documento -- por eso NO se hostean acá,
// a diferencia de la constancia de CCNA (sin datos personales sensibles, sí
// hosteada en public/certs/).
export const certifications: Certification[] = [
  {
    id: "coursera-python-i",
    issuer: "Coursera — Pontificia Universidad Católica de Chile",
    mark: "PY",
    name: {
      es: "Introducción a la programación en Python I",
      en: "Introduction to Programming in Python I",
    },
    year: 2020,
    verifyUrl: "https://coursera.org/verify/W9F3WC9DE5G8",
  },
  {
    id: "coursera-speak-english",
    issuer: "Coursera — Georgia Institute of Technology",
    mark: "EN",
    name: {
      es: "Speak English Professionally: In Person, Online & On the Phone",
      en: "Speak English Professionally: In Person, Online & On the Phone",
    },
    year: 2020,
    verifyUrl: "https://coursera.org/verify/A3CG29ETZVXR",
  },
  {
    id: "utn-webmaster",
    issuer: "UTN — Facultad Regional Buenos Aires",
    mark: "UTN",
    name: { es: "Professional Webmaster", en: "Professional Webmaster" },
    year: 2016,
    hours: 144,
    // Portal de validación con código manual (CER--23062), no un deep-link
    // directo -- se linkea el portal en sí, no el PDF (que trae el DNI impreso).
    verifyUrl: "https://sysgestion.frba.utn.edu.ar/alumnos/validar_certificado",
  },
  {
    id: "cisco-ccna-1",
    issuer: "Cisco Networking Academy — Fundación Proydesa / UTN",
    mark: "CI",
    name: {
      es: "CCNA 1 R&S: Introduction to Networks",
      en: "CCNA 1 R&S: Introduction to Networks",
    },
    year: 2016,
    verifyUrl: "/certs/ccna-cisco-networking-academy.pdf",
  },
  {
    id: "telefonica-ciberseguridad",
    issuer: "Fundación Telefónica Movistar — Conecta Empleo",
    mark: "SEC",
    name: { es: "Curso Ciberseguridad", en: "Cybersecurity Course" },
    year: 2019,
    hours: 200,
    // Sin portal de verificación pública, y el PDF original trae el DNI
    // impreso -- no se hostea. Constancia disponible a pedido.
    verifyUrl: null,
  },
];
