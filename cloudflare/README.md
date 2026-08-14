# Cloudflare Pages — deploy

Dos proyectos de Cloudflare Pages **separados y sin relación entre sí** —
mismo motivo que `.env.example` documenta para usar un dominio de envío
distinto al del portfolio: si algo sale mal en uno (cuota agotada, un bug),
no tiene que poder afectar al otro.

| Proyecto | Sirve | Functions |
|---|---|---|
| Demos de prospección | `gtm/public/` (generado por `gtm/factory/deploy.py`) | `cloudflare/functions/` — descrito abajo |
| Portfolio (`juancruzeiriz.com`) | `site/dist/` (generado por `astro build`) | `site/functions/` — ver `site/functions/README.md` |

El portfolio ya está migrado a Cloudflare Pages (`tech-services-arg.pages.dev`,
redeploy automático con cada push a `main`); `site/functions/` sirve de
verdad y `/api/audit`, `/api/subscribe` responden en producción. El dominio
propio (`juancruzeiriz.com`) apunta a Cloudflare vía *Custom domains* del
proyecto — ver `docs/PROCESOS.md` para el estado del DNS. `.github/workflows/`
ya no tiene ningún workflow de deploy (GitHub Pages se apagó).

## Demos de prospección

`gtm/factory/deploy.py` publica el contenido estático de las demos en
`gtm/public/`. Este directorio (`cloudflare/`) es lo que se agrega arriba de
eso al desplegar con Cloudflare Pages: la Function de tracking de aperturas.

```bash
# El primer comando no es opcional: Wrangler dejó de compilar functions/ solo
# dentro de `pages deploy` en versiones recientes. Sin este paso, la Function de
# tracking (y la de unsubscribe, ver site/functions/README.md) quedan rotas en
# producción sin ningún error -- toda ruta cae a la página estática de índice.
# gtm/factory/deploy.py::_copy_functions arma functions/ desde acá y desde
# site/functions/api/unsubscribe.js en cada corrida de `deploy`.
wrangler pages functions build gtm/public/functions \
    --outdir=gtm/public/_worker.js --build-output-directory=gtm/public
wrangler pages deploy gtm/public --project-name=<nombre-del-proyecto>
```

`functions/v/[token].js` resuelve un link de redirección (`/v/{token}`) contra
la tabla `demo_links`, registra la apertura en `demo_views`, y redirige (302) a
la demo real. Ver el comentario al inicio del archivo para el detalle completo.

### Variables de entorno del proyecto de Pages

En el dashboard de Cloudflare Pages del proyecto, **Settings → Environment
variables**:

| Variable | Valor | Nota |
|---|---|---|
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` | El origin pelado, **sin** `/rest/v1` — la Function lo concatena ella misma. Un valor con `/rest/v1` ya pegado (fácil de copiar así del dashboard de Supabase) produce un 404 silencioso; `restBase()` en el código lo tolera igual, pero no vale la pena depender de eso |
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
