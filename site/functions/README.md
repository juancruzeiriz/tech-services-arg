# Cloudflare Pages Functions — portfolio

Dos Functions, independientes del proyecto de Cloudflare Pages de las demos
de prospección (ver `cloudflare/README.md`). Viven bajo `site/functions/`
porque el proyecto de Pages del portfolio tiene su **root directory** en
`site/` — Cloudflare detecta `functions/` como sibling de `dist/` y las
publica automáticamente al desplegar, sin config adicional.

**Estado actual: desplegado y en producción.** El proyecto de Cloudflare
Pages (`tech-services-arg.pages.dev`) se redespliega solo con cada push a
`main`; `juancruzeiriz.com` apunta ahí vía *Custom domains* (ver
`docs/PROCESOS.md`). GitHub Pages está apagado. `/api/audit` y
`/api/subscribe` responden en producción.

## `functions/api/audit.js` — GET /api/audit?url=

Versión pública y acotada de `gtm/factory/score.py`: analiza una URL con las
APIs públicas de Google (PageSpeed Insights, Chrome UX Report) y devuelve los
hallazgos derivables de ahí, con el mismo texto de venta que usa el resto del
pipeline (exportado por `gtm/factory/findings_export.py` a
`site/src/data/audit-findings.json` — **no se reescribe a mano**, se
regenera corriendo ese comando cuando cambia el texto en `findings.py`).

No implementa los hallazgos forenses (jQuery, paleta de colores, copyright
congelado, tablas de maquetación, ausencia de redes sociales): esos exigen
descargar y parsear el HTML del sitio, y portar `forensics.py` a JavaScript
lo haría divergir del original. Ver el docstring del archivo para el resto
del razonamiento (por qué nunca hace fetch directo a la URL del usuario, el
cacheo por URL, el cooldown por IP).

Variables de entorno:

| Variable | Nota |
|---|---|
| `PAGESPEED_API_KEY` | Opcional — sin ella, cuota reducida de PageSpeed |
| `CRUX_API_KEY` | Opcional — si falta, cae a `PAGESPEED_API_KEY` (mismo proyecto de Google Cloud habilita las dos APIs) |

## `functions/api/subscribe.js` — POST /api/subscribe

Inserta `{email, segment, source}` en la tabla `subscribers`
(`gtm/store/schema/0005_subscribers.sql`) vía PostgREST, con la misma
convención de RLS que `cloudflare/functions/v/[token].js` — la `anon key` es
pública por diseño, la barrera real es que la policy de Postgres solo
permite `INSERT`.

**No manda ningún mail.** Ni de confirmación ni de campaña — el envío
arranca apagado a propósito. Un double opt-in real (mail de confirmación al
alta) es trabajo aparte, todavía sin implementar: necesita wirear
`gtm/send/` (SMTP puro) a algo que corra desde el edge o desde un cron, y
está fuera del alcance de este cambio.

Variables de entorno:

| Variable | Nota |
|---|---|
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` — el origin pelado, **sin** `/rest/v1`. Un valor con `/rest/v1` ya pegado produce un 404 silencioso de PostgREST (`restBase()` en el código lo tolera, pero cargalo bien igual) |
| `SUPABASE_ANON_KEY` | la anon key **pública**, nunca la `service_role` |

**Nota sobre `Prefer` en `subscribe.js`:** el insert a `subscribers` no manda
`resolution=ignore-duplicates`, a propósito — esa preferencia genera un
`ON CONFLICT DO NOTHING`, y como la tabla solo tiene policy de `INSERT` (sin
`SELECT`), Postgres no puede resolver el conflicto y rechaza el insert entero
con `42501`, no solo con emails duplicados. Un email repetido revienta la
unicidad del índice y vuelve como 409 normal, que el código ya trata como
éxito.

## Antes del primer deploy

1. Aplicar `gtm/store/schema/0005_subscribers.sql` (`python -m gtm.store.migrate`).
2. Confirmar que la policy `subscribers_insert_only` quedó activa.
3. Correr `python -m gtm.factory.findings_export` si `findings.py` cambió
   desde la última vez y commitear el JSON actualizado.
4. Cargar las cuatro variables de entorno de arriba en el dashboard de
   Cloudflare Pages del proyecto del portfolio.
