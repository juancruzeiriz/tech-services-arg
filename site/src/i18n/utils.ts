import en from "./en.json";
import es from "./es.json";

export const languages = { es: "Español", en: "English" } as const;
export type Lang = keyof typeof languages;
export const defaultLang: Lang = "es";

/** Slugs traducidos por página, más allá de /[lang]/. Sin esto, alternateUrl
 * (que solo sabe reemplazar el segmento de idioma) mapearía /es/servicios/ a
 * /en/servicios/ -- una ruta que no existe, porque la versión en inglés vive
 * en /en/services/. Cada página con URL propia entra acá. */
export const routes = {
  services: { es: "servicios", en: "services" },
} as const;

const dict = { es, en } as const;

export function getLangFromUrl(url: URL): Lang {
  const [, lang] = url.pathname.split("/");
  return lang in dict ? (lang as Lang) : defaultLang;
}

function lookup(obj: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, part) => {
    if (acc !== null && typeof acc === "object" && part in acc) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, obj);
}

/**
 * Devuelve un traductor. Lanza si falta la clave: un texto faltante tiene que
 * romper el build, no llegar al sitio publicado como el nombre de la clave.
 */
export function useTranslations(lang: Lang) {
  return function t(key: string): string {
    const value = lookup(dict[lang], key);
    if (typeof value !== "string") {
      throw new Error(`i18n: falta la clave "${key}" en el idioma "${lang}"`);
    }
    return value;
  };
}

/** La URL equivalente en el otro idioma, para el switch de idioma y los
 * hreflang de Base.astro. Traduce el slug de la página (vía `routes`) además
 * del segmento de idioma -- si el slug actual no está en `routes`, lo deja
 * igual (ese es el comportamiento de siempre, para rutas sin traducir). */
export function alternateUrl(url: URL, target: Lang): string {
  const current = getLangFromUrl(url);
  const rest = url.pathname.split("/").filter(Boolean).slice(1);

  if (rest.length === 0) return `/${target}/`;

  const [slug, ...tail] = rest;
  const routeKey = (Object.keys(routes) as Array<keyof typeof routes>).find(
    (key) => routes[key][current] === slug,
  );
  const translatedSlug = routeKey ? routes[routeKey][target] : slug;

  return `/${target}/${[translatedSlug, ...tail].join("/")}/`;
}

export function otherLang(lang: Lang): Lang {
  return lang === "es" ? "en" : "es";
}
