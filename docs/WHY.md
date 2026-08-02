# Por qué este proyecto — y por qué así

Este documento responde tres preguntas que no están consolidadas en ningún otro lugar
del repo: qué es exactamente lo que se ofrece, por qué Estados Unidos, y por qué oficios.
El resto de la documentación explica *cómo* funciona el pipeline; esto explica *por qué*
tiene la forma que tiene.

---

## 1. Qué es esto, en una frase

**Vos, developer, le ofrecés a un negocio de oficio en USA (un plomero, un técnico de
HVAC) una digitalización que ya está hecha**: un sitio web con sus datos reales y un
sistema de respuesta automática a llamadas perdidas, publicado antes de que el negocio
sepa que existís.

Lo inusual no es la oferta —sitio web + captura de leads es un servicio viejo—, es el
**orden**: normalmente vendés primero y construís después. Acá se invierte porque el
recurso que falta (confianza, marca, historial) no se puede comprar con plata ni
generar rápido, pero el recurso que sobra (velocidad de producción con IA) sí puede
generar el sustituto: un artefacto terminado que reemplaza la credencial que no tenés.

La aritmética completa de por qué se llegó a este modelo —y por qué la alternativa
obvia (anunciar y esperar) se descartó por cálculo, no por preferencia— está en
[`gtm/README.md`](../gtm/README.md#por-qué-existe).

---

## 2. Por qué Estados Unidos

Hay una razón de fondo y dos secundarias. La de fondo es legal, no cultural, y es la
que en realidad decide todo lo demás.

### La razón que manda: el contacto en frío es legal en USA y no en Europa

Todo el modelo depende de poder escribirle o llamar a un negocio que no te pidió nada.
Eso tiene un nombre legal —*outbound B2B en frío*— y su legalidad cambia radicalmente
según la jurisdicción:

| | USA (CAN-SPAM) | Europa (GDPR) |
|---|---|---|
| Contacto B2B sin consentimiento previo | **Permitido**, con reglas de forma | **Prohibido** salvo base legal específica |
| Qué exige | Remitente real, asunto no engañoso, dirección postal, opt-out honrado en ≤10 días hábiles | Consentimiento previo o interés legítimo demostrable, con carga de prueba sobre quien contacta |
| Consecuencia para este modelo | El pipeline es legal tal como está diseñado | El mismo pipeline sería una infracción desde el primer email |

Esto no es un detalle de compliance que se resuelve leyendo la letra chica: es la
condición de existencia del proyecto. Si el mercado elegido fuera Europa, "generar y
enviar demos no solicitadas" no sería una estrategia agresiva de ventas, sería ilegal
por diseño. USA es el mercado grande de habla inglesa donde el mecanismo central del
proyecto —tocar la puerta sin que te inviten— está permitido.

El detalle técnico de cómo el código hace cumplir esto (validación de CAN-SPAM al
construir cada email, antes de que exista) está en
[`gtm/README.md`](../gtm/README.md#reglas-que-el-código-hace-cumplir).

### Razones secundarias

- **Se cobra en USD, no en pesos.** El ticket (USD 950 + recurrente) se exporta como
  servicio desde Argentina: Factura E, exenta de IVA, sin derechos de exportación
  vigentes, y no computa contra el límite de facturación del monotributo (ver
  [`gtm/pipeline.md`](../gtm/pipeline.md#riesgos)). El arbitraje cambiario no es el
  motivo del proyecto, pero es lo que hace que el mismo trabajo rinda mucho más ahí
  que vendido en el mercado local.
- **El inglés técnico-comercial de USA es más fácil de automatizar de forma creíble**
  que el español rioplatense de un cliente argentino, que detecta un mensaje
  "traducido" al toque. Un email en inglés con datos reales del negocio no delata el
  origen del remitente.

---

## 3. Por qué oficios (home services)

El vertical no es plomeros por casualidad ni por ser el ejemplo más fácil de imaginar.
Cuatro condiciones tienen que darse a la vez, y los oficios de home services (plomería,
HVAC, electricidad, techado) las cumplen todas simultáneamente. Ningún otro tipo de
negocio chico las cumple todas a la vez:

### a. El trabajo vale plata real

Un service de HVAC factura entre USD 300 y USD 15.000 por trabajo. Un sitio de
USD 950 es un gasto trivial frente a eso — no hay que convencer a nadie de que el
presupuesto existe, solo de que vale la pena gastarlo en esto.

### b. El dolor es un hecho, no un argumento

"Perdiste esta llamada" o "tu sitio tarda 8 segundos en cargar en el celular" son
verificables por el propio prospecto en su propio teléfono, en su propio navegador,
sin tener que creerte nada. Eso es lo que hace que el "artefacto antes que la venta"
funcione: el mensaje no pide fe, pide que abras un link.

### c. El mercado está desatendido, y por una razón estructural

Las agencias de marketing digital no bajan a este ticket: su costo de adquisición no
cierra vendiendo sitios de menos de USD 2.000. Los oficios quedan en un punto ciego —
tienen plata para pagar, pero nadie los ataca a ese precio — que es exactamente el
hueco que este modelo explota.

### d. El servicio no se puede deslocalizar, así que no compite por precio

Esta es la condición menos obvia y la más importante. Un plomero de Tucson **no puede
comprar** su servicio de plomería a alguien en Manila o en Bangalore — el trabajo se
hace físicamente en su casa. Eso significa que la venta del sitio web tampoco se cierra
comparando precios contra un freelancer más barato de otro país: se cierra por
**confianza y urgencia local**. Un desarrollador remoto compite mundialmente contra
cualquiera que sepa programar; un servicio atado a la geografía del cliente no. Esa
asimetría es la que permite cobrar USD 950 por un producto que en tiempo de desarrollo
cuesta mucho menos.

Explícitamente evitados: salud (HIPAA agrega una capa regulatoria que no vale la pena
para el ticket) y servicios legales (mismo motivo). Ver
[`gtm/pipeline.md`](../gtm/pipeline.md#la-oferta).

---

## 4. Lo que sigue siendo una simulación, no una decisión

HVAC en Tucson, AZ fue el par elegido para **probar que el pipeline funciona**, no una
conclusión de que sea el mejor par posible. La elección real del oficio y la ciudad
—dentro de las cuatro condiciones de la sección 3— es una decisión de negocio que el
código no puede tomar por vos, y que todavía está pendiente.
