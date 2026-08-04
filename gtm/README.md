# GTM — Fábrica de demos para SMBs de USA

Pipeline que fabrica artefactos de prospección personalizados a costo marginal ~0.

## Por qué existe

Un negocio de servicios sin marca tiene un problema de **confianza**, no de capacidad.
El cuello de botella no es ejecutar el trabajo: es que nadie contrata a un desconocido.

### Qué se descartó y por qué

La alternativa evaluada era validar la demanda con anuncios pagos: publicar N servicios,
medir clics, quedarse con el ganador. Se descartó por aritmética, no por criterio.

| Variable | Valor |
|---|---|
| CPC promedio B2B (AR, 2026) | ~USD 5,70 |
| Presupuesto disponible | USD 200 |
| Clics comprables | ~35 |
| Repartidos en 5 anuncios | **7 por brazo** |
| Conversión landing→lead típica | 2-5% |
| Leads esperados por brazo | **0** |

Un experimento cuyo resultado esperado es cero en todos los brazos no distingue la
hipótesis buena de la mala: no puede acertar ni fallar. Para llegar a n≈10 leads por
brazo harían falta USD 500-1.000 **por servicio**.

Hay tres razones más, independientes del presupuesto:

- **El clic mide el copy, no la disposición a pagar.** Su correlación con ingreso es débil.
- **Google Search solo captura demanda ya articulada.** Nadie googlea "automatización con
  IA para mi PyME", así que da falso negativo sistemático justo en las ideas de mayor margen.
- **Elegir por demanda sola contradice el requisito de mantenibilidad.** "Alta demanda" y
  "fácil de mantener" suelen ser opuestos.

### El reencuadre

Si sobra capacidad de producción y falta confianza, hay que **entregar el trabajo antes de
la transacción**. El artefacto reemplaza a la marca: no lo pediste, ya está hecho, está
online, acá está el link. El prospecto no tiene que creerte nada — lo abre y lo ve.

Eso solo es viable si producir el artefacto es casi gratis. Por eso la automatización va
acá, en la prospección — y no en la entrega, que es donde instintivamente uno la querría
poner.

Y define qué se puede vender: la oferta tiene que ser **construible sin permiso, sobre
información pública**. Eso descarta las auditorías (CI/CD, costos cloud, OIDC), que
requieren credenciales del cliente y por lo tanto no admiten hacer el trabajo primero.

En vez de clics, la métrica es una **escalera de compromiso** — clic (ruido) → responde →
agenda llamada → acepta propuesta → **paga**. Cada escalón le cuesta más al prospecto y
por eso vale más como evidencia. El umbral de decisión está pre-registrado en
[`decision_criteria.yaml`](decision_criteria.yaml) y no se modifica durante el experimento.

## Pipeline

```
discover  →  score  →  generate  →  deploy  →  outreach  →  contact
 Places      Lighthouse   HTML       URL viva    mensaje     cola de trabajo
```

| Etapa | Qué hace | Salida |
|---|---|---|
| `discover` | Google Places API, filtrado por demanda probada y web pobre | `prospects.json` |
| `score` | PageSpeed Insights → pain score 0-100 (async) | `scores.json` |
| `generate` | Renderiza la demo con datos reales del negocio | `build/demos/<slug>/` |
| `deploy` | Arma el directorio publicable con URL única por demo | `public/` |
| `outreach` | Email validado contra CAN-SPAM | `emails.json` |
| `contact` | Resuelve canal por prospecto y arma la cola (async) | `queue.md` |
| `ledger` | Supresión y embudo, persistentes entre corridas | `suppression.jsonl`, `funnel.jsonl` |

Cada etapa es idempotente y se identifica por `place_id`. Re-correrla no duplica nada.

## Uso

```bash
export PYTHONPATH=$(pwd)

python -m gtm.factory.discover --vertical plumber --metro "Tucson, AZ" --limit 20
python -m gtm.factory.score
python -m gtm.factory.generate --all
python -m gtm.factory.deploy --dry-run     # revisar URLs antes de publicar
python -m gtm.factory.deploy
python -m gtm.factory.outreach
python -m gtm.factory.contact --queue      # cola de trabajo ordenada por dolor

# Durante la operación
python -m gtm.factory.ledger record --place-id ChIJ... --event replied
python -m gtm.factory.ledger suppress --place-id ChIJ... --reason opted_out
python -m gtm.factory.ledger report --spend 150

wrangler pages deploy gtm/public           # publicar
```

Sin credenciales de Places, se puede correr todo desde la etapa 3 con el fixture:

```bash
python -m gtm.factory.generate --all --input gtm/examples/prospects.sample.json \
  --author-name "Tu Nombre" --author-url "https://tusitio.com"
python -m gtm.factory.deploy --base-url "https://demos.tusitio.com" --dry-run
```

## UI

```bash
python -m gtm.ui                    # abre http://127.0.0.1:8787
python -m gtm.ui --port 9000 --no-browser --reload
```

Corre el mismo pipeline que la CLI (`gtm/factory/pipeline.py` llama a las mismas
funciones puras que usan los 8 `main()`, no las reimplementa) detrás de un
formulario con todos los parámetros, en vez de pasarlos a mano por `argparse`
corrida por corrida. Bind fijo a `127.0.0.1`: el proceso guarda credenciales en
memoria y no tiene capa de autenticación, así que exponerlo a la red tiene que
ser una decisión explícita de quien lo corre, nunca el default.

| Ruta | Qué hace |
|---|---|
| `/` | Formulario de corrida (los ~15 parámetros del pipeline) + presets guardados |
| `/runs`, `/runs/{id}` | Lista y detalle de corridas, con progreso en vivo por SSE |
| `/queue` | Cola de contacto: guion listo para copiar, un clic por evento del embudo |
| `/dashboard/funnel` | Embudo contra `decision_criteria.yaml`, con intervalos de Wilson y proyección de horas del corte temprano por costo |
| `/dashboard/economics` | USD/hora efectivo, CAC, cohortes (oficio×metro×idioma), correlación dolor↔conversión |
| `/settings` | Estado del entorno (qué falta por variable) + carga de costos |

El ledger local (`funnel.jsonl`, `suppression.jsonl`) sigue siendo la fuente de
verdad — se escribe siempre, primero. Postgres es un store analítico opcional:
sin `SUPABASE_DB_URL`, o si la escritura falla, lo que no se pudo guardar queda
en `gtm/build/outbox.jsonl` y se reintenta con `python -m gtm.store.backfill`.
La UI nunca falla por esto — se degrada, no se rompe.

## Configuración

En `.env.personal` (raíz del repo). Ninguna de estas variables va al código.

| Variable | Etapa | Obligatoria |
|---|---|---|
| `GOOGLE_PLACES_API_KEY` | discover | sí |
| `PAGESPEED_API_KEY` | score | no (sin key hay cuota menor) |
| `GTM_FROM_NAME` | generate, outreach | sí |
| `GTM_FROM_EMAIL` | outreach | sí |
| `GTM_PHYSICAL_ADDRESS` | outreach | sí — CAN-SPAM |
| `GTM_UNSUBSCRIBE_URL` | outreach | sí — CAN-SPAM |
| `GTM_DEMO_BASE_URL` | deploy, UI | sí |
| `SUPABASE_DB_URL` | UI, store, backfill | no — sin ella, degrada al outbox local |

## Reglas que el código hace cumplir

No son convenciones: están implementadas y testeadas, porque son las que se rompen
solas cuando uno tiene apuro por enviar.

**El pipeline no inventa hechos sobre el prospecto.** El gancho de la llamada perdida
solo se renderiza si se registró una observación real (`missed_call_at`). Si no existe,
el email cae al ángulo medido por Lighthouse, que el prospecto puede verificar por su
cuenta en pagespeed.web.dev. Un dato inventado se descubre en la primera llamada.

**La demo se marca como preview de terceros y sale con `noindex`.** No puede confundirse
con el sitio oficial del negocio ni competirle en buscadores. El negocio no pidió estar
acá; el artefacto es un regalo, no una suplantación.

**Un mockup no es prueba de trabajo.** `outreach` rechaza cualquier demo sin URL pública.
El adjunto que no abre en el teléfono es exactamente el pitch que el prospecto ya
descartó veinte veces.

**Todo email cumple CAN-SPAM antes de existir.** Dirección postal física, mecanismo de
baja, identificación como comunicación comercial y asunto no engañoso. Se valida al
construir el objeto, no al enviar: las multas se cuentan por mensaje.

```bash
pytest tests/gtm/test_outreach.py -k canspam   # correr antes de cualquier envío
```

**El pipeline prepara, no envía.** A 25 prospectos por semana mandar a mano cuesta
hora y media, convierte más y evita de raíz los dos riesgos legales del envío
automatizado. `contact` deja una cola en Markdown ordenada por dolor, con el canal
resuelto y el mensaje listo para copiar.

**No existe un canal de email scrapeado, y es deliberado.** Recolectar direcciones de
forma automatizada desde sitios web es una *aggravated violation* de CAN-SPAM —agrava
las multas en vez de solo aplicarlas— y además falla justo con los mejores prospectos,
que son los que no tienen sitio del cual scrapear nada. Tampoco hay SMS en frío: el TCPA
exige consentimiento previo expreso por escrito, con multas de USD 500-1.500 por mensaje.
Quedan dos canales: teléfono para los de mayor dolor, formulario propio para el resto.

**La supresión persiste, pero sin datos personales.** `suppression.jsonl` y
`funnel.jsonl` **sí** van a git —si se pierden, le volvés a escribir a quien pidió que
no— pero guardan solo hashes SHA-256 de identificadores normalizados. Alcanzan para
responder "¿a este ya lo contacté?" sin almacenar a quién. El chequeo cruza place_id,
teléfono y dominio, porque Google reemite place_ids y el mismo negocio reaparece con
otro ID pero el mismo teléfono.

**El criterio pre-registrado es verificable, no decorativo.** `tests/gtm/test_ledger_criteria.py`
lee `decision_criteria.yaml` y falla si el código implementa umbrales distintos. Sin eso,
nada impediría mover el umbral después de ver los datos — que es el sesgo exacto que el
pre-registro existe para bloquear. Si ese test falla, la pregunta no es cómo arreglarlo
sino por qué cambió el criterio a mitad del experimento.

**Las etapas de red van en paralelo, con techo.** `score` y `contact` hacen N llamadas
independientes y en serie tardaban minutos de espera pura: Lighthouse son 30-60s por
sitio, así que 50 prospectos eran 25-50 minutos. Ahora comparten un cliente async —reusar
conexiones es buena parte de la mejora, no solo la concurrencia— con un semáforo que
regula el ritmo. El techo no es opcional: soltar 50 requests de golpe contra PageSpeed
garantiza 429s, y el backoff posterior sale más caro que haber ido de a cinco desde el
principio. Se ajusta con `--concurrency`.

**Los datos de prospectos no entran a git.** `gtm/build/` y `gtm/public/` están en
`.gitignore`. Son datos de contacto de negocios reales; el historial de un repo es
permanente.

## Documentos

- [`pipeline.md`](pipeline.md) — precios, guion de venta, secuencia y contrato
- [`decision_criteria.yaml`](decision_criteria.yaml) — criterio de kill pre-registrado
- [`validation.md`](validation.md) — investigación de mercado externa: qué tan real es el
  problema, quién más cobra por esto, objeciones documentadas, qué NO está en la oferta
- [`plan_aprendizaje.md`](plan_aprendizaje.md) — plan semanal de aprendizaje + simulación +
  ejecución para quien arranca sin conocer el terreno
- [`offers/`](offers/) — one-pagers de oferta, en inglés
