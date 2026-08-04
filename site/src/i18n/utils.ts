import en from "./en.json";
import es from "./es.json";

export const languages = { es: "Español", en: "English" } as const;
export type Lang = keyof typeof languages;
export const defaultLang: Lang = "es";

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

/** La URL equivalente en el otro idioma, para el switch de idioma. */
export function alternateUrl(url: URL, target: Lang): string {
  const parts = url.pathname.split("/");
  parts[1] = target;
  const joined = parts.join("/");
  return joined.endsWith("/") ? joined : `${joined}/`;
}

export function otherLang(lang: Lang): Lang {
  return lang === "es" ? "en" : "es";
}
