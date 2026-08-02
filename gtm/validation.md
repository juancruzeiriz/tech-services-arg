# Validación de mercado — antes de gastar las 8 semanas

Investigación externa hecha porque ninguno de los dos conocía el terreno de home
services en USA. **No reemplaza el experimento pre-registrado en
[`decision_criteria.yaml`](decision_criteria.yaml)** — reduce el riesgo de que la
categoría entera esté mal elegida antes de gastar las 200 llamadas en probarlo.

## El problema es real y medido, no solo intuido

| Fuente | Dato |
|---|---|
| [Jobber, 2026 Home Service Trends Report](https://www.getjobber.com/home-service-trends-report/) (n=1.050 dueños, encuestados dic-2025) | **45-56% de contratistas/oficios sin sitio web** — la categoría con peor adopción digital de todas, contra ~27% del promedio de pequeños negocios en USA |
| [b2bleadfinder.io](https://b2bleadfinder.io/blog/small-business-without-website-statistics) | El promedio general de pequeños negocios sin sitio bajó de 36% (2020) a 27% (2026) — los oficios no siguieron esa curva |

**Cruce con `simulate.py`:** el simulador asume 20% `NONE` + 15% `SOCIAL_ONLY` = 35%
sin sitio propio. La encuesta de Jobber sugiere 45-56%. Puede que
`_PRESENCE_WEIGHTS` en [`factory/simulate.py`](factory/simulate.py) esté siendo
optimista — vale recalibrarlo con datos reales de Places antes de tratar los
resultados del simulador como representativos, no solo como fixture para probar
el pipeline.

## Ya hay quien cobra por esto — señal de demanda, y de competencia

Existen agencias activas vendiendo paquetes de sitio + marketing específicamente a
contratistas (páginas tipo GoHighLevel con el pitch "We build websites & marketing
systems for contractors"). Lectura en dos sentidos: confirma que hay disposición a
pagar, pero también que el nicho no es un secreto — la diferenciación de
`offers/website-call-capture.md` (precio fijo, sin retainer, demo ya publicada
antes de vender) importa más de lo que parece.

## Resistencia real, no hipotética

En Reddit (r/Contractor, r/electricians, r/handyman) hay un debate activo y
dividido sobre si un sitio web hace falta. La objeción dominante de operadores
chicos es literalmente **"consigo el 99% de mi trabajo por referidos, no necesito
sitio web."**

Esto no es evidencia de que la estrategia falle — es la objeción exacta que hay
que esperar en la llamada. Ya tiene respuesta preparada en la sección
"Objeciones esperadas" de [`pipeline.md`](pipeline.md): la oferta no compite
con los referidos, cubre las llamadas que se pierden mientras están
trabajando.

## Validación institucional de terceros

Asociaciones reales, no genéricas, con la misión explícita de cerrar la brecha de
digitalización/negocio en contratistas hispanos — útiles como canal de
*descubrimiento cualitativo* (leer sus publicaciones, eventualmente escribirles),
no como canal de venta en frío:

- [National Hispanic Contractors Association (NAHICA)](https://nahica.org/)
- [Latin Builders Association](https://www.lbaorg.com/) (desde 1971)
- [Hispanic American Construction Industry Association (HACIA)](https://www.haciaworks.org/) (desde 1979)
- [Regional Hispanic Construction Association](https://regionalhca.org/)
- [National Hispanic Construction Alliance (NHCA)](https://nhca.pro/)

Grupos de Facebook en español para oficios en USA existen (ej. "Plomeros en
USA"), pero cambian de nombre y se mezclan con resultados de México/Argentina en
cualquier búsqueda — no se listan acá como fuente fija; conviene rebuscarlos al
momento de necesitarlos.

## WhatsApp: dato de contexto, no parte de la oferta

La adopción de WhatsApp Business en pequeños negocios de Latinoamérica pasó de
22% a 45% entre 2023-2025, y el uso de WhatsApp en USA general creció "impulsado
por comunidades inmigrantes" (~32% de adultos de EE.UU. en 2025). Es un dato de
contexto real, pero **no cambia la decisión ya tomada**: `pipeline.md` descarta
WhatsApp para prospección porque la Business API exige plantillas aprobadas y
opt-in previo — el envío en frío es inviable. La oferta vigente es sitio estático
+ missed-call text-back por **SMS**, no un bot de WhatsApp. Si el planteo inicial
del proyecto mencionaba WhatsApp, Google Maps administrado o un sistema de
cobros propio: ninguno de los tres está en el paquete actual (ver
[`offers/website-call-capture.md`](offers/website-call-capture.md)).

## Qué NO responde esta investigación

Si tu redacción, tu precio o tu metro/oficio elegido convierten. Eso solo lo mide
`decision_criteria.yaml` con datos reales. Esta nota solo baja el riesgo de que
la categoría entera esté mal elegida — no es un sustituto de las 200 llamadas.

## Fuentes

- [Blue Collar Strong: The 2026 Home Service Trends Report](https://www.getjobber.com/home-service-trends-report/)
- [How Many Small Businesses Don't Have a Website? 2026 Statistics & Data](https://b2bleadfinder.io/blog/small-business-without-website-statistics)
- [WhatsApp in the U.S.: Usage, Adoption Trends & Business Growth](https://sleekflow.io/en-us/blog/whatsapp-in-us-trends)
- [Adoption of WhatsApp Business in Latin America: Figures by Country](https://www.aurorainbox.com/en/2026/03/05/adopcion-whatsapp-business-latam/)
- [National Hispanic Contractors Association (NAHICA)](https://nahica.org/)
- [Latin Builders Association](https://www.lbaorg.com/)
- [Hispanic American Construction Industry Association (HACIA)](https://www.haciaworks.org/)
- [Regional Hispanic Construction Association](https://regionalhca.org/)
- [National Hispanic Construction Alliance (NHCA)](https://nhca.pro/)
