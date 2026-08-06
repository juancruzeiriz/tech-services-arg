// Captura de interés: POST /api/subscribe {email, segment}
//
// Solo INSERTA la fila -- no manda ningún mail. El envío de campañas arranca
// apagado a propósito (ver el plan de la sesión que agregó esto): esta
// Function junta interés, no dispara nada por su cuenta. Un futuro double
// opt-in real (mandar un mail de confirmación al alta) es trabajo aparte que
// necesita wirear gtm/send/ -- SMTP puro, no una API HTTP -- a algo que corra
// desde el edge o desde un cron; no está implementado todavía y no se debe
// asumir que sí.
//
// `segment` decide qué le interesa a quien se suscribe ('business_owner' vs.
// 'developer') -- útil para decidir más adelante qué mandarle a cada uno,
// una vez que ese "qué mandar" esté definido (queda abierto, ver el plan).
//
// Variables de entorno (Cloudflare Pages > Settings > Environment variables):
//   SUPABASE_URL         https://<project-ref>.supabase.co
//   SUPABASE_ANON_KEY    la anon key PÚBLICA -- la barrera real es la RLS de
//                        Postgres (gtm/store/schema/0005_subscribers.sql),
//                        que solo permite INSERT, nunca SELECT/UPDATE/DELETE.

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const VALID_SEGMENTS = new Set(["business_owner", "developer"]);

export async function onRequestPost(context) {
  const { request, env } = context;

  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: "Cuerpo inválido." }, 400);
  }

  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  const segment = typeof body.segment === "string" ? body.segment : "";
  const source = typeof body.source === "string" ? body.source.slice(0, 100) : "";

  if (!EMAIL_RE.test(email) || email.length > 254) {
    return jsonResponse({ error: "Email inválido." }, 400);
  }
  if (!VALID_SEGMENTS.has(segment)) {
    return jsonResponse({ error: "Segmento inválido." }, 400);
  }

  const supabaseUrl = env.SUPABASE_URL;
  const anonKey = env.SUPABASE_ANON_KEY;
  if (!supabaseUrl || !anonKey) {
    return jsonResponse({ error: "Servicio no disponible en este momento." }, 503);
  }

  const row = { email, segment, source: source || null };

  try {
    const response = await fetch(`${supabaseUrl}/rest/v1/subscribers`, {
      method: "POST",
      headers: {
        apikey: anonKey,
        Authorization: `Bearer ${anonKey}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal,resolution=ignore-duplicates",
      },
      body: JSON.stringify(row),
    });
    // 201 = insertada. 409/otros con ignore-duplicates: ya estaba
    // suscripta -- se trata igual como éxito para no filtrar esa
    // información al que llena el formulario.
    if (!response.ok && response.status !== 409) {
      return jsonResponse({ error: "No se pudo guardar la suscripción." }, 502);
    }
  } catch {
    return jsonResponse({ error: "No se pudo guardar la suscripción." }, 502);
  }

  return jsonResponse({ ok: true }, 200);
}

function jsonResponse(payload, status) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
