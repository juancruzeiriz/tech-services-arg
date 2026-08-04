import { describe, expect, it } from "vitest";
import en from "./en.json";
import es from "./es.json";
import { alternateUrl, defaultLang, getLangFromUrl, languages, otherLang, useTranslations } from "./utils";

function paths(obj: unknown, prefix = ""): string[] {
  if (typeof obj !== "object" || obj === null) return [prefix];
  return Object.entries(obj).flatMap(([k, v]) => paths(v, prefix ? `${prefix}.${k}` : k));
}

describe("i18n: paridad de claves", () => {
  it("es y en tienen exactamente las mismas claves", () => {
    expect(paths(es).sort()).toEqual(paths(en).sort());
  });

  it("ninguna clave tiene valor vacío en ningún idioma", () => {
    for (const [lang, dict] of Object.entries({ es, en })) {
      for (const path of paths(dict)) {
        const value = path.split(".").reduce<unknown>((acc, part) => (acc as Record<string, unknown>)?.[part], dict);
        expect(typeof value === "string" && value.trim().length > 0, `${lang}.${path} está vacío`).toBe(true);
      }
    }
  });
});

describe("useTranslations", () => {
  it("resuelve claves anidadas", () => {
    const t = useTranslations("es");
    expect(t("nav.work")).toBe("Proyectos");
  });

  it("lanza si la clave no existe, en vez de devolver undefined silenciosamente", () => {
    const t = useTranslations("es");
    expect(() => t("nav.no_existe")).toThrow(/falta la clave/);
  });

  it("EN y ES devuelven textos distintos para la misma clave", () => {
    const tEs = useTranslations("es");
    const tEn = useTranslations("en");
    expect(tEs("hero.line1")).not.toBe(tEn("hero.line1"));
  });
});

describe("getLangFromUrl", () => {
  it("reconoce /es/ y /en/", () => {
    expect(getLangFromUrl(new URL("https://x.dev/es/"))).toBe("es");
    expect(getLangFromUrl(new URL("https://x.dev/en/work"))).toBe("en");
  });

  it("cae al idioma por defecto si el path no tiene prefijo de idioma válido", () => {
    expect(getLangFromUrl(new URL("https://x.dev/"))).toBe(defaultLang);
    expect(getLangFromUrl(new URL("https://x.dev/algo-random"))).toBe(defaultLang);
  });
});

describe("alternateUrl", () => {
  it("reemplaza el segmento de idioma preservando el resto del path", () => {
    expect(alternateUrl(new URL("https://x.dev/es/work"), "en")).toBe("/en/work/");
  });

  it("siempre termina en barra", () => {
    expect(alternateUrl(new URL("https://x.dev/es"), "en")).toBe("/en/");
  });
});

describe("otherLang / languages", () => {
  it("es <-> en son inversos", () => {
    expect(otherLang("es")).toBe("en");
    expect(otherLang("en")).toBe("es");
  });

  it("expone las dos etiquetas de idioma", () => {
    expect(Object.keys(languages).sort()).toEqual(["en", "es"]);
  });
});
