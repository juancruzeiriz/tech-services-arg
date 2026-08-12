// Mecanismo de baja de CAN-SPAM: GET sirve una página con un formulario de
// email, POST procesa el alta en `unsubscribes`.
//
// Por qué un formulario y no un link de un solo clic con token: el link que va
// en el cuerpo del email (`SenderIdentity.unsubscribe_url`, ver
// gtm/factory/config.py::load_sender_identity) es UNA URL fija para todos los
// envíos -- `outreach.py` no genera un token por email enviado. Sin token no
// hay forma de saber, solo con el clic, a qué dirección llegó ese mensaje. Pedir
// el email en la página sigue cumpliendo CAN-SPAM (la ley exige un mecanismo
// funcional de baja, no específicamente un link de un clic sin fricción) y no
// requiere tocar la etapa de generación de emails para agregar tokens.
//
// Variables de entorno (Cloudflare Pages > Settings > Environment variables),
// mismo par que subscribe.js y v/[token].js:
//   SUPABASE_URL         https://<project-ref>.supabase.co -- origin pelado.
//   SUPABASE_ANON_KEY    anon key pública -- la barrera real es la RLS de
//                        gtm/store/schema/0007_unsubscribes.sql (solo INSERT).
//
// `gtm/factory/ledger.py sync-unsubscribes` (con SUPABASE_DB_URL, no la anon
// key) es lo único que lee de esta tabla y vuelca cada baja a la lista de
// supresión local (`gtm/suppression.jsonl`), que es la que de verdad filtra a
// quién no se vuelve a contactar.

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export async function onRequestGet(context) {
  return new Response(renderForm(), {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

export async function onRequestPost(context) {
  const { request, env } = context;

  const contentType = request.headers.get("content-type") || "";
  let email = "";
  try {
    if (contentType.includes("application/json")) {
      const body = await request.json();
      email = typeof body.email === "string" ? body.email : "";
    } else {
      const form = await request.formData();
      email = String(form.get("email") || "");
    }
  } catch {
    return htmlResponse(renderForm("No pudimos leer el formulario. Probá de nuevo."), 400);
  }

  email = email.trim().toLowerCase();
  if (!EMAIL_RE.test(email) || email.length > 254) {
    return htmlResponse(renderForm("Ese email no parece válido."), 400);
  }

  const supabaseUrl = restBase(env.SUPABASE_URL);
  const anonKey = env.SUPABASE_ANON_KEY;
  if (!supabaseUrl || !anonKey) {
    return htmlResponse(renderForm("Servicio no disponible en este momento. Escribinos directamente para darte de baja."), 503);
  }

  const row = { email, source: "unsubscribe_page" };

  try {
    const response = await fetch(`${supabaseUrl}/rest/v1/unsubscribes`, {
      method: "POST",
      headers: {
        apikey: anonKey,
        Authorization: `Bearer ${anonKey}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify(row),
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      console.error("unsubscribe: PostgREST rechazó el insert", response.status, detail);
      return htmlResponse(renderForm("No se pudo procesar la baja. Escribinos directamente."), 502);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("unsubscribe: fetch a Supabase falló", message);
    return htmlResponse(renderForm("No se pudo procesar la baja. Escribinos directamente."), 502);
  }

  return htmlResponse(renderConfirmation(email), 200);
}

function restBase(rawUrl) {
  if (!rawUrl) return null;
  try {
    const url = new URL(rawUrl);
    return `${url.protocol}//${url.host}`;
  } catch {
    return null;
  }
}

function htmlResponse(html, status) {
  return new Response(html, {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

function renderForm(error) {
  const errorHtml = error ? `<p style="color:#b00020">${escapeHtml(error)}</p>` : "";
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Unsubscribe</title>
</head>
<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem;">
<h1>Unsubscribe</h1>
<p>Enter the email address the message was sent to. You will not hear from us again after this.</p>
${errorHtml}
<form method="POST" action="/api/unsubscribe">
  <input type="email" name="email" required placeholder="you@example.com"
         style="width:100%;padding:0.5rem;font-size:1rem;box-sizing:border-box;">
  <button type="submit" style="margin-top:0.75rem;padding:0.5rem 1.25rem;font-size:1rem;">Unsubscribe</button>
</form>
</body>
</html>`;
}

function renderConfirmation(email) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Unsubscribed</title>
</head>
<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem;">
<h1>You're unsubscribed</h1>
<p>${escapeHtml(email)} will not receive any further messages. This can take up to 10 business days to
fully process, as required by CAN-SPAM.</p>
</body>
</html>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
