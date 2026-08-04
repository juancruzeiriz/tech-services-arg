// Redirección con tracking de apertura de demo.
//
// El link que efectivamente se manda al prospecto (email, formulario, SMS) es
// {base_url}/v/{token} -- nunca la URL directa de la demo. Este worker resuelve
// el token contra la tabla `demo_links` (Postgres/Supabase, vía PostgREST),
// registra la apertura en `demo_views`, y redirige (302) a la demo real.
//
// Por qué así y no un beacon en el HTML de la demo: la demo tiene que seguir
// haciendo CERO requests externos -- es el argumento de venta y está
// verificado por tests/gtm/test_generate.py::test_no_hace_requests_externas.
// Un pixel de tracking en la página lo rompería. Acá el tracking pasa por la
// URL que se envía, antes de que el prospecto llegue a ver el HTML.
//
// Variables de entorno (Cloudflare Pages > Settings > Environment variables):
//   SUPABASE_URL         https://<project-ref>.supabase.co
//   SUPABASE_ANON_KEY    la anon key PÚBLICA del proyecto -- nunca la
//                        service_role key: esto corre en el edge, visible
//                        para cualquiera que inspeccione el tráfico.
//
// La anon key por sí sola no alcanza como barrera de seguridad: lo que
// realmente limita qué puede hacer es la Row Level Security de Postgres
// (ver gtm/store/schema/0002_demo_views_rls.sql) -- solo puede INSERTAR en
// demo_views y solo puede LEER demo_links, nada más.

export async function onRequestGet(context) {
  const { params, request, env } = context;
  const token = params.token;

  if (!token || typeof token !== "string") {
    return new Response("Not found", { status: 404 });
  }

  const supabaseUrl = env.SUPABASE_URL;
  const anonKey = env.SUPABASE_ANON_KEY;
  if (!supabaseUrl || !anonKey) {
    // Sin config no se puede resolver el token, pero un error de configuración
    // nuestro no tiene que tumbar la request del prospecto con un 500 feo.
    return new Response("Service unavailable", { status: 503 });
  }

  const link = await lookupLink(supabaseUrl, anonKey, token);
  if (!link) {
    return new Response("Not found", { status: 404 });
  }

  // No se espera a que termine de escribir la vista antes de redirigir: el
  // prospecto no tiene que notar el tracking en la latencia del click.
  context.waitUntil(recordView(supabaseUrl, anonKey, token, link, request));

  const destination = new URL(`/${link.demo_slug}/`, request.url);
  return Response.redirect(destination.toString(), 302);
}

async function lookupLink(supabaseUrl, anonKey, token) {
  const url = `${supabaseUrl}/rest/v1/demo_links?token=eq.${encodeURIComponent(token)}&select=demo_slug,place_id`;
  const response = await fetch(url, {
    headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` },
  });
  if (!response.ok) {
    return null;
  }
  const rows = await response.json();
  return rows[0] || null;
}

async function recordView(supabaseUrl, anonKey, token, link, request) {
  const userAgent = request.headers.get("user-agent") || "";
  const referer = request.headers.get("referer") || "";
  const ip = request.headers.get("cf-connecting-ip") || "";

  const row = {
    client_id: crypto.randomUUID(),
    token,
    demo_slug: link.demo_slug,
    place_id: link.place_id,
    at: new Date().toISOString(),
    // Se guarda el hash, no la IP: alcanza para des-duplicar sin quedarse con
    // un dato personal que no hace falta.
    ip_hash: ip ? await sha256Hex(ip) : null,
    user_agent: userAgent.slice(0, 500),
    referer: referer.slice(0, 500),
    is_probable_bot: looksLikeBot(userAgent),
  };

  try {
    await fetch(`${supabaseUrl}/rest/v1/demo_views`, {
      method: "POST",
      headers: {
        apikey: anonKey,
        Authorization: `Bearer ${anonKey}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify(row),
    });
  } catch (_err) {
    // Un fallo acá no debe afectar al prospecto -- ya se lo redirigió. Se
    // pierde una vista, no se rompe el link.
  }
}

function looksLikeBot(userAgent) {
  // Heurística, no autoritativa: filtra los rastreadores obvios (previews de
  // link de Slack/Facebook/Twitter, curl, bots de indexación) para que el
  // conteo de aperturas no se infle con tráfico que no es un humano mirando
  // el link. No reemplaza un chequeo serio de bot management.
  const needle = userAgent.toLowerCase();
  return [
    "bot", "spider", "crawler", "curl", "wget", "facebookexternalhit",
    "slackbot", "twitterbot", "whatsapp", "telegrambot", "linkedinbot",
    "discordbot", "preview",
  ].some((marker) => needle.includes(marker));
}

async function sha256Hex(value) {
  const data = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
