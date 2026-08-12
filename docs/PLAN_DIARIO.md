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

- [ ] **Día 10** (45 min, Nodo 2) — ¿`MIN_REVIEWS=50` y `MIN_RATING=4.0` dejan afuera a los
  mejores prospectos? Correr con los filtros bajados (ej. 20/3.5) y comparar los dos conjuntos.
  Medir también el costo de Places por prospecto útil.

- [ ] **Día 11** (60 min, Nodo 3 — el día más denso) — Calibrar el score contra tu propio juicio
  en 10 sitios reales: puntuar vos primero de 0-100 a ojo, después mirar el score del pipeline.
  Si la correlación es mala, el problema son los pesos de dimensión o el corte de 45 — no el
  código.

- [x] **Día 12** (2026-08-12, Nodo 4, parcial) — Las dos preguntas que se pueden responder sin
  voz humana, hechas: 1,9 hallazgos por prospecto en promedio sobre los 8 reales de Albuquerque
  que sí puntuó PageSpeed; y sí hay un falso positivo real en `dated_palette` —
  `legacytreecompany.com` lo dispara porque 7 de sus 37 colores detectados son, exactos, la
  paleta *default* del editor de bloques de WordPress (Gutenberg), CSS que se carga siempre que
  el sitio usa bloques, la use el diseño visible o no. `legacy_jquery` no se disparó ni una vez
  en esta muestra, sin datos para juzgarlo. Detalle completo en la ficha del Nodo 4. **Pendiente,
  necesita a alguien escuchando**: si la línea de venta del hallazgo más grave suena natural en
  voz alta delante de un plomero — eso no se puede evaluar sin un oído humano.

- [ ] **Día 13** (45 min, Nodos 5+6) — ¿La demo se reconoce como plantilla? Mostrarle 2 demos a
  alguien que no sabe nada del proyecto y preguntarle qué negocio es. Medir el Lighthouse de la
  propia demo generada. *No se pudo avanzar sin ayuda: mostrarle la demo a alguien ajeno
  necesita a esa persona, y medir el Lighthouse de la demo propia necesita que esté publicada
  de verdad — `GTM_DEMO_BASE_URL` sigue siendo el placeholder (ver Nodo 6), así que hoy no hay
  URL pública que PageSpeed pueda analizar.*

- [x] **Día 14** (2026-08-12, Nodo 7) — `resolve_all` corrido de verdad (con probe real, no
  `--no-probe`) sobre los 10 prospectos de Albuquerque: 9/10 tienen sitio propio, y de esos 9,
  5 resolvieron a `CONTACT_FORM` (55,6%) y 4 cayeron a teléfono (44,4%) por no encontrarse
  formulario. **Cero `UNREACHABLE`** — nadie se pierde del todo en esta muestra. Revisados a
  mano los 2 casos de caída a teléfono más dudosos: ninguno es un falso negativo del detector
  (uno no tiene ningún `<form>` en su home, el otro no respondió al momento de la corrida).
  Detalle en la ficha del Nodo 7.

- [ ] **Día 15** (45 min, Nodo 8) — Leer los 3 mensajes en los 2 idiomas, en voz alta. El
  español no es traducción del inglés: ¿suena a alguien de Argentina hablándole a un dueño de
  negocio en Houston, o a traducción automática?

- [ ] **Día 16** (60 min, Nodos 10+11) — Roleplay completo: apertura de 20 s + llamada de 20
  min, ensayando las 3 objeciones documentadas en `validation.md`. Cronometrar. Si la apertura
  pasa de 25 segundos, sobra texto.

## Fase C — El PARA QUÉ (días 17-20)

- [ ] **Día 17** (60 min) — **Números unitarios.** Con los tiempos medidos en las fases A y B:
  minutos por prospecto en cada etapa, USD/hora proyectado, y cuántas horas cuesta llegar a los
  200 contactados de `decision_criteria.yaml` al ritmo de 5-10 hs/semana. *Salida: tabla de
  economía unitaria agregada a `PROCESOS.md`.*

- [ ] **Día 18** (45 min) — **El criterio.** Releer `decision_criteria.yaml` entero, incluido el
  comentario sobre por qué v1 estaba mal calibrado (el error de potencia estadística). Correr
  `pytest tests/gtm/test_ledger_criteria.py`. Confirmar por escrito, con fecha, que no se toca.

- [ ] **Día 19** (45 min) — **Riesgo.** Correr `pytest tests/gtm/test_outreach.py -k canspam`.
  Revisar: ley mini-TCPA del estado elegido, no grabar llamadas, Factura E para el cobro desde
  USA. Dar de alta el email de envío (Zoho Mail). **Actualizado (Día 7):** no es la única
  credencial que falta — `GTM_UNSUBSCRIBE_URL` sigue siendo el placeholder
  `https://example.com/unsubscribe` (`validate_compliance()` solo chequea que el string esté
  en el cuerpo, no que la URL funcione de verdad) y `GTM_PHYSICAL_ADDRESS` tiene un espacio
  faltante ("1Victorica y La Pampa"). Los dos van en cada email real por exigencia de
  CAN-SPAM — confirmar y arreglar acá antes del primer envío.

- [ ] **Día 20** (60 min) — **Cierre.** Reescribir `PROCESOS.md` con todo lo aprendido en las 19
  sesiones anteriores, republicar el Artifact. Escribir el plan concreto de las primeras 25
  llamadas reales: qué días, a qué hora del huso horario del metro elegido, con qué guion ya
  calibrado.

---

## Después del día 20

Empieza la Fase de ejecución de `gtm/plan_aprendizaje.md` (semanas 5-8): los 200 contactos
reales. A las primeras `llamadas_de_calibracion: 50` del `corte_temprano_por_costo`, se
recalcula el corte por costo — ya definido en el yaml, no hay que decidir nada nuevo ahí.
