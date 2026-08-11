# Mapa de procesos — tech-services-arg

Este documento existe porque el negocio ya está construido en código (`gtm/`), pero el código
solo prueba que las etapas funcionan — no dice **por qué** se cortó en 50 reseñas, **por qué**
el pain score corta en 45, o **qué pasa** si se saca un nodo. Ese es el propósito de este mapa:
poder señalar cualquier pata de la operación y decir qué hace, cómo lo hace, y para qué existe.

Se lee junto a [`docs/PLAN_DIARIO.md`](PLAN_DIARIO.md), que es el plan de 20 sesiones de
30-60 min para entenderlo (Fase A), debuggearlo (Fase B) y cerrarlo (Fase C) antes de arrancar
el experimento pre-registrado de [`gtm/decision_criteria.yaml`](../gtm/decision_criteria.yaml).

Cada nodo se lee: **qué** hace → **cómo** lo hace → **para qué** existe. Ese es el orden pedido,
y es deliberado: entender el mecanismo antes de opinar sobre él evita la trampa más común de
iterar un sistema que todavía no se terminó de leer.

---

## Diagrama 1 — Grafo maestro

Catorce nodos. La línea punteada marca el corte real de la operación: todo lo de arriba lo
automatiza el código; todo lo de abajo lo hace una persona (vos), a propósito — es la decisión
de diseño central del pipeline (ver [`gtm/README.md`](../gtm/README.md#por-qué-existe)).

```mermaid
flowchart TD
    N0["0. Carta de presentación<br/>site/ → juancruzeiriz.com"]
    N1["1. Elección de nicho<br/>trades.yaml + metros.yaml"]
    N2["2. Discover<br/>Places API"]
    N3["3. Ponderación<br/>pain score 0-100"]
    N4["4. Catálogo de hallazgos<br/>15 códigos con evidencia"]
    N5["5. Generate<br/>demo personalizada"]
    N6["6. Deploy<br/>URL pública única"]
    N7["7. Resolución de canal<br/>teléfono / formulario"]
    N8["8. Redacción del mensaje<br/>email / form / guion"]
    N9["9. Cola de trabajo<br/>queue.md"]
    N10(["10. Contacto en frío<br/>humano — 20s"])
    N11(["11. Conversación de venta<br/>humano — 20min"])
    N12(["12. Entrega<br/>humano — 48hs"])
    N13["13. Ledger y decisión<br/>embudo + supresión"]

    N0 -.confianza previa.-> N10
    N1 --> N2 --> N3 --> N4
    N3 --> N5
    N4 --> N5
    N5 --> N6 --> N7 --> N8 --> N9
    N9 ==corte automatizado/humano==> N10
    N10 --> N11 --> N12 --> N13
    N13 -.alimenta.-> N1
    N13 -.alimenta.-> N9

    classDef auto fill:#1f2937,stroke:#4b5563,color:#e5e7eb
    classDef human fill:#7c2d12,stroke:#c2410c,color:#fed7aa
    class N0,N1,N2,N3,N4,N5,N6,N7,N8,N9,N13 auto
    class N10,N11,N12 human
```

| # | Nodo | Dónde vive | Qué decide |
|---|---|---|---|
| 0 | Carta de presentación | `site/` → juancruzeiriz.com | Lo que ven cuando te googlean. No es parte del pipeline: es el nodo de confianza del que cuelgan todos los demás |
| 1 | Elección de nicho | `gtm/catalog/trades.yaml`, `metros.yaml` | `rank` de oficio = ticket × peso de urgencia; `rank` de metro = población × %hispano ÷ 1.5 si hay riesgo mini-TCPA |
| 2 | Discover | `gtm/factory/discover.py` | Google Places API. Filtro: ≥50 reseñas, ≥4.0 rating, con teléfono. Orden: sin sitio primero |
| 3 | Ponderación (pain score) | `gtm/factory/score.py` + `PainScore.score` en `types.py` | PageSpeed + CrUX + forensics HTML + Wayback → 5 dimensiones combinadas con OR ruidoso. Corte `is_qualified`: score ≥ 45 |
| 4 | Catálogo de hallazgos | `gtm/factory/findings.py` (15 códigos) | Cada defecto detectable lleva su evidencia citable y su línea de venta en EN/ES |
| 5 | Generate | `gtm/factory/generate.py`, `gtm/template/site.html` | Renderiza la demo con datos reales del negocio. `noindex`, marcada como preview de terceros |
| 6 | Deploy | `gtm/factory/deploy.py` | Copia al directorio publicable y asigna URL única. Sin URL viva no hay pitch |
| 7 | Resolución de canal | `gtm/factory/contact.py::resolve_contact` | Sin sitio propio → teléfono (mayor dolor). Con sitio → busca formulario de contacto. Nunca email scrapeado, nunca SMS en frío |
| 8 | Redacción del mensaje | `outreach.py::build_body`, `contact.py::build_form_message`/`build_call_script` | Tres formatos distintos para tres canales. El email se valida contra CAN-SPAM al construirse |
| 9 | Cola de trabajo | `contact.py::render_queue` → `gtm/build/queue.md`, `/queue` en la UI | El pipeline **prepara, no envía**. Cola ordenada por dolor descendente |
| 10 | Contacto en frío | Humano — guion en `pipeline.md` | Llamada de 20 segundos. Objetivo único: permiso para mandar el link por SMS |
| 11 | Conversación de venta | Humano — guion de 20 min en `pipeline.md` | No es demo del producto: confirmar que el dolor existe y hay presupuesto. Precio recién al final |
| 12 | Entrega | Humano — 48 hs | Apuntar el dominio + configurar el proveedor de missed-call-text-back |
| 13 | Ledger y decisión | `gtm/factory/ledger.py`, `decision_criteria.yaml`, `/dashboard/*` | Embudo de 5 niveles + lista de supresión, ambos persistidos como hash. Ganador: 1 venta cobrada. Kill: 200 contactados, 0 ventas, <5 respuestas |

---

## Diagrama 2 — DER de datos

Todo se encadena por `Prospect.place_id`, el ID estable que devuelve Google Places. Fuente:
[`gtm/factory/types.py`](../gtm/factory/types.py).

```mermaid
erDiagram
    TRADE ||--o{ PROSPECT : califica
    METRO ||--o{ PROSPECT : ubica
    PROSPECT ||--o| PAINSCORE : tiene
    PAINSCORE ||--o{ FINDING : contiene
    PROSPECT ||--o| DEMO : genera
    DEMO ||--o| CONTACTPLAN : habilita
    PROSPECT ||--o{ OUTREACHEMAIL : recibe
    PROSPECT ||--o{ FUNNELEVENT : registra
    PROSPECT ||--o{ SUPPRESSIONENTRY : puede-estar-en

    PROSPECT {
        string place_id PK
        string name
        string vertical
        string metro
        string phone
        string website
        float rating
        int review_count
    }
    PAINSCORE {
        string place_id FK
        int performance
        int seo
        int accessibility
        bool has_web_presence
        bool reachable
    }
    DEMO {
        string place_id FK
        string slug
        string url
        bool is_live
    }
    CONTACTPLAN {
        string place_id FK
        string channel
        string target
    }
    FUNNELEVENT {
        string place_id_hash
        string event
        string channel
        string language
    }
    SUPPRESSIONENTRY {
        string key_hash
        string reason
    }
```

`FUNNELEVENT` y `SUPPRESSIONENTRY` guardan **solo hashes SHA-256** de `place_id`/teléfono/dominio
normalizados, nunca el dato de contacto — es la regla que permite que `funnel.jsonl` y
`suppression.jsonl` vivan en git (ver [`gtm/README.md`](../gtm/README.md#reglas-que-el-código-hace-cumplir)).

---

## Diagrama 3 — Bucles de realimentación

Esto es lo que hoy **no está dibujado en ningún lado** — y por eso es donde viven la mayoría de
las oportunidades de mejora que busca la Fase B del plan diario.

```mermaid
flowchart LR
    subgraph Operación
        D2["Discover"]
        D3["Score"]
        D9["Cola de contacto"]
        D13["Ledger<br/>funnel + supresión"]
    end
    subgraph Análisis
        DASH1["/dashboard/funnel<br/>respuesta por segmento"]
        DASH2["/dashboard/economics<br/>USD/hora, cohortes"]
    end

    D2 --> D3 --> D9 --> D13
    D13 --> DASH1
    D13 --> DASH2
    DASH1 -.qué oficio×metro×idioma convierte.-> N1["Elección de nicho"]
    DASH2 -.dónde se va el tiempo.-> N1
    D13 -.ya contactado / opt-out.-> D2
    DASH1 -.qué hallazgo convierte más.-> N4["Catálogo de hallazgos"]
```

Tres bucles concretos:

1. **Supresión → discover.** Un `place_id` ya contactado o que pidió baja nunca vuelve a
   aparecer en una corrida nueva — se filtra en `contact.py::main` antes de llegar a la cola.
2. **Embudo → elección de nicho.** `/dashboard/economics` correlaciona dolor↔conversión por
   cohorte (oficio×metro×idioma). Es la única fuente legítima para cambiar de nicho — nunca una
   corazonada a mitad del experimento.
3. **Embudo → catálogo de hallazgos.** Si un hallazgo nunca aparece en el pain_score de los que
   sí convierten, es candidato a bajar de peso o sacar — pero esto es una lectura *posterior* al
   cierre del experimento, no algo para tocar en caliente (viola `regla_dura`).

---

## Fichas de nodo

Plantilla fija. **Problemas conocidos** y **Bitácora** arrancan vacíos a propósito — se llenan
durante la Fase B del [plan diario](PLAN_DIARIO.md), con hipótesis falsables, no opiniones.

### 0. Carta de presentación

**Qué** — El sitio propio (juancruzeiriz.com) y el perfil que un prospecto encuentra si te
googlea antes de contestar.

**Cómo** — Astro estático, `site/src/`. Deploy a Cloudflare Pages
(`tech-services-arg.pages.dev`), redeploy automático con cada push a `main` —
ya no hay workflow de GitHub Actions para esto. El dominio propio
(`juancruzeiriz.com`) se corta a Cloudflare (*Custom domains* del proyecto,
DNS proxied) — ver el estado del corte antes de asumirlo terminado.

**Para qué** — Es el mecanismo #5 de "resolver la falta de marca" en `pipeline.md`: presencia
verificable. Sin esto, el prospecto que googlea antes de responder no encuentra nada y el
mensaje pierde credibilidad.

**Palancas** — Copy de "Sobre mí", certificaciones mostradas, CV descargable, nav mobile, tema
activo (dark/light/cream), loader de intro.

**Problemas conocidos** — Auditoría del Día 2 (2026-08-05). Tres hipótesis, verificadas por
medición en vivo antes de tocar código — no por opinión:

1. **Bug de layout en `/servicios/`, confirmado.** `.services-detail-list li` (selector
   descendiente) atrapaba también los `<li>` de la lista de stack anidada dentro de cada fila.
   Medido: el chip "Python" medía 97×59px con `grid-template-columns: 56px 0px` — texto en una
   columna de 0px de ancho. 21 chips afectados en las 4 rutas del catálogo. **Resuelto** en
   `fix(site): chips de stack rotos...` — combinador de hijo directo (`>`).
2. **"Nada se mueve", parcialmente un bug y parcialmente diseño.** Medido en producción:
   `prefers-reduced-motion` estaba activo y la regla `*, *::before, *::after
   { animation-duration: 0.01ms !important }` apagaba *todo* el movimiento, no solo el
   vestibular — más de lo que pide la accesibilidad (WCAG 2.3.3 habla de parallax/desplazamientos
   grandes, no de un simple fundido). **Resuelto**: reduced-motion ahora conserva el fade de
   opacidad y solo mata `transform`/animaciones ambientales (`data-motion="ambient"`).
3. **Aun con el movimiento activo, era imperceptible.** Blobs de 22-28s de período y reveals de
   `translateY(1.2rem)` no se notan en la ventana de atención real de un visitante. **Resuelto**:
   blobs a 13-16s con más amplitud, reveals a `translateY(2.2rem) + scale`, stagger real vía
   `--i` en las grillas (Certifications/Services/StatsBand/ProjectCard), más loader de intro,
   tercer tema, blobs con parallax de mouse, transiciones SPA entre páginas, barra de progreso de
   lectura y contadores que cuentan hacia arriba.

**Oportunidad identificada, no resuelta todavía**: el marquee de servicios podría reaccionar a la
velocidad/dirección del scroll en vez de tener una velocidad fija — quedó fuera de esta sesión
por relación costo/beneficio (la ganancia era la más chica de toda la lista).

**Bitácora** —

- **2026-08-05** — Fix de layout en `/servicios/` (Fase 0). Reduced-motion matizado + intensidad
  de reveals/blobs subida (Fase 1). Tercer tema "cream" con contraste WCAG AA calculado, no a
  ojo — el primer valor de acento elegido daba 3.80:1, insuficiente (Fase 3b). Loader de intro
  con grilla de bits 0/1, diseñado para degradar a "no mostrar nunca" si el script falla, nunca a
  "overlay trabado para siempre" (Fase 3a). `<ClientRouter />` + parallax de mouse en los blobs +
  barra de progreso de lectura (CSS puro) + contadores animados en StatsBand (Fase 3c). Paleta
  del tema oscuro rediseñada a pedido: negro/blanco puro (`--color-ink`/`--color-paper`)
  reemplazados SOLO en ese tema por carbón grisáceo (`#1c1917`) y crema cálido (`#efe6d8`) —
  claro y cream quedan intactos, son tokens propios desacoplados. Salvia apagado (`#7c8a6a`,
  tendencia documentada de paletas tierra-terracota-crema 2026) como segundo acento decorativo
  del oscuro únicamente: un blob del hero y la mitad de los puntos del marquee, nunca en botones
  o links. Contraste verificado: crema/carbón 14.14:1, taupe-muted/carbón 6.68:1.
- **2026-08-05** — Sección "Sobre mí": se sacó la trayectoria (`Experience.astro`/`experience.ts`,
  eliminados — ya está en LinkedIn y el CV, era ruido repetido) y se reescribió el copy: menos
  jerga técnica (sin nombrar Django/PageSpeed/Chrome UX Report), directo a los tres beneficios que
  le importan a alguien sin conocimiento técnico — más clientes, más facturación, más presencia.
  Se agregó el proyecto del trabajo actual (motor de costo-a-servir/rentabilidad, ETL) como primer
  ítem de Proyectos, descrito en términos de capacidad, no de detalles confidenciales del empleador.
  De paso, se implementó el render del campo `stages` (existía en `projects.ts` desde antes, nunca
  se mostraba en ningún lado) como un esquema de flujo de nodos con flechas — ahora también visible
  en `gtm-factory`, que ya tenía sus 6 etapas cargadas y sin usar.

---

### 1. Elección de nicho

**Qué** — Elegir un par oficio × metro antes de correr nada.

**Cómo** — `gtm/catalog/trades.yaml` (rank = `avg_ticket_usd` × peso de urgencia: alto=3,
medio=2, bajo=1, ascendente = mejor primero); `gtm/catalog/metros.yaml` (rank = población ×
%hispano/100 ÷ 1.5 si `mini_tcpa_risk`, descendente = mejor primero).

**Para qué** — Es la decisión de apalancamiento más importante del negocio: el mismo template
sirve a todos los prospectos del par elegido, el costo marginal por demo tiende a cero. Elegir
mal acá invalida todo lo que sigue.

**Palancas** — Qué oficio, qué metro, umbral de reseñas/rating aguas abajo en discover.

**Problemas conocidos** —

- (2026-08-11) Tres entradas de `trades.yaml` (`pool_service`, `appliance_repair`,
  `locksmith`) tenían el `rank` invertido respecto a la fórmula documentada en la
  cabecera del archivo. No había ningún comentario que lo justificara ni ningún commit
  posterior a la carga inicial que lo explicara — era un error de carga, no una
  decisión de recurrencia no escrita. Corregido en `600182d`. Los 20 metros sí cumplían
  la fórmula exacta.

**Bitácora** —

- (2026-08-11) Houston (score 690.000) y Phoenix (675.360) quedan casi empatados; lo
  único que los separa es la penalización de `mini_tcpa_risk` de Texas. Sin esa
  penalización Houston daría 1.035.000 y no habría contienda. Vale tenerlo presente:
  la elección de metro #1 depende de cuánto se confíe en el multiplicador 1.5, que es
  un número fijado a mano, no medido.

**Par elegido (2026-08-11): `tree_service` (poda y tala de árboles) × Albuquerque, NM.**

1. Barrido real con `discover` sobre los 15 oficios × 20 metros del catálogo (539
   negocios revisados vía Places API): `tree_service × Albuquerque` da el mayor "valor
   esperado" (% sin sitio × ticket promedio) del catálogo junto con `tree_service ×
   Miami` — 23,5% sin sitio propio sobre un ticket de 1.800 USD.
2. Los oficios de mayor ticket "obvio" del ranking original (roofer, hvac, plumber,
   pest_control) están saturados de negocios ya digitalizados en las 20 ciudades
   probadas (0-3% sin sitio) — el ángulo de urgencia alta no compensa la ausencia casi
   total de prospectos reales que cumplan el perfil de la oferta.
3. Albuquerque no tiene `mini_tcpa_risk` (a diferencia de Miami, que sí), así que las
   primeras llamadas no dependen de una ley estatal de telemarketing más estricta que
   la exención B2B federal — una variable menos para el Día 9.
4. Urgencia `medium` (una rama caída en la tormenta sí apura, una poda de rutina no) da
   un ángulo de venta más natural que cercos o pintura, que quedaron muy cerca en el
   ranking pero son compras 100% meditadas, sin ningún apuro que vender.
5. La muestra real en Albuquerque es de 17 negocios, la más chica de las candidatas del
   top — conviene confirmarla con una muestra mayor (Día 10) antes de comprometer el
   guion de venta a este par, pero es el mejor punto de partida con los datos de hoy.

---

### 2. Discover

**Qué** — Encontrar negocios candidatos del par oficio×metro elegido.

**Cómo** — `gtm/factory/discover.py::discover`. Google Places API (New), `textQuery`, hasta 5
páginas. Filtra por `MIN_REVIEWS=50`, `MIN_RATING=4.0`, requiere teléfono. Ordena sin-sitio
primero, después por reseñas descendente.

**Para qué** — El cruce reseñas-altas + rating-alto + web-pobre es el prospecto ideal: tiene
plata, le importa su reputación, y su web no está a la altura — no está peleando por sobrevivir.

**Palancas** — `MIN_REVIEWS`, `MIN_RATING`, `--limit`.

**Problemas conocidos** —

- (2026-08-11) `discover` real sobre `hvac × Houston, TX` con `limit=40`: de 39
  calificados, **1 solo no tiene sitio (2,6%)**. `simulate.py` asume 20% `NONE` +
  15% `SOCIAL_ONLY` = 35% sin sitio propio; la encuesta de Jobber citada en
  `validation.md` dice 45-56%. Ninguno de los dos números se sostuvo con datos
  reales en este metro — `_PRESENCE_WEIGHTS` de `simulate.py` está siendo muy
  optimista para un metro grande y competitivo. Hipótesis: Houston tiene cadenas
  nacionales y franquicias (John Moore Services, 1-800-PLUMBER, Aire Serv,
  Service Experts) que saturan los primeros resultados por relevancia — todas ya
  digitalizadas. El metro más grande del catálogo puede ser el peor lugar para
  buscar el prospecto "sin sitio" que la oferta necesita.
- (2026-08-11) Contraprueba en `locksmith × Laredo, TX` (el metro más chico y más
  hispano del catálogo, sin filtro de reseñas/rating): solo **4 locksmiths en
  total** en toda la búsqueda, 1 de 4 sin sitio (25%, más cerca de lo esperado,
  pero n=4 no prueba nada por sí solo). Con `MIN_REVIEWS=50` estándar, **0
  calificaban** — el filtro deja el metro entero sin prospectos.
- Hipótesis falsable para seguir en el Día 10: el ratio de "sin sitio" depende más
  del **tamaño/competitividad del metro** que del oficio — `simulate.py` trata a
  los dos como si dieran lo mismo, y en una muestra real no dio lo mismo. Repetir
  con 3-4 metros medianos (ni el más grande ni el más chico del catálogo) antes de
  tratar cualquiera de los dos números como calibrado.
- (2026-08-11) **Barrido completo, 15 oficios × 20 metros, 539 negocios reales
  vía Places API.** Confirma y refina la hipótesis de arriba — no es solo el
  tamaño del metro, es el oficio en sí. Agregado por oficio (suma de las 3
  primeras ciudades probadas, `MIN_REVIEWS` bajado a 20):

  | Oficio | Ticket | % sin sitio | Valor esperado (%×ticket) |
  |---|---|---|---|
  | Electricista | 750 | 10,1% | 76 |
  | Cercos | 2.500 | 9,6% | 240 |
  | Poda de árboles | 1.800 | 9,1% | 164 |
  | Reparación de electrodomésticos | 325 | 7,2% | 23 |
  | Remoción de escombros | 300 | 6,5% | 20 |
  | Paisajismo | 900 | 6,4% | 58 |
  | Pintor | 2.800 | 5,8% | 162 |
  | Cerrajero | 200 | 4,9% | 10 |
  | Mantenimiento de piletas | 450 | 3,7% | 17 |
  | Puertas de garaje | 500 | 2,4% | 12 |
  | Canaletas | 800 | 1,7% | 14 |
  | HVAC | 2.434 | 1,1% | 27 |
  | Techista, plomero, control de plagas | — | 0,0% | 0 |

  Ampliado a los 20 metros completos para los 4 candidatos con mejor valor
  esperado (cercos, poda de árboles, pintor, electricista — 68 negocios más
  revisados). Top 3 combinaciones individuales oficio×metro (muestra ≥15):

  | Oficio × metro | Muestra | % sin sitio | Valor esperado |
  |---|---|---|---|
  | Poda de árboles × Miami, FL | 21 | 23,8% | 429 |
  | Poda de árboles × Albuquerque, NM | 17 | 23,5% | 424 |
  | Cercos × Bakersfield, CA | 15 | 13,3% | 333 |

  El electricista, pese a rankear alto en el agregado de 3 ciudades, resultó
  volátil: 0% en Houston/Dallas/Vegas/Denver/Fresno/Orlando, pero 28-36% en
  las ciudades fronterizas con más población hispana (El Paso, Laredo,
  McAllen) — el agregado de 20 metros lo bajó a 65 de valor esperado, último
  entre los 4 candidatos. Decisión del par final en la ficha del Nodo 1.

**Bitácora** —

- (2026-08-11) `simulate.py` usa `_PRESENCE_WEIGHTS` global, igual para cualquier
  oficio y metro — confirmado corriendo el mismo `seed=42` en 5 pares distintos:
  `locksmith×El Paso` y `pool_service×Tucson` dieron la distribución de presencia
  web *idéntica* (6 sin sitio, 4 solo redes, 20 con sitio, de 30). El simulador no
  modela ninguna diferencia real entre verticales o metros — sirve para ejercitar
  el pipeline (su propósito declarado), no para estimar el ratio de calificación
  real de un par específico. Para eso hace falta `discover` real, no `simulate`.

---

### 3. Ponderación (pain score)

**Qué** — Medir cuánto le duele a cada prospecto su presencia digital actual, en una escala
0-100.

**Cómo** — `gtm/factory/score.py::score_prospect` orquesta PageSpeed Insights (Lighthouse
mobile), CrUX (datos de campo reales), forensics sobre el HTML crudo y última fecha de cambio
real (Wayback CDX). `PainScore.score` en `types.py` combina 5 dimensiones (mobile 2.0,
conversion 2.0, speed 1.0, seo 1.0, modernity 0.8 — corregido acá el 2026-08-11, la ficha decía
"speed 1.5, mobile 1.5", desactualizado respecto a `_DIMENSION_WEIGHTS`) con **OR ruidoso** por
dimensión — dos hallazgos en la misma dimensión duelen más que uno solo, nunca se promedian
entre sí. Sin sitio = 100 automático. Sitio caído = 95. `is_qualified` corta en `score >= 45`.

**Para qué** — Es el filtro que decide en qué prospecto vale la pena gastar el costo (bajo pero
no cero) de generar una demo. Sin esto, se generarían demos parejo para negocios que ya tienen
web decente, quemando tiempo sin mejorar la tasa de respuesta.

**Palancas** — Los 5 pesos de dimensión, el corte de 45, `MIN_REVIEWS`/`MIN_RATING` aguas
arriba que determinan qué llega a puntuarse.

**Problemas conocidos** —

- (2026-08-11, **corregido**) `score_website` buscaba los audits de Lighthouse por sus IDs
  viejos (`viewport`, `tap-targets`, `font-size`), que Google renombró/retiró de PageSpeed
  Insights en algún momento antes de esta fecha. Confirmado en vivo contra la API real: esos
  tres IDs ya no aparecen en la respuesta, así que `mobile_friendly` quedaba siempre en `None`
  y el hallazgo `tap_targets` nunca se disparaba — la dimensión `mobile` (el peso más alto del
  score, 2.0) daba **0 de dolor en el 100% de los 90+ sitios reales puntuados** en esta sesión,
  sin que ningún test lo notara: los únicos tests de `score_prospect`/`score_all` mockean
  `score_website` entero, así que el parseo real del payload de Lighthouse no tenía cobertura.
  Fix: `viewport`→`meta-viewport`, `tap-targets`→`target-size`; `font-size` no tiene sucesor
  (Lighthouse lo sacó de la API sin reemplazo) y quedó deshabilitado con comentario. Agregado
  `tests/gtm/test_score.py`, que antes no existía. Impacto medido sobre los mismos 10
  prospectos reales de Albuquerque: calificados (`score >= 45`) pasó de 2/10 a 6/10.
- (2026-08-11, **corregido**) `probe_url_async`/`probe_url` trataban cualquier status
  `< 500` como "reachable", incluido 404. Un prospecto real (`leos-tree-service.com`) tiene
  el sitio caído de verdad (404 confirmado con `curl`, sin importar el User-Agent), pero
  pasaba el probe igual y se mandaba a puntuar con PageSpeed, que devolvió un puntaje casi
  perfecto (probablemente una corrida cacheada de cuando el sitio sí andaba) — el negocio
  quedó puntuado en 9/100 (sin dolor) cuando la realidad es la mejor línea de venta posible
  ("tu sitio ni siquiera carga"). Fix: el corte pasa a `< 400`. Mismo prospecto, con el fix:
  95/100, `is_qualified=True`. Agregado `tests/gtm/test_net.py`, que antes no existía.
- **Límite conocido, no arreglado a propósito**: con el fix de arriba, un sitio real y
  funcional (`bacastrees.com`, verificado con `curl` normal: 200 tras dos redirects) también
  cae en "no reachable" porque el sitio bloquea al cliente HTTP del pipeline — probado con
  el User-Agent propio y con uno de navegador real, ambos reciben 403 sin redirigir, lo que
  sugiere bloqueo por fingerprint TLS/HTTP más que por el header. Imitar el fingerprint de un
  navegador real para evadir esto no se hace: `net.py` ya documenta la decisión de
  identificarse en vez de disfrazarse. Consecuencia práctica: un `reachable=False` es una
  señal fuerte, no una certeza — antes de usar "tu sitio no carga" como línea de venta en una
  llamada real, conviene un chequeo humano rápido. Relevante para el Día 12 (¿la línea de
  venta del hallazgo más grave suena natural?) y el Día 14 (tasa de `UNREACHABLE`).

**Bitácora** —

- (2026-08-11) **Comparación score-vs-juicio propio, 3 casos reales** (poda de árboles ×
  Albuquerque, con los dos fixes de arriba ya aplicados):
  - **Legacy Tree Company (score 65, calificado)** — mi lectura del contenido a ojo: sitio
    con pinta profesional, 908 reseñas a 4.9★, personal certificado, teléfono tocable, CTAs
    claros. A ojo yo lo hubiera descartado (pain bajo, ~15-25). El score tenía razón y yo no:
    Lighthouse mobile mide `performance=32/100` (rendimiento real, no apariencia) y
    `target-size` reprobado (botones muy juntos) — dos problemas técnicos invisibles leyendo
    el contenido, que "verse profesional" no compensa en un celular real.
  - **Treepros LLC (score 46-47, al borde del corte)** — acá coincidimos: mirando la página
    a mano no encontré ningún link `tel:` entre los elementos interactivos (confirma
    `no_tel_link` a ojo), más URL sin HTTPS. Caso de acuerdo claro entre algoritmo y ojo.
  - **Leo's Tree Service (score 9→95 con el fix)** — el caso que encontró el bug de arriba:
    mi propio chequeo a mano (la página literalmente dice "404 - Page not found") es lo que
    disparó la investigación que llevó al fix de `probe_url_async`. Acá el juicio humano
    encontró lo que el algoritmo (antes del fix) se perdía.
  - Conclusión del ejercicio: en 1 de 3 casos el score corrige al ojo (mide algo que no se ve
    a simple vista), en 1 de 3 coinciden, y en 1 de 3 el ojo encontró un bug real del score.
    Ninguno de los tres es "el score siempre tiene razón" ni "el ojo siempre tiene razón" —
    exactamente por eso vale la pena seguir haciendo este ejercicio en más casos.

---

### 4. Catálogo de hallazgos

**Qué** — El diccionario de 15 defectos detectables, cada uno con severidad, dimensión, peso, y
su frase de venta en inglés y español.

**Cómo** — `gtm/factory/findings.py::FINDINGS`. Cada `Finding` concreto lleva evidencia citable
(un número, una fecha, una etiqueta encontrada) — nunca una afirmación sin dato detrás.
`PainScore.sales_lines()` los ordena del más grave al menos grave.

**Para qué** — Es lo que convierte un score abstracto en una frase que un dueño de negocio
puede verificar él mismo en el momento ("tu sitio no cambia desde marzo de 2016"). Sin evidencia
citable, el gancho es indistinguible del spam genérico que ya descartaron veinte veces.

**Palancas** — El texto de cada `sales_line_en`/`sales_line_es`, el peso de cada hallazgo.

**Problemas conocidos** —

**Bitácora** —

---

### 5. Generate

**Qué** — Renderizar la demo personalizada del negocio.

**Cómo** — `gtm/factory/generate.py` + `gtm/template/site.html`. Usa nombre, teléfono, rating,
reseñas (agregado, no texto — restricción de licencia de Google Maps Platform), ciudad y
servicios del catálogo (`gtm/catalog`). Se marca con `noindex` y como preview de terceros.

**Para qué** — Es el artefacto que reemplaza a la marca: el prospecto no tiene que creer nada,
lo abre y lo ve. Solo es viable como estrategia si generar el artefacto es casi gratis — por
eso toda la automatización está acá y no en la entrega.

**Palancas** — Copy por vertical en `trades.yaml`, plantilla HTML, servicios default cuando el
vertical no está en catálogo.

**Problemas conocidos** —

- (2026-08-11) **El bloque "What we do" (las 4 tarjetas de servicios) es byte-por-byte
  idéntico entre cualquier par de prospectos del mismo oficio**, confirmado con `diff` real
  sobre las 8 demos generadas de `tree_service × Albuquerque`: título y cuerpo de las 4
  tarjetas ("Emergency removal / Storm-damaged and fallen trees, cleared fast.", etc.) no
  cambian ni un carácter entre Davids Tree Removal, Legacy Tree Company, Treepros y las otras
  5 — lo único que varía en todo el HTML es nombre, teléfono, dirección, rating y conteo de
  reseñas. `--ai-copy` (`copy_ai.py`) **no toca este bloque**: solo varía 5 slots 100%
  genéricos (`cta_body`, `trust_serving_label`, `trust_fast_label`, `services_heading`,
  `reviews_heading`), nunca `services_html`, que sale fijo de `trade.services()` en
  `trades.yaml`. Es el bloque con más texto de la página y el más fácil de comparar
  lado a lado o de buscar en Google con una frase exacta ("Storm-damaged and fallen trees,
  cleared fast" + nombre de otro negocio) — si eso pasa, la demo deja de ser "tu sitio hecho
  a medida" para ser evidencia de que es una plantilla. Hipótesis falsable para el Día 13:
  si se le muestran 2 demos del mismo oficio a alguien ajeno al proyecto, reconoce el patrón
  en el bloque de servicios en menos de lo que tarda en leerlo — probarlo con una persona
  real antes de asumir que `--ai-copy` (que ya existe pero no cubre esto) alcanza.

**Bitácora** —

- (2026-08-11) Corrido el pipeline real hasta acá (`discover` → `score` → `generate --all`)
  sobre `tree_service × Albuquerque, NM`: 8/9 calificados, 8 demos generadas. Servidas
  localmente (`.claude/launch.json`, config `demos`, `python -m http.server`) para abrirlas
  de verdad en vez de solo leer el código. Cada demo es un único archivo HTML autocontenido
  de ~5,3 KB, **cero requests externos** (confirmado con `read_network_requests`: una sola
  entrada, la del propio HTML) — carga instantánea en el sentido literal: no hay nada que
  esperar más allá de la latencia de red hasta donde se hostee. Notas de 3 renglones por
  demo, viewport móvil (375×812):
  - **Davids Tree Removal (sin sitio propio, pain=100)** — la demo es la primera presencia
    digital real de este negocio. Botón de llamar arriba de todo, teléfono tocable, reseñas
    reales (78, 5★). Para este caso el "es plantilla" importa poco: no hay nada previo con
    qué compararla, y es estrictamente mejor que no tener nada.
  - **Legacy Tree Company (ya tiene sitio propio profesional, pain=62)** — acá sí importa:
    esta demo compite contra un sitio real con 903 reseñas y personal certificado. El
    contenido de servicios es genérico donde el sitio real de este negocio es específico
    (arboristas certificados ISA, equipo con nombre y foto) — la demo gana en velocidad
    móvil pura, pero pierde en especificidad si el dueño la compara con lo que ya tiene.
  - **Treepros LLC (al borde del corte, pain=50)** — el caso más favorable para la demo:
    el sitio real de este negocio no tiene teléfono tocable ni HTTPS (hallazgos confirmados
    a mano en el Día 5); la demo sí tiene ambos. Acá la comparación es claramente a favor.

---

### 6. Deploy

**Qué** — Publicar la demo en una URL pública única y estable.

**Cómo** — `gtm/factory/deploy.py::deploy`. Copia a `gtm/public/<slug>/`, listo para
`wrangler pages deploy`. El directorio está fuera de git (datos de contacto de negocios reales).

**Para qué** — Un mockup adjunto no es prueba de trabajo. Sin URL viva, `outreach.py` rechaza
directamente el email — es una regla dura, no una convención.

**Palancas** — `GTM_DEMO_BASE_URL`, el dominio donde se publica.

**Problemas conocidos** —

**Bitácora** —

- (2026-08-11) `deploy --dry-run` corrido de verdad sobre las 8 demos del Nodo 5: se comporta
  exactamente como documenta el código (calcula URLs, no copia nada a `gtm/public/`, no
  escribe el índice). `GTM_DEMO_BASE_URL` en `.env.personal` sigue siendo el placeholder
  `https://demo.example.com` — no es un bug, pero es el dato pendiente antes de un deploy
  real: hoy no hay ningún hosting de demos configurado, distinto de `tech-services-arg.pages.dev`
  (el portfolio) y del proyecto de Cloudflare Pages de las demos que sí existe en
  `cloudflare/README.md` pero cuyo dominio real no está anotado acá.

---

### 7. Resolución de canal

**Qué** — Decidir por qué canal se contacta a cada prospecto: Google Places no da emails.

**Cómo** — `gtm/factory/contact.py::resolve_contact`. Sin sitio propio (o solo redes) → teléfono
si hay, si no `UNREACHABLE`. Con sitio → busca `<form>` con textarea o campo de email, rankeado
por palabras clave (`request-a-quote` convierte mejor que `contact-us`). Sin formulario
ubicable pero con teléfono → teléfono igual.

**Para qué** — La asignación de canal sigue al pain score a propósito: los de mayor dolor no
tienen sitio, así que no tienen formulario, pero sí teléfono, y son pocos — manejable a mano.

**Palancas** — `_FORM_HINTS` y su orden de prioridad, `--no-probe`.

**Problemas conocidos** —

**Bitácora** —

---

### 8. Redacción del mensaje

**Qué** — Escribir el texto real que ve el prospecto, en el formato del canal resuelto.

**Cómo** — Tres builders: `outreach.py::build_body` (email, con validación CAN-SPAM
obligatoria), `contact.py::build_form_message` (≤600 caracteres, sin firma ni dirección postal),
`contact.py::build_call_script` (guion de 20 s). El gancho de "llamada perdida" **solo** se
renderiza si hay una `missed_call_at` real registrada — si no, cae al ángulo medido por
Lighthouse.

**Para qué** — El orden importa: primero el hecho observado, después el link, recién al final
el precio. Si el precio va arriba, se lee como publicidad. Y nunca se inventa un hecho: el
primer teléfono que atiendan destruye la venta y la reputación.

**Palancas** — El texto de los tres templates, `price_usd`, `language`.

**Problemas conocidos** —

**Bitácora** —

---

### 9. Cola de trabajo

**Qué** — La lista concreta y ordenada de a quién contactar, cómo y con qué mensaje.

**Cómo** — `contact.py::render_queue` → `gtm/build/queue.md`, también disponible en `/queue` de
la UI. Ordenada por `pain_score` descendente, separada en Llamadas / Formularios / Descartados.

**Para qué** — Decisión de diseño central: **el pipeline prepara, no envía.** A 25 prospectos
por semana, mandar a mano cuesta hora y media, convierte más, y evita de raíz el harvesting de
direcciones (CAN-SPAM agravado) y el SMS en frío (TCPA).

**Palancas** — Ninguna propia — hereda todo de los nodos 7 y 8.

**Problemas conocidos** —

**Bitácora** —

---

### 10. Contacto en frío

**Qué** — El primer contacto humano real: la llamada de apertura.

**Cómo** — Guion de 20 segundos en [`pipeline.md`](../gtm/pipeline.md#guion-de-apertura--llamada-en-frío-20-segundos),
también implementado en `contact.py::build_call_script` — si se retoca uno, retocar el otro.

**Para qué** — Objetivo único: permiso para mandar el link por SMS. No es venta, no es la demo,
no son 20 minutos. Bajar la barrera de entrada al mínimo posible.

**Palancas** — El guion en sí (EN/ES).

**Problemas conocidos** —

**Bitácora** —

---

### 11. Conversación de venta

**Qué** — La llamada de 20 minutos que se agenda después de que respondieron al link.

**Cómo** — Guion de 6 pasos en `pipeline.md`: dejar que el dueño describa cómo le llegan los
trabajos, que él mismo diga qué pasa cuando se le escapa una llamada, cuantificar el valor de un
trabajo típico, cuántas llamadas se le escapan por semana, multiplicar en voz alta delante suyo,
y recién ahí precio/plazo/garantía.

**Para qué** — No es una demo del producto: es confirmar que el dolor existe y que hay
presupuesto. Si el número del paso 5 da menos de USD 950, el prospecto está mal elegido — hay
que volver al discovery, no bajar el precio.

**Palancas** — El guion, las respuestas a objeciones documentadas en `validation.md`.

**Problemas conocidos** —

**Bitácora** —

---

### 12. Entrega

**Qué** — Apuntar el sitio al dominio del cliente y configurar el bot de texto automático.

**Cómo** — Plazo contractual de 48 horas. El bot **no se construye**: se configura un proveedor
existente de AI receptionist / missed-call-text-back (USD 25-50/mes) con la info real del
negocio.

**Para qué** — El margen está en la instalación, no en el software. Construir el bot propio
significa heredar guardias 24/7, incompatible con 5-10 hs semanales.

**Palancas** — Qué proveedor de SMS/bot se usa, el contrato (cláusulas mínimas en `pipeline.md`).

**Problemas conocidos** —

**Bitácora** —

---

### 13. Ledger y decisión

**Qué** — Registrar cada evento del embudo y cada supresión, de forma persistente entre
corridas, y leer contra el criterio pre-registrado.

**Cómo** — `gtm/factory/ledger.py`. `funnel.jsonl` (5 niveles: contacted → replied →
call_booked → proposal_sent → paid) y `suppression.jsonl`, ambos JSONL append-only con solo
hashes SHA-256. El criterio vive en `decision_criteria.yaml` y `tests/gtm/test_ledger_criteria.py`
falla si el código se aparta de esos umbrales.

**Para qué** — Es la única defensa contra el sesgo de "encontrar una lectura que justifica
seguir": ganador = 1 venta cobrada; kill = 200 contactados, 0 ventas, <5 respuestas. El archivo
no se toca durante el experimento — si el criterio resulta mal calibrado, es un resultado, no
un bug.

**Palancas** — Ninguna durante el experimento — es la regla dura. Se ajusta solo entre
experimentos, y con el hash del commit como prueba de que fue antes de ver datos.

**Problemas conocidos** —

**Bitácora** —

---

## Documentos relacionados

- [`gtm/pipeline.md`](../gtm/pipeline.md) — precios, guiones de venta, secuencia, contrato
- [`gtm/decision_criteria.yaml`](../gtm/decision_criteria.yaml) — criterio de kill pre-registrado
- [`gtm/validation.md`](../gtm/validation.md) — investigación de mercado externa, objeciones
- [`gtm/plan_aprendizaje.md`](../gtm/plan_aprendizaje.md) — plan semanal previo, sigue vigente en paralelo
- [`docs/WHY.md`](WHY.md) — por qué home services, por qué USA
- [`docs/CHANNELS.md`](CHANNELS.md) — por qué no hay WhatsApp/Telegram/SMS en frío
- [`docs/PLAN_DIARIO.md`](PLAN_DIARIO.md) — las 20 sesiones para recorrer este mapa
- [`docs/SERVICIOS_FUTUROS.md`](SERVICIOS_FUTUROS.md) — lo que todavía no existe, con plan de implementación
- [`docs/WHATSAPP_BOT.md`](WHATSAPP_BOT.md) — WhatsApp como producto vendible (distinto de WhatsApp como canal de prospección)
