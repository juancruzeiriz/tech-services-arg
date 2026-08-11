# Bot de WhatsApp — análisis de viabilidad como producto

Investigación hecha el 2026-08-11. **No cambia ninguna decisión vigente del pipeline
de prospección** — cubre un hueco que los documentos existentes no trataban.

## La distinción que faltaba

`gtm/pipeline.md` y `gtm/validation.md` descartan WhatsApp, y siguen teniendo razón,
pero sobre **una** pregunta:

> ¿Sirve WhatsApp para que Juan le escriba en frío a un plomero de Houston que no lo
> conoce?

No. La Business API exige plantillas aprobadas y opt-in previo; el envío en frío es
inviable. Esa decisión no se toca.

Este documento trata **otra** pregunta, que no estaba escrita en ningún lado:

> ¿Sirve WhatsApp como producto que Juan le *instala* a un cliente, para que atienda
> a los clientes *de ese cliente*?

Sí, y la economía es mejor de lo esperado. La diferencia no es de matiz: en el caso
descartado el negocio escribe primero a un desconocido (frío, regulado, caro). En
este caso **el cliente final escribe primero al negocio**, lo que abre la ventana de
servicio y genera el opt-in solo. Es el mismo mecanismo, al revés, y el revés es
legal, barato y esperado por el usuario.

## Casos de uso, por oficio

Los oficios ya están clasificados por `urgency` en
[`gtm/catalog/trades.yaml`](../gtm/catalog/trades.yaml), y ese campo predice bastante
bien qué le sirve a cada uno. No es el mismo producto para todos.

### Urgencia alta — el bot vende velocidad

`hvac` (ticket 2.434), `plumber` (1.708), `garage_door` (500), `locksmith` (200).

El cliente final tiene una urgencia y está escribiendo a tres negocios a la vez. Gana
el que contesta primero. Es exactamente el argumento del one-pager actual
([`offers/website-call-capture.md`](../gtm/offers/website-call-capture.md)) — "the
caller does not leave a voicemail, they call the next name on the list" — pero por el
canal donde el cliente hispano ya está.

Qué hace el bot: confirma que el mensaje llegó en segundos, pregunta las 3 cosas que
determinan si el trabajo se puede tomar (qué pasó, dónde, cuándo), y le avisa al
dueño. No cotiza ni promete horario: filtra y retiene mientras el dueño está abajo de
una pileta.

### Urgencia media — el bot califica

`roofing` (9.500), `electrician` (750), `pest_control` (375), `appliance_repair` (325),
`tree_service` (1.800).

Acá el cliente compara y tarda. El valor no es la velocidad sino no perder el lead
entre el primer mensaje y la visita. El bot toma los datos, manda el rango de precio
típico si el dueño lo definió, y agenda la visita de diagnóstico.

`roofing` merece atención aparte: con ticket promedio de 9.500 es el oficio donde un
solo lead recuperado paga el servicio de un año entero.

### Urgencia baja — el bot agenda y recuerda

`painter` (2.800), `fencing` (2.500), `landscaping` (900), `gutters` (800),
`pool_service` (450, **recurrente**), `junk_removal` (300).

Casi no hay urgencia, así que contestar en 5 segundos no cambia nada. Lo que sí
cambia: recordatorios de visita y, en `pool_service`, el servicio recurrente. Es el
único caso donde conviene mandar mensajes **proactivos** (fuera de la ventana de 24 h),
que son los únicos que se pagan — y aun así, a 0,004 USD cada uno.

## Qué se necesita

Requisitos de Meta, verificados contra su documentación y guías de proveedores
(fuentes al final):

| Requisito | Detalle | De quién es |
|---|---|---|
| Meta Business Portfolio | Cuenta de negocio activa | Del cliente |
| Verificación de negocio (Meta Business Verification) | Revisión de Meta, 2-4 días hábiles | Del cliente |
| Número de teléfono | **No puede estar activo en un WhatsApp personal**. Si lo está, hay que darlo de baja primero | Del cliente |
| Nombre para mostrar aprobado | Debe coincidir exactamente con cómo aparece la marca en su sitio web. 1-3 días hábiles de revisión | Del cliente |
| **Un sitio web funcionando** | El nombre para mostrar **no se aprueba sin un sitio verificable** en el portfolio de Meta | ← ver abajo |
| Endpoint HTTPS para el webhook | Recibe los mensajes entrantes | De Juan |
| Método de pago | Aunque el uso previsto sea gratis, la cuenta lo pide | Del cliente |

### El hallazgo que cambia el orden de venta

**Meta no aprueba el nombre para mostrar sin un sitio web funcionando y verificado.**

Eso convierte al paquete actual de 950 USD en un **prerequisito técnico** del bot, no
en un producto que compite con él. La secuencia natural de venta deja de ser una
elección entre dos productos y pasa a ser una escalera:

1. Sitio (950 USD) — necesario para que exista el paso 2
2. Bot de WhatsApp — se le vende a quien ya compró el paso 1

El prospecto ideal del bot es un cliente que ya pagó. No hay que salir a buscarlo.

**Plazo:** la mediana de alta es de 3-5 días hábiles, con la verificación de negocio
como cuello de botella. El bot **no** entra en la promesa de "live in 48 hours" del
one-pager actual. Se vende y se promete aparte.

## Costos

Meta pasó a cobro **por mensaje** el 2025-07-01. Categorías y tarifas de Norteamérica
(junio 2026):

| Categoría | Tarifa | Cuándo aplica |
|---|---|---|
| **Servicio** (respuesta dentro de la ventana de 24 h) | **Gratis, sin tope mensual** | Todo lo que conteste el bot cuando el cliente escribió primero |
| Utility (plantilla) | 0,004 USD | Recordatorio de visita, confirmación — solo **fuera** de la ventana |
| Authentication | 0,004 USD | No aplica a este caso |
| Marketing | 0,025 USD | Promociones. No aplica, y conviene que siga sin aplicar |

La documentación de Meta lo confirma textualmente: *"All non-template messages are
free"* dentro de la ventana de servicio, y las plantillas de utility también son
gratis si la ventana está abierta.

**Consecuencia económica:** el caso de uso principal —el bot contestando a quien
escribió— **no tiene costo por mensaje**. La ventana además se reinicia cada vez que
el cliente vuelve a escribir.

### Costo real por cliente, por mes

| Ítem | Costo estimado |
|---|---|
| Mensajes de servicio | 0 USD |
| Plantillas utility (recordatorios) | ~0,40 USD por cada 100 recordatorios |
| Hosting del webhook | 0 USD en el plan gratuito de Cloudflare Workers (ya en el stack) |
| Base de datos | 0 USD en el plan gratuito de Supabase (ya en el stack) |
| Modelo de IA, si se usa | Variable — ver "Build vs. buy" |

El costo marginal de un cliente adicional tiende a cero. Es un servicio recurrente de
margen muy alto, que es exactamente lo que le falta al paquete de pago único actual.

**Advertencia:** las tarifas cambian y varían por país. Antes de comprometer un precio,
hay que bajar el número vivo del rate card de Meta para el país del destinatario.

## Build vs. buy

`gtm/pipeline.md:32` ya fijó una regla para el missed-call-text-back: **"El bot no se
construye. Se configura un proveedor existente."** El razonamiento —no heredar
guardias 24/7 con 5-10 hs semanales— sigue siendo válido y se aplica igual acá.

Pero hay una diferencia que justifica revisarlo más adelante: el missed-call-text-back
es un commodity (responde siempre lo mismo), mientras que un bot que cotiza según los
parámetros del oficio es lógica propia. Recomendación en dos tiempos:

- **Primer cliente: comprar.** Configurar un proveedor existente. Se aprende el
  problema real con dinero de otro y sin construir nada. Si el cliente se va, no se
  perdió trabajo de desarrollo.
- **A partir del tercero: evaluar construir** sobre Cloud API directo. El stack ya
  está (Cloudflare Workers para el webhook, Supabase para el estado), el costo de
  mensajes es cero, y ahí el margen del proveedor pasa a ser margen propio. No antes:
  construirlo para un cliente hipotético es exactamente lo que este proyecto evita.

Sobre la IA en el bot: un flujo determinista (menú, preguntas fijas, reglas de
cotización que define el dueño) es más barato, más predecible y más fácil de explicar
en la venta que un LLM suelto. Un LLM conviene como *fallback* para lo que el flujo no
cubre, no como la primera capa. Además hereda la regla dura que ya existe en
[`copy_ai.py`](../gtm/factory/copy_ai.py): nunca inventar hechos del negocio — un bot
que promete un horario o un precio que el dueño no autorizó es un pasivo, no un
producto.

## Arquitectura, si se construye

Encaja con lo que ya corre, sin dependencias nuevas:

```
Cliente final (WhatsApp)
   ↓
Meta Cloud API
   ↓  webhook POST
Cloudflare Worker  ← mismo patrón que cloudflare/functions/v/[token].js
   ↓
Supabase (Postgres)  ← estado de conversación, reservas, RLS igual que subscribers
   ↓
Notificación al dueño (WhatsApp / SMS / mail)
```

El multi-cliente es el punto no resuelto: cada negocio necesita su propia WABA,
su propio número y su propia verificación. Onboardear clientes a mano no escala.
Meta tiene un camino de **Tech Provider con Embedded Signup** para esto — es lo que
hay que investigar antes del tercer cliente, no ahora.

## Qué NO sabemos todavía

Honestidad sobre los límites de esta investigación:

- **Si alguien lo va a pagar, y cuánto.** Nada acá lo prueba. Es la misma trampa que
  `decision_criteria.yaml` existe para evitar: una idea que suena bien no es demanda.
- **Adopción real de WhatsApp entre clientes finales de oficios en USA.**
  `validation.md` tiene el dato de contexto (~32% de adultos en USA, empujado por
  comunidades inmigrantes) pero no segmentado por quien contrata un plomero.
- **Si el dueño hispano prefiere WhatsApp o SMS** para su negocio en USA. Es una
  pregunta de entrevista, no de escritorio.
- **El costo de soporte real.** Un bot que atiende clientes es una superficie de
  reclamo nueva: si contesta mal, el que queda mal es el dueño.

## Cómo se validaría, barato

Sin construir nada, dentro de la Fase B del plan diario:

1. Agregar una pregunta a las entrevistas de problema: *"¿Tus clientes te escriben por
   WhatsApp? ¿Cuántos por semana? ¿Cuántos se te pierden?"* Costo: cero.
2. Si tres de cinco dicen que sí y que se les pierden, recién ahí armar el alta de una
   WABA de prueba con el número propio y medir el flujo real punta a punta.
3. Precio: no inventarlo acá. Sale del piso por hora que ya calcula
   [`gtm/ui/routes/pricing.py`](../gtm/ui/routes/pricing.py) más el costo mensual real
   medido en el paso 2.

## Fuentes

- [Pricing on the WhatsApp Business Platform — Meta for Developers](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing)
- [WhatsApp Cloud API Get Started — Meta for Developers](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started)
- [About WhatsApp Business Display Name — Meta Business Help Center](https://www.facebook.com/business/help/338047025165344)
- [WhatsApp Business API Pricing in 2026: Conversation Categories, Costs, and What Changed](https://blueticks.co/blog/whatsapp-business-api-pricing-2026)
- [WhatsApp 24-Hour Session Window: Rules, Costs & Support Ops Guide (2026)](https://ominiflow.com/blog/whatsapp-24-hour-session-window)
- [WhatsApp API Prerequisites: Phone, Documents, and Verification](https://www.wati.io/en/blog/whatsapp-api-prerequisites/)
