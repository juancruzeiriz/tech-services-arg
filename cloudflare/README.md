# Cloudflare Pages — deploy

Dos proyectos de Cloudflare Pages **separados y sin relación entre sí** —
mismo motivo que `.env.example` documenta para usar un dominio de envío
distinto al del portfolio: si algo sale mal en uno (cuota agotada, un bug),
no tiene que poder afectar al otro.

| Proyecto | Sirve | Functions |
|---|---|---|
| Demos de prospección | `gtm/public/` (generado por `gtm/factory/deploy.py`) | `cloudflare/functions/` — descrito abajo |
| Portfolio (`juancruzeiriz.com`) | `site/dist/` (generado por `astro build`) | `site/functions/` — ver `site/functions/README.md` |

El portfolio **todavía se sirve desde GitHub Pages** (`.github/workflows/site.yml`,
estático puro). Migrar ese proyecto a Cloudflare Pages es un paso manual
pendiente -- crear el proyecto en el dashboard de Cloudflare, apuntar el
root directory a `site/`, mover el DNS, y recién ahí `site/functions/`
empieza a servir de verdad. Hasta que eso pase, `/api/audit` y
`/api/subscribe` existen como código pero no están desplegados en ningún
lado.

## Demos de prospección

`gtm/factory/deploy.py` publica el contenido estático de las demos en
`gtm/public/`. Este directorio (`cloudflare/`) es lo que se agrega arriba de
eso al desplegar con Cloudflare Pages: la Function de tracking de aperturas.

```bash
wrangler pages deploy gtm/public
```

`functions/v/[token].js` resuelve un link de redirección (`/v/{token}`) contra
la tabla `demo_links`, registra la apertura en `demo_views`, y redirige (302) a
la demo real. Ver el comentario al inicio del archivo para el detalle completo.

### Variables de entorno del proyecto de Pages

En el dashboard de Cloudflare Pages del proyecto, **Settings → Environment
variables**:

| Variable | Valor | Nota |
|---|---|---|
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` | El REST endpoint del proyecto |
| `SUPABASE_ANON_KEY` | la anon key **pública** | Nunca la `service_role` key acá — esto corre en el edge, visible para cualquiera |

### Antes del primer deploy

1. Aplicar las migraciones de `gtm/store/schema/` contra el proyecto de
   Supabase (`python -m gtm.store.migrate`), **incluida** `0002_demo_views_rls.sql`
   — sin esa migración, la Function no tiene permiso de insertar ni de leer,
   y todo termina en 404/503.
2. Confirmar que las policies de RLS quedaron activas: `demo_views` solo
   admite `INSERT` con la `anon` key, `demo_links` solo admite `SELECT`.

## Portfolio (juancruzeiriz.com)

Ver `site/functions/README.md` para el detalle de `/api/audit` y
`/api/subscribe`, sus variables de entorno propias, y las migraciones que
necesitan aplicadas antes del primer deploy (**incluida**
`0005_subscribers.sql`).
