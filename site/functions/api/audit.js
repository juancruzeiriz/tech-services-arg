// Auditoría pública de un sitio: GET /api/audit?url=https://ejemplo.com
//
// Versión pública y acotada de gtm/factory/score.py + forensics.py. Solo
// implementa el subconjunto de hallazgos derivable de APIs de Google (Lighthouse
// vía PageSpeed Insights, datos de campo vía CrUX) más una comparación de
// esquema de URL -- nada que requiera descargar y parsear el HTML del sitio
// del lado nuestro. Ver gtm/factory/findings_export.py para el porqué completo
// y para cómo se generó site/src/data/audit-findings.json, la única fuente de
// verdad del texto de venta (no se reescribe acá).
//
// Esta ruta NUNCA hace fetch directo a la URL del usuario -- solo la pasa como
// parámetro a las APIs de Google, que son las que la visitan. Evita que este
// endpoint sea usable como proxy SSRF hacia direcciones internas.
//
// Variables de entorno (Cloudflare Pages > Settings > Environment variables):
//   PAGESPEED_API_KEY   Opcional -- sin ella, cuota reducida (igual que score.py).
//   CRUX_API_KEY        Opcional -- si falta, cae a PAGESPEED_API_KEY (mismo
//                        proyecto de Google Cloud habilita las dos APIs).
//
// Cachea por URL destino (evita quemar cuota de Google si dos visitantes
// prueban el mismo sitio) y aplica un cooldown best-effort por IP -- ambos
// usan la Cache API estándar de Cloudflare, no una KV: se pueden perder
// entradas bajo presión de memoria, así que esto es una mitigación, no una
// garantía dura. Un rate-limit estricto necesitaría una KV o Durable Object.

import auditFindings from "../../src/data/audit-findings.json";

const PAGESPEED_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed";
const CRUX_ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord";

const CACHE_TTL_SECONDS = 60 * 60; // 1 hora: mismo orden que la vida útil real de un audit de Lighthouse.
const RATE_LIMIT_WINDOW_MS = 15_000; // cooldown por IP entre auditorías.

// Umbrales oficiales de Core Web Vitals -- mismos valores que gtm/factory/crux.py.
const LCP_POOR_MS = 4000;
const INP_POOR_MS = 500;

export async function onRequestGet(context) {
  const { request, env } = context;
  const cache = caches.default;

  const targetUrl = new URL(request.url).searchParams.get("url");
  const validation = validateTargetUrl(targetUrl);
  if (!validation.ok) {
    return jsonResponse({ error: validation.error }, 400);
  }
  const target = validation.url;

  const ip = request.headers.get("cf-connecting-ip") || "unknown";
  const allowed = await checkRateLimit(ip, cache);
  if (!allowed) {
    return jsonResponse(
      { error: "Demasiadas solicitudes. Esperá unos segundos e intentá de nuevo." },
      429,
    );
  }

  const cacheKey = new Request(`https://audit-cache.internal/?url=${encodeURIComponent(target)}`);
  const cached = await cache.match(cacheKey);
  if (cached) {
    return cached;
  }

  let result;
  try {
    result = await runAudit(target, env);
  } catch (err) {
    return jsonResponse({ error: "No se pudo analizar el sitio. Probá de nuevo en un rato." }, 502);
  }

  const response = jsonResponse(result, 200);
  response.headers.set("Cache-Control", `public, max-age=${CACHE_TTL_SECONDS}`);
  context.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

function validateTargetUrl(raw) {
  if (!raw || typeof raw !== "string" || raw.length > 2048) {
    return { ok: false, error: "Falta el parámetro url, o es demasiado largo." };
  }
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return { ok: false, error: "La URL no es válida." };
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return { ok: false, error: "Solo se admiten URLs http o https." };
  }
  return { ok: true, url: parsed.toString() };
}

async function checkRateLimit(ip, cache) {
  const key = new Request(`https://audit-ratelimit.internal/?ip=${encodeURIComponent(ip)}`);
  const cached = await cache.match(key);
  if (cached) {
    return false; // todavía dentro de la ventana de cooldown
  }
  await cache.put(
    key,
    new Response("1", { headers: { "Cache-Control": `max-age=${Math.ceil(RATE_LIMIT_WINDOW_MS / 1000)}` } }),
  );
  return true;
}

async function runAudit(target, env) {
  const pagespeedKey = env.PAGESPEED_API_KEY;
  const cruxKey = env.CRUX_API_KEY || pagespeedKey;

  const [lighthouse, crux] = await Promise.all([
    fetchLighthouse(target, pagespeedKey),
    fetchCrux(target, cruxKey),
  ]);

  const findings = [];

  if (target.startsWith("http://")) {
    findings.push(buildFinding("no_https", target));
  }

  if (lighthouse) {
    const audits = lighthouse.audits || {};
    const viewportScore = audits.viewport?.score;
    if (viewportScore !== undefined && viewportScore !== null && viewportScore < 1) {
      findings.push(buildFinding("no_viewport", "sin meta viewport"));
    }
    if (auditFailed(audits, "tap-targets")) {
      findings.push(buildFinding("tap_targets", "botones o enlaces muy chicos o muy juntos entre sí"));
    }
    if (auditFailed(audits, "font-size")) {
      findings.push(buildFinding("tiny_font", "texto por debajo del tamaño legible en celular"));
    }
  }

  if (crux) {
    if (crux.lcpMs !== null && crux.lcpMs > LCP_POOR_MS) {
      findings.push(buildFinding("crux_lcp_poor", `${(crux.lcpMs / 1000).toFixed(1)}s`));
    }
    if (crux.inpMs !== null && crux.inpMs > INP_POOR_MS) {
      findings.push(buildFinding("crux_inp_poor", `${crux.inpMs}ms`));
    }
  }

  const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
  findings.sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);

  return {
    url: target,
    performance: categoryScore(lighthouse, "performance"),
    findings,
    checked_at: new Date().toISOString(),
  };
}

function buildFinding(code, evidence) {
  const spec = auditFindings[code];
  return {
    code,
    evidence,
    severity: spec.severity,
    sales_line_en: spec.sales_line_en.replace("{evidence}", evidence),
    sales_line_es: spec.sales_line_es.replace("{evidence}", evidence),
  };
}

function auditFailed(audits, auditId) {
  const raw = audits[auditId]?.score;
  return raw !== undefined && raw !== null && raw < 1;
}

function categoryScore(lighthouse, category) {
  const raw = lighthouse?.categories?.[category]?.score;
  return raw === undefined || raw === null ? null : Math.round(raw * 100);
}

async function fetchLighthouse(target, apiKey) {
  const params = new URLSearchParams({ url: target, strategy: "mobile" });
  params.append("category", "performance");
  params.append("category", "seo");
  params.append("category", "accessibility");
  if (apiKey) params.set("key", apiKey);

  const response = await fetch(`${PAGESPEED_ENDPOINT}?${params.toString()}`);
  if (!response.ok) {
    return null; // degrada -- no tumba el resto del análisis (igual que score.py)
  }
  const payload = await response.json();
  return payload.lighthouseResult || null;
}

async function fetchCrux(target, apiKey) {
  if (!apiKey) return null;
  for (const body of [{ url: target }, { origin: originOf(target) }]) {
    try {
      const response = await fetch(`${CRUX_ENDPOINT}?key=${encodeURIComponent(apiKey)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, formFactor: "PHONE" }),
      });
      if (response.status === 404) continue; // sin datos de campo para esa URL, probar el origen
      if (!response.ok) return null;
      const payload = await response.json();
      return parseCrux(payload);
    } catch {
      return null;
    }
  }
  return null;
}

function parseCrux(payload) {
  const metrics = payload?.record?.metrics || {};
  const lcp = metrics.largest_contentful_paint?.percentiles?.p75;
  const inp = metrics.interaction_to_next_paint?.percentiles?.p75;
  return {
    lcpMs: lcp === undefined ? null : Math.round(lcp),
    inpMs: inp === undefined ? null : Math.round(inp),
  };
}

function originOf(target) {
  const parsed = new URL(target);
  return `${parsed.protocol}//${parsed.host}`;
}

function jsonResponse(payload, status) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
