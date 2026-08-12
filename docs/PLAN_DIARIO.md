# Plan diario — 20 sesiones de 30-60 min

Se lee junto a [`docs/PROCESOS.md`](PROCESOS.md). Corre **antes y en paralelo** de
[`gtm/plan_aprendizaje.md`](../gtm/plan_aprendizaje.md) — lo complementa, no lo reemplaza: ese
plan cubre inmersión de mercado (foros, entrevistas de problema) y calibración de guion; este
plan cubre entender y debuggear el mecanismo del pipeline mismo, nodo por nodo.

**No arranca el experimento pre-registrado.** Los 200 contactos reales de
[`decision_criteria.yaml`](../gtm/decision_criteria.yaml) empiezan después del día 20. Cambiar
el guion o el criterio a mitad del experimento es exactamente lo que ese archivo existe para
bloquear — así que toda la iteración tiene que pasar antes del primer contacto real.

## Ritual de cada sesión

1. **5 min** — releer la ficha del nodo de hoy en `PROCESOS.md`.
2. **20-40 min** — el ejercicio del día. Uno solo. Si no entra en el tiempo, se corta y se anota
   dónde se quedó — no se estira la sesión.
3. **5-10 min** — escribir el hallazgo en la ficha del nodo (Problemas conocidos / Bitácora) y
   tildar el día acá abajo.

**Regla dura de la Fase B**: todo hallazgo se escribe como *hipótesis falsable + medición
barata*, nunca como opinión suelta. Ejemplo: no "el corte de 45 deja pasar sitios que están
bien", sino "de 10 sitios que el score califica, yo a mano descarto N — si N≥4 el corte está mal
calibrado".

---

## Fase A — El QUÉ (días 1-8): entender antes de opinar

- [x] **Día 1** (60 min, setup) — Commit+push del incremento pendiente del sitio. Confirmar que
  `docs/PROCESOS.md` está creado con los 3 diagramas y las 14 fichas. Publicar el Artifact
  navegable. *Salida: el mapa existe y se puede mirar desde el celular.*

- [x] **Día 2** (2026-08-05, Nodo 0) — Auditoría real de juancruzeiriz.com. Encontró y resolvió
  un bug de layout (chips rotos en `/servicios/`), un bug de accesibilidad (reduced-motion
  apagaba todo el movimiento, no solo lo vestibular) y un problema de diseño (el movimiento
  activo era imperceptible). Sumó loader de intro, tercer tema, transiciones SPA, parallax de
  mouse y contadores animados. Detalle completo en la ficha del Nodo 0 en `PROCESOS.md`. El gap
  del nav mobile mencionado en la sesión anterior ("<860px sin hamburguesa") resultó estar
  desactualizado: `Nav.astro` ya tiene un botón hamburguesa con popover nativo, verificado en
  vivo a 375px (aparece, oculta los links de escritorio, funciona). No había nada que arreglar
  ahí.

- [x] **Día 3** (2026-08-11, Nodo 1) — Reconstruidas a mano las dos fórmulas de `rank`.
  Encontrada y corregida una discrepancia real: `pool_service`, `appliance_repair` y
  `locksmith` tenían el rank invertido respecto a la fórmula documentada (fix en
  `600182d`). Los 20 metros sí cumplían la fórmula exacta. Hallazgo de la fórmula de
  metros: Houston y Phoenix quedan casi empatados (690k vs 675k) — la distancia entre
  #1 y #2 depende enteramente del multiplicador 1.5 de `mini_tcpa_risk`, un número
  fijado a mano. **Par elegido, con datos reales de un barrido de 539 negocios (15
  oficios × 20 metros vía Places API), no del ranking original del catálogo:
  `tree_service` (poda y tala de árboles) × Albuquerque, NM** — justificación completa
  en la ficha del Nodo 1 en `PROCESOS.md`. Los oficios de mayor ticket del ranking
  original (roofer, hvac, plumber) resultaron saturados de negocios ya digitalizados
  en las 20 ciudades probadas (0-3% sin sitio propio) — el hallazgo central del día.

- [x] **Día 4** (2026-08-11, Nodo 2) — `simulate` corrido sobre 5 pares con el mismo
  seed: reveló que `_PRESENCE_WEIGHTS` es global, no varía por oficio ni metro —
  `locksmith×El Paso` y `pool_service×Tucson` dieron la distribución de presencia web
  *idéntica*. `simulate` no puede responder "ratio de calificación real" por diseño.
  `discover` real sobre `hvac×Houston, TX` (limit=40): de 39 calificados, solo **1 sin
  sitio (2,6%)** — muy por debajo del 35% que asume `simulate.py` y del 45-56% de
  Jobber citado en `validation.md`. Contraprueba en `locksmith×Laredo, TX` (metro más
  chico del catálogo): con `MIN_REVIEWS=50` estándar, **0 prospectos calificaban** —
  el filtro deja el metro entero afuera. Hipótesis abierta para el Día 10: el ratio de
  "sin sitio" depende más del tamaño/competitividad del metro que del oficio. Detalle
  completo en la ficha del Nodo 2 en `PROCESOS.md`.

  > Verificado el pipeline en simulación en esta máquina: `simulate` → `generate --all` →
  > `deploy` → `contact --queue` corren sin errores (requiere `PYTHONPATH=$(pwd)`,
  > `GTM_FROM_NAME` seteado, y los paquetes de `requirements.txt` runtime: `httpx`,
  > `python-dotenv`, `beautifulsoup4`, `PyYAML`). Con datos simulados, `contact` necesita
  > `--no-probe` — las URLs simuladas no responden de verdad, así que sin esa flag todo cae a
  > "no se ubicó formulario" en vez de detectar el formulario real.

- [x] **Día 5** (2026-08-11, Nodos 3+4) — Corrido `score` real sobre los 10 prospectos de
  `tree_service × Albuquerque, NM`. Encontrados y corregidos **dos bugs de producción** al leer
  `sub_scores` línea por línea: (1) `score_website` buscaba audits de Lighthouse por IDs que
  Google renombró (`viewport`/`tap-targets`/`font-size`) — la dimensión `mobile`, el peso más
  alto del score, daba 0 de dolor en el 100% de los sitios puntuados en la sesión, sin que
  ningún test lo detectara (todos mockean `score_website` entero). (2) `probe_url_async`
  trataba cualquier 4xx como "reachable" — un prospecto con el sitio 404 de verdad se puntuó
  como si no tuviera ningún problema (9/100) en vez del máximo dolor posible. Impacto medido:
  calificados sobre los mismos 10 pasó de 2/10 a 6/10. Agregados `tests/gtm/test_score.py` y
  `tests/gtm/test_net.py`, que antes no existían. Comparación score-vs-juicio en 3 casos reales
  (abiertos en el navegador, no en un celular físico): 1 caso donde el score corrigió mi lectura
  a ojo, 1 de acuerdo claro, 1 donde mi propio chequeo a mano encontró el bug del punto (2).
  Detalle completo, con las tres comparaciones, en la ficha del Nodo 3 en `PROCESOS.md`.

- [x] **Día 6** (2026-08-11, Nodos 5+6) — Corrido `generate --all` + `deploy --dry-run` sobre
  los 8 calificados de `tree_service × Albuquerque, NM`, servidas localmente para abrirlas de
  verdad (viewport móvil). Carga: instantánea, cada demo es un único HTML autocontenido de
  ~5,3 KB, cero requests externos (confirmado con la pestaña de red). Hallazgo real, no
  solo impresión a ojo: **el bloque "What we do" es byte-por-byte idéntico entre cualquier
  par de prospectos del mismo oficio** (confirmado con `diff` sobre las 8 demos) — y
  `--ai-copy` no lo cubre, solo varía 5 slots secundarios (CTA, labels, encabezados), nunca
  las 4 tarjetas de servicio. Es el bloque más largo de la página y el más fácil de reconocer
  como plantilla en una comparación lado a lado. Notas de 3 renglones por demo (una sin sitio
  propio, una que compite contra un sitio real bueno, una que compite contra uno malo) en la
  ficha del Nodo 5 en `PROCESOS.md`.

- [x] **Día 7** (2026-08-11, Nodos 7+8+9) — Corrido `contact --queue` real sobre los 8
  prospectos de Albuquerque: 4 llamadas + 4 formularios. Leída la cola completa, el guion de
  llamada en voz alta y 3 emails reales (inglés y español). Encontrados y corregidos **dos
  bugs de mezcla de idiomas confirmados en vivo**, no solo "suena forzado": (1) el guion de
  llamada tenía "[Enviar SMS: {link}]" hardcodeado en español en la rama de inglés — se
  escuchaba literalmente en medio del guion en inglés. (2) Investigar eso llevó a un problema
  más grande: 7 de los 15 hallazgos del catálogo guardaban su evidencia en prosa española
  hardcodeada, colándose en emails en inglés (confirmado en el email real de Legacy Tree
  Company). Arreglados los 7 extendiendo el mismo mecanismo que ya usaba `stale_since`
  (evidencia neutral, se traduce recién al renderizar). Agregados tests de regresión en
  `test_contact.py` y `test_findings.py` (10 casos nuevos entre los dos). Además, sin
  arreglar a propósito (son datos, no código): `GTM_UNSUBSCRIBE_URL` sigue siendo un
  placeholder que no funciona, y `GTM_PHYSICAL_ADDRESS` tiene un typo de espaciado — los dos
  se cuelan en cada email real, ver la nota agregada al Día 19. Detalle completo en la ficha
  del Nodo 8 en `PROCESOS.md`.

- [x] **Día 8** (2026-08-11, Nodos 2+3+8+9) — Distinto de lo planeado: en vez de solo releer
  el mapa, llegó un documento de planificación externo señalando que el Paso 3 (detección de
  ausencia digital) era insuficiente —una sola fuente, Google Maps— y una estrategia de venta
  con piezas que no existían en el código. Implementado con TDD estricto, en 5 etapas:
  1. `classify_web_presence` suma 12 directorios de terceros (Angi, HomeAdvisor, Thumbtack,
     Porch, Houzz, BBB, Yellow Pages, Weebly, GoDaddy Sites, Squarespace, WordPress.com,
     Google Sites) que antes contaban como `HAS_SITE`.
  2. Capa 2 nueva (`gtm/factory/verify.py`): antes de asignarle a un prospecto el dolor máximo
     por "no tiene sitio", corrobora contra un dominio derivado de su nombre (gratis, siempre
     corre) y, con `GTM_SEARCH_API_KEY` opcional, contra Google Programmable Search. Corrida
     de verdad sobre los 10 prospectos reales de Albuquerque: el único caso sin sitio salió
     `unverified` (nombre demasiado largo para que la heurística de dominio le pegue, sin key
     de búsqueda configurada) — resultado honesto, no un falso positivo, pero tampoco probó el
     camino `own_domain` contra datos reales. Pendiente para una sesión futura con más
     candidatos sin sitio.
  3. Cadencia de seguimiento Día 0/3/7, derivada de eventos existentes
     (`FunnelLedger.due_followups`), sin agregar un `FunnelEvent` al compromiso pre-registrado.
  4. Límite de tiempo ("te lo reservo 7 días") en los tres mensajes.
  5. Idioma detectado por prospecto (`gtm/factory/lang.py`) en vez de fijado por corrida —
     encontró y corrigió tres lugares que perdían el idioma real en el camino (`deploy()`,
     el registro del embudo en `/queue`, la fila de Postgres).

  812 tests (79 nuevos; 2 fallan por timing de concurrencia, ya fallaban antes de esta sesión
  y no están relacionados), mypy y ruff limpios. Descartado a propósito, con motivo escrito en
  `PROCESOS.md` Nodo 2: sumar candidatos nuevos desde una búsqueda general (el documento lo
  pedía) — reescribiría discover.py entero por un beneficio dudoso, dado que el cuello de
  botella medido es el % sin sitio, no cuántos negocios se encuentran. Tampoco se tocó el
  canal de contacto (el documento sugería SMS/WhatsApp en frío): `docs/CHANNELS.md` ya había
  descartado eso por TCPA, y el código ya implementa el flujo correcto (llamar, pedir permiso,
  recién ahí mandar el link). Detalle completo, con el razonamiento de cada etapa y lo que se
  dejó afuera, en las fichas de los Nodos 2, 3, 8 y 9 de `PROCESOS.md`.

## Fase B — El CÓMO (días 9-16): debuggear cada pata

- [x] **Día 9** (2026-08-12, Nodo 1) — `avg_ticket_usd: 1800` de `tree_service` ya no es
  "estimado" sin fuente. Dos fuentes reales: BizMetricsHQ (análisis de 165+ empresas de tree
  service, 2025-2026) da $1.800-$4.500+ para "full removals with stump grinding and debris
  hauling" — el paquete exacto que vende el catálogo — pero $1.150 de mediana si se mezclan los
  cuatro tipos de trabajo (poda sola, stump grinding solo, remoción completa, desmonte); This
  Old House (act. 2026-03-05) da $906 de promedio para remoción simple sin stump grinding,
  $1.000-2.000 para árboles de 80+ pies solos. $1.800 se sostiene como "trabajo completo", no
  como promedio de cualquier llamado — nota agregada en `trades.yaml` con el detalle. Además:
  Albuquerque **sí** tiene `mini_tcpa_risk` técnicamente elegible para chequear (NM tiene su
  propia ley, NM Stat §57-12-22 a 30, con derecho de acción privada), aunque el catálogo la
  marca `false` — leída la ley: está scopeada explícitamente a "residential subscriber", no a
  líneas comerciales, así que `false` se sostiene con esta lectura (no es asesoramiento legal;
  nota con la cita agregada en `metros.yaml`, confirmar antes de escalar volumen real).

- [x] **Día 10** (2026-08-12, Nodo 2) — Sí dejan afuera prospectos buenos, medido a igualdad de
  condiciones (mismo `--limit 40`, mismos `pages_fetched=5`): estricto (50/4.0) da 11 calificados
  en `tree_service × Albuquerque, NM`, laxo (20/3.5) da 17. De los 6 nuevos, 3 no tienen sitio
  propio (50%) y 4 califican para demo con pain_score alto (100, 100, 100, 95). El costo de Places
  **no depende de qué tan laxo sea el filtro** — depende solo de `pages_fetched` (1:1 con requests,
  ya logueado, no hizo falta contador nuevo), así que aflojar el filtro sale más barato por
  calificado (USD 0,010 vs USD 0,016 estimado, tier Pro/Enterprise ~USD 32-35/1.000 requests,
  [Woosmap 2026](https://www.woosmap.com/blog/google-places-api-pricing)), no más caro.
  Contraprueba en Laredo, TX con cero filtro: el metro entero tiene 2 negocios de `tree_service` en
  Places, ambos con sitio — ahí el problema es inventario, no filtro. Decisión: usar 20/3.5 para
  Albuquerque en adelante, como flag explícito por corrida, sin tocar todavía las constantes de
  `discover.py`. Detalle completo en la ficha del Nodo 2.

- [x] **Día 11** (2026-08-12, Nodo 3, el día más denso) — Calibración contra juicio humano en 8
  sitios comparables (de 10 puntuados a ciegas: 2 quedaron afuera del cruce, uno nunca se corrió
  por `score.py`, otro no viene de ningún `discover` real). Resultado más duro de lo esperado:
  correlación de rango **negativa** (Spearman ρ = -0,19, no solo "mala") y concordancia en el
  corte de solo **2/8 (25%)**. El caso más claro: `legacytreecompany.com` calificó 10/100 a ojo
  (responsive, rápido, buena info) contra 65/100 del pipeline — enteramente por el flag
  `mobile_friendly=False` de PageSpeed (peso 2.0, el más alto), que contradice la lectura a mano
  en viewport real. El inverso: `kikistreeservice.com` calificó 70/100 a ojo ("vieja, lenta")
  contra 32/100 del pipeline (quedaría afuera de la cola) — la dimensión que sí coincide con el
  juicio humano, `modernity`, tiene el peso más bajo (0.8) de las 5. Decisión: no se mueve el
  corte de 45 (el problema es de orden, no de umbral) ni se tocan los pesos todavía — n=8 es
  chico para eso, mismo criterio que el Día 12 con `dated_palette`. Queda la hipótesis falsable
  para la próxima calibración con muestra mayor: subir el peso de `modernity` y auditar
  `mobile_friendly` contra más casos reales. `dated_palette` no se contradice con esta muestra —
  se sostiene `quotable=False` del Día 12 sin cambios. Detalle completo, con la tabla de 8
  filas, en la ficha del Nodo 3.

- [x] **Día 12** (2026-08-12, Nodo 4, cerrado con Miami) — Ampliada la muestra con `discover`
  real sobre `tree_service × Miami, FL` (20 calificados) para no calibrar nada sobre n=8.
  `dated_palette` resultó más ruidoso de lo que parecía: sobre 11 sitios reales con señal
  medible (Albuquerque+Miami), **dispara en el 73%** — muy por encima de "típico de una
  década atrás". Arreglados dos bugs reales que inflaban esa tasa: `_normalise_hex` no bajaba
  a minúscula (`#FFFFFF`/`#ffffff` contaban doble) y el detector contaba la paleta *default*
  de Gutenberg (WordPress la inyecta sola, la use el diseño o no — confirmado en vivo, 7 de 37
  colores de `legacytreecompany.com` eran exactos a esa paleta). Ninguno de los dos arreglos
  bajó la tasa bajo el umbral — el sesgo real es que los colores que sobreviven son verdes de
  marca (árboles), y el componente "saturado = viejo" los penaliza. Excluir neutros bajaría la
  tasa a 27%, pero **no implementado**: cambiar la fórmula necesita la misma calibración
  contra juicio humano que el Día 11 (pendiente), no decidirse mirando n=11. Mientras tanto:
  `dated_palette` sigue sumando al score pero ya no se cita en el mensaje al prospecto
  (`FindingSpec.quotable=False`, filtrado en `PainScore.sales_lines()`; el informe interno de
  `audit.py` lo sigue mostrando). `legacy_jquery` sí tenía un bug real de falso negativo
  (WordPress sirve la versión en `?ver=` del query string, no en el nombre de archivo — el
  detector solo miraba el nombre) y, al arreglarlo, casi se introduce uno de falso positivo
  simétrico (confundir jQuery Mobile con jQuery core) — el fix final restringe el fallback al
  basename exacto del bundle de jQuery core. Confirmado en vivo: `miamistumpbrothers.com`
  corre jQuery 1.12.4 real (ahora sí detectado), `legacytreecompany.com` no dispara nada
  (correcto, su jQuery core es 3.7.1). Detalle completo, con los números exactos, en la ficha
  del Nodo 4. Sigue sin poder cerrarse sin un oído humano: si la línea de venta del hallazgo
  más grave suena natural en voz alta.

- [x] **Día 13** (2026-08-12, Nodos 5+6, la parte medible) — La premisa de "no se puede sin
  publicar" era falsa a medias: medir Lighthouse **no** necesita `GTM_DEMO_BASE_URL` real —
  `@lhci/cli` ya estaba instalado (`site/node_modules`) y hay Edge headless en la máquina, así
  que corrió local contra las demos servidas por `.claude/launch.json`. Las 8 demos dan
  **exactamente los mismos 4 números**: performance=100, accessibility=90, best-practices=96,
  seo=60. El seo=60 es esperado (el `noindex` de diseño, no un bug). Los otros dos sí son
  bugs reales, y afectan a las 8 demos por igual porque viven en el footer compartido:
  **contraste insuficiente** (3,85:1 contra el 4,5:1 que exige WCAG AA, en la dirección y el
  disclosure del footer) y **404 de `/favicon.ico`** (no declarado). Ninguno arreglado en esta
  sesión — medir y documentar era el alcance acordado, no tocar la plantilla. Además,
  cuantificado con `SequenceMatcher`: **79% del contenido visible es idéntico** entre
  cualquier par de demos (sacando el CSS compartido, que es a propósito). Armada
  `gtm/build/template_recognition_test.html` para la prueba con una persona real — pero esa
  prueba en sí **sigue sin poder hacerse sin vos**: además de necesitar a alguien ajeno al
  proyecto, resultó que no puede ser una prueba ciega de verdad, porque el banner de
  disclosure obligatorio ("Preview site — built for...") ya dice el nombre del negocio.
  Detalle completo en la ficha del Nodo 5. **Actualizado (2026-08-12):** los dos bugs medidos
  acá (contraste 3,85:1 y favicon 404) están arreglados en `gtm/template/site.html` — la causa
  del contraste era que el modo oscuro nunca sobreescribía el color del footer, quedaba con el
  gris de modo claro contra el fondo oscuro. Detalle en la ficha del Nodo 5.

- [x] **Día 14** (2026-08-12, Nodo 7, cerrado con Miami) — `resolve_all` corrido de verdad
  sobre los 10 prospectos de Albuquerque (9/10 con sitio, 5 `CONTACT_FORM`/4 teléfono, cero
  `UNREACHABLE`) y repetido sobre los 20 de Miami (15/20 con sitio, 9 `CONTACT_FORM`/6
  teléfono, cero `UNREACHABLE` de nuevo). Combinados: 24 `HAS_SITE`, 58,3% formulario / 41,7%
  teléfono, **cero `UNREACHABLE` en 34 prospectos reales entre dos metros distintos** — la
  preocupación original del nodo no se materializó ni con el doble de muestra. Detalle en la
  ficha del Nodo 7.

- [x] **Día 15** (2026-08-12, Nodo 8) — Leídos en voz alta los 10 bloques (subject, email,
  formulario, guion de llamada, seguimiento × EN/ES, no solo "3 mensajes") sobre un prospecto
  real. Los mensajes se sostienen tal cual: nada se traba al leerlo, el español no lee como
  traducción automática. Cierra de paso la deuda del Día 12 (línea de venta del hallazgo más
  grave, en voz alta: suena natural). El hallazgo real del día fue estructural, no de
  redacción: `render_queue` (`contact.py`) no propaga `language`, así que `contact --queue`
  siempre renderiza en inglés — no hay camino de CLI a la cola en español todavía. Detalle en
  la ficha del Nodo 8.

- [ ] **Día 16** (60 min, Nodos 10+11) — Roleplay completo: apertura de 20 s + llamada de 20
  min, ensayando las 3 objeciones documentadas en `validation.md`. Cronometrar. Si la apertura
  pasa de 25 segundos, sobra texto.

## Fase C — El PARA QUÉ (días 17-20)

- [x] **Día 17** (2026-08-12) — **Números unitarios.** Corrida real del pipeline (Places +
  PageSpeed reales, no simulado): `score` es el 97% del tiempo de máquina, 12,2 s/prospecto —
  el resto es trivial. Tasa descubierto→calificado real (n=30, 2 metros): **73,3%**, muy por
  encima del temor del Día 4. Proyección de máquina para 200 contactables: **~57 minutos en
  total**. El costo real es tiempo humano, no dinero ni máquina: estimado (no medido, sin
  minutos cargados todavía en `/time-log`) en **~5 min/prospecto** ponderado por el split de
  canal del Día 14, o sea **~16,7 horas** para 200 contactados — entra cómodo en 8 semanas a 5 o
  a 10 hs/semana (3,3 y 1,7 semanas respectivamente). Places cuesta ~USD 2-3 para el lote
  completo. USD/hora depende enteramente de la tasa contactado→venta, que sigue sin medirse
  (`funnel.jsonl` en 0 bytes) — exactamente lo que las primeras 50 llamadas de calibración de
  `corte_temprano_por_costo` existen para resolver antes de comprometerse a los 200. Tabla
  completa en la ficha del Nodo 13.

- [ ] **Día 18** (45 min) — **El criterio.** Releer `decision_criteria.yaml` entero, incluido el
  comentario sobre por qué v1 estaba mal calibrado (el error de potencia estadística). Correr
  `pytest tests/gtm/test_ledger_criteria.py`. Confirmar por escrito, con fecha, que no se toca.

- [x] **Día 19** (2026-08-12, Nodo 8) — **El gate de CI nunca podía cazar el placeholder porque
  usaba el mismo.** `validate_compliance()` valida con `in`/`startswith`, así que
  `https://example.com/unsubscribe` pasaba las 4 validaciones de `SenderIdentity.validate()` —
  y `tests/gtm/conftest.py` usaba **ese mismo placeholder** como fixture, así que
  `pytest -k canspam` daba verde con la config real rota. Arreglado: `validate()` ahora rechaza
  cualquier `unsubscribe_url` en un dominio reservado por RFC 2606 (`example.com` y variantes),
  y las fixtures de test pasaron a un dominio distinto. Construido el mecanismo de baja real:
  migración `0007_unsubscribes.sql` (RLS insert-only, verificado en vivo contra la Supabase real
  — anon key inserta con 201, no puede leer, `[]` vacío), `site/functions/api/unsubscribe.js`
  (formulario de email, no link de un clic — el sistema no genera token por email enviado) y
  `ledger sync-unsubscribes`, corrido de punta a punta. Al escribirlo se encontraron y arreglaron
  dos bugs reales: un `suppression or SuppressionList()` que por el `__len__` de la clase
  reemplazaba en silencio una lista vacía por una que escribe en el archivo real del repo, y que
  `gtm/send/worker.py` nunca chequeaba la lista de supresión antes de enviar — sin eso, la baja
  sería decorativa. Mini-TCPA de NM (Día 9) sigue vigente sin cambios. Sigue pendiente, para
  Juan: la dirección postal (¿falta un espacio o un número?), alta de Zoho Mail, y el dominio
  real para que `/api/unsubscribe` sirva de algo — hasta entonces `validate()` bloquea cualquier
  envío real, que es la protección correcta. Detalle completo en la ficha del Nodo 8.

- [ ] **Día 20** (60 min) — **Cierre.** Reescribir `PROCESOS.md` con todo lo aprendido en las 19
  sesiones anteriores, republicar el Artifact. Escribir el plan concreto de las primeras 25
  llamadas reales: qué días, a qué hora del huso horario del metro elegido, con qué guion ya
  calibrado.

---

## Después del día 20

Empieza la Fase de ejecución de `gtm/plan_aprendizaje.md` (semanas 5-8): los 200 contactos
reales. A las primeras `llamadas_de_calibracion: 50` del `corte_temprano_por_costo`, se
recalcula el corte por costo — ya definido en el yaml, no hay que decidir nada nuevo ahí.
