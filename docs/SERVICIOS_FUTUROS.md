# Servicios futuros — plan de implementación

Inventario de todo lo que se pensó para este proyecto y **todavía no existe**, con un
plan concreto para cada cosa. Escrito el 2026-08-11.

## Para qué sirve este documento

No es un backlog para ir tachando en orden. Es un documento de **preparación**: que si
mañana un cliente pide cualquiera de estas cosas, la respuesta sea "sí, dame N días" y
no "déjame pensarlo". Cada ficha tiene lo mínimo para arrancar sin volver a investigar
desde cero.

**Regla que sigue en pie:** nada de esto se construye antes de la primera venta cobrada
del paquete base. `decision_criteria.yaml` fija ese experimento y este documento no lo
altera — un servicio de upsell para clientes que todavía no existen es exactamente el
trabajo que ese archivo existe para frenar. Preparar no es construir.

## Estado de cada cosa

| # | Servicio | Estado | Depende de |
|---|---|---|---|
| 1 | Envío de mails a suscriptores | **Hueco activo** — el botón junta emails sin destino | Nada |
| 2 | Proveedor de missed-call-text-back | **Investigado (2026-08-13)** — Enzak, precio en conflicto de fuentes (USD 20 o 99/mes), mantiene el número real del cliente. Faltan 3 datos y la alta real | Nada |
| 3 | Bot de WhatsApp | Analizado — ver [`WHATSAPP_BOT.md`](WHATSAPP_BOT.md) | Sitio del cliente (prerequisito de Meta) |
| 4 | Sistema de reservas | No empezado | Primera venta |
| 5 | Calculadora de precio para el cliente | No empezado | Primera venta |
| 6 | Optimización de rutas | No empezado | Varios clientes con volumen |
| 7 | Facturación / OCR | No empezado | Primera venta |
| 8 | CRM con IA | No empezado | Cartera real |
| 9 | Mantenimiento predictivo | **Descartado** — ver ficha | — |
| 10 | Asistente de diagnóstico IA | **Descartado por ahora** — ver ficha | — |
| 11 | Grupos de Facebook | Investigación pendiente | Nada |

Los dos primeros son incoherencias del sistema actual, no features nuevas. Van primero
porque el costo de dejarlos así ya se está pagando.

---

## 1. Envío de mails a suscriptores — HUECO ACTIVO

**Problema:** `/api/subscribe` guarda emails en `subscribers` y nada los usa. La tabla
crece sin destinatario. Además el formulario promete "avisos ocasionales", así que hay
una promesa hecha y no cumplida.

**Lo que ya existe:** `gtm/send/` completo (SMTP, outbox, bounces, worker con jitter,
gate CAN-SPAM probado en CI). El motor de envío está construido y testeado.

**Lo que falta:** el puente entre la tabla y ese motor, y —más difícil— **decidir qué
mandar**. El problema real no es técnico.

**Plan:**
1. Decidir la promesa concreta: frecuencia y contenido. Sin esto lo demás no importa.
2. Double opt-in real. La columna `confirmed_at` ya existe en
   [`0005_subscribers.sql`](../gtm/store/schema/0005_subscribers.sql) esperando esto.
   Sin confirmación, un alta falsa con el mail de otro te ensucia la reputación de envío.
3. Baja funcionando antes del primer envío. `GTM_UNSUBSCRIBE_URL` ya está en el entorno
   pero apunta a `example.com` — hoy no existe.
4. Recién ahí conectar `gtm/send/worker.py` leyendo de `subscribers`.

**Costo:** cero en infraestructura (ya está todo). El costo es de decisión y de tiempo.

**Riesgo legal:** CAN-SPAM aplica. El gate ya está en CI (`test_outreach.py -k canspam`)
pero está escrito para el pipeline de prospección, no para una lista de suscriptores —
hay que verificar que cubra este caso también.

**Alternativa honesta:** si no hay nada concreto que mandar en los próximos 60 días,
sacar el formulario. Una lista que nunca recibe nada es peor que no tenerla: quema la
dirección y la confianza de quien se anotó.

---

## 2. Proveedor de missed-call-text-back — HUECO ACTIVO

**Problema:** [`offers/website-call-capture.md`](../gtm/offers/website-call-capture.md)
lo vende como parte del paquete de 950 USD, y `PROCESOS.md` (Nodo 12) lo tiene como paso
de entrega — pero no hay ningún proveedor elegido. Si mañana alguien paga, hay 48 horas
para resolverlo con el reloj corriendo.

**Decisión ya tomada:** se configura, no se construye
([`pipeline.md:32`](../gtm/pipeline.md)).

**Plan (una sesión, 45 min):**
1. ✅ Elegir 3 candidatos de AI receptionist / missed-call-text-back que operen en USA.
2. ✅ Comparar: precio real, si permite reventa o cuenta por cliente, cuánto tarda el alta,
   si el número puede ser del cliente, y qué pasa si el cliente se va.
3. ⏳ Dar de alta uno con el número propio y probarlo de punta a punta llamando y cortando
   — pendiente: implica un compromiso de pago mensual real, no se hace sin confirmar.
4. ⏳ Escribir el procedimiento de alta en la ficha del Nodo 12 de `PROCESOS.md`.

**Comparación (2026-08-13):**

| Proveedor | Precio | ¿Usa el número real del cliente? |
|---|---|---|
| [Enzak](https://enzak.com/) | **En conflicto** — ver nota abajo | **Sí** — se integra al sistema telefónico existente, sin número nuevo |
| [OpenPhone/Quo](https://www.openphone.com/features/missed-call-service) | USD 15-23/usuario/mes | No directo — dan número nuevo, o exigen portar el número (cambia de operador) |
| Rango de mercado general | USD 40-120/mes típico | Varía |

**Precio de Enzak: dato en conflicto de fuentes, no resuelto todavía.**
[enzak.com](https://enzak.com/) (fuente primaria, consultada 2026-08-13) publica
**USD 20/mes** (primer mes USD 4, 1.000 mensajes/mes, analytics incluido, usuarios extra
USD 10/mes). Una búsqueda posterior tomó como firme un número de
[el blog de Quo/OpenPhone](https://www.quo.com/blog/missed-call-text-back-software/) —
un **competidor directo** de Enzak, no la fuente primaria — que decía USD 99/mes + USD 99
de alta, y ese fue el número que quedó escrito acá y en `pipeline.md:32`. No hay forma de
saber cuál es correcto sin llamar a Enzak (precio real vs. precio que le conviene citar a
un competidor). **No usar ninguno de los dos como dato firme hasta la llamada de alta
(paso 3, abajo).**

**Tres preguntas que decide la llamada de alta gratuita**, ninguna respondida por lo
investigado hasta ahora:

1. **¿Cuánto tarda el alta?** Sin este dato, "live in 48 hours" del one-pager
   (`offers/website-call-capture.md`) es una apuesta, no una promesa verificada.
2. **¿Desde qué número sale el SMS automático?** — la que más importa. Enzak confirma que
   el negocio **recibe** las llamadas en su número de siempre (asigna un número virtual
   "detrás de escena" para el forward), pero no dice desde qué número sale el *texto* de
   vuelta. Si sale desde el número virtual, el que llamó recibe un mensaje de un número que
   no reconoce — el mismo problema de confianza que este producto viene a resolver.
3. **¿Qué pasa si el cliente se va?** (¿se queda con el flujo armado o hay que revertir el
   forward?).

**Dato bueno confirmado, no en conflicto:** Enzak **registra el A2P 10DLC por vos** — el
cliente no necesita registrar su propia marca ni pagar el vetting. Eso saca de encima el
bloqueante regulatorio que documenta [`CHANNELS.md`](CHANNELS.md#4-sms--no-se-implementa)
(los carriers de USA bloquean el 100% del tráfico A2P no registrado desde febrero de 2025)
— nota: ese bloqueante es para SMS en frío de prospección, que este proyecto ya descartó;
acá aplica al SMS *saliente al cliente final* del bot, que es un caso distinto y donde este
dato sí es una ventaja real de Enzak.

**Salida:** un proveedor candidato, sin precio confirmado ni las 3 preguntas de arriba
resueltas. Falta el paso 3 (alta real, requiere decidir pagar la suscripción) antes de
poder cerrar este ítem — y el paso 3 es también la única forma de resolver el precio real.

---

## 3. Bot de WhatsApp

Analizado en detalle en [`WHATSAPP_BOT.md`](WHATSAPP_BOT.md). Resumen:

- Los mensajes de respuesta dentro de la ventana de 24 h **no se cobran**, así que el
  costo marginal por cliente tiende a cero.
- Meta exige un sitio web funcionando para aprobar el nombre para mostrar: **el paquete
  de 950 USD es un prerequisito técnico del bot**, no un competidor.
- Alta de 3-5 días hábiles, así que no entra en la promesa de 48 horas.
- Primer cliente: configurar un proveedor. A partir del tercero: evaluar Cloud API propio.

---

## 4. Sistema de reservas

**Idea original:** *"una app o página de reservas donde los clientes reservan días para
que el trabaje, así se despierta y sabe cuántos trabajos tiene."*

**Lectura crítica:** el planteo asume que el cliente final va a entrar a una web a
elegir un día. Para `urgency: high` (plomero, cerrajero, HVAC) eso es dudoso — el que
tiene un caño roto llama, no reserva. Donde sí cierra es en `urgency: low` y sobre todo
en `pool_service`, que el catálogo ya marca como **recurrente**: visitas programadas,
mismo cliente, todas las semanas.

**Encaje:** es la mitad natural del bot de WhatsApp, no un producto aparte. El cliente
escribe, el bot toma la reserva, la reserva aparece en el calendario del dueño. Venderlo
suelto es venderle a un oficio una agenda web que ya tiene en papel.

**Stack:** Supabase para las reservas (mismo patrón de RLS que `subscribers`),
Cloudflare Workers para la API, y una vista web mínima. Todo ya está en el proyecto.

**Lo no resuelto:** la sincronización con el calendario que el dueño ya usa (Google
Calendar). Sin eso son dos agendas y va a mirar la de siempre. Con eso, es integración
con OAuth de Google, que es trabajo real.

**Prerequisito:** una entrevista con un dueño de oficio preguntando cómo maneja hoy su
agenda. Si contesta "en un cuaderno" o "en la cabeza", el producto es distinto del que
se está imaginando.

---

## 5. Calculadora de precio para el cliente

**Idea original:** *"una app que analice cuánto tiene que cobrar por cada trabajo."*

**Ojo con la confusión:** ya existe [`gtm/ui/routes/pricing.py`](../gtm/ui/routes/pricing.py),
pero calcula el piso por hora **de Juan**, con los costos y horas del proyecto. No sirve
para un plomero: sus costos son camioneta, nafta, seguro, licencia, materiales y ayudante.
Es otro modelo, no una adaptación.

**Lo difícil no es la aritmética.** La fórmula es conocida (costos fijos + variables +
margen ÷ horas facturables). Lo difícil es que el dueño cargue sus números reales, que
en general no tiene ordenados. Una calculadora vacía no se usa dos veces.

**Camino más corto que funciona:** en vez de una app, una plantilla precargada con los
valores típicos del oficio y del metro, que el dueño ajusta. `trades.yaml` ya tiene
`avg_ticket_usd` por oficio como punto de partida.

**Advertencia:** decirle a alguien cuánto cobrar es una recomendación de negocio con
consecuencias. Si el número está mal y pierde plata, el responsable es el que armó la
herramienta. Conviene que muestre el razonamiento, no solo el resultado.

---

## 6. Optimización de rutas

**Idea original:** *"una app que tome todas las direcciones y ordene automáticamente la
ruta en auto para ahorrar costos de nafta"*, y después *"en tiempo real usando IA y
datos de tráfico."*

**Realidad del problema:** es el Travelling Salesman Problem con ventanas de tiempo. No
hace falta resolverlo desde cero — la Routes API de Google lo hace, y Google Maps ya
optimiza paradas gratis para volúmenes chicos.

**La pregunta que decide todo:** ¿cuántas paradas por día tiene el cliente? Con 3-5
visitas —que es lo típico de un plomero o un HVAC— el ahorro de optimizar es de minutos
y el dueño ya conoce su ciudad mejor que el algoritmo. Recién con 10+ paradas diarias
(pest control, pool service, landscaping en temporada) el problema es real.

**Conclusión:** producto válido solo para los oficios recurrentes de alto volumen, que
son justo los de ticket más bajo (`pool_service` 450, `pest_control` 375). Vender un
ahorro de nafta a quien factura poco por visita es una venta difícil.

**No investigar más hasta** tener un cliente que diga cuántas paradas hace por día.

---

## 7. Facturación y OCR

**Idea original:** *"automatizar la facturación y el procesamiento de pagos mediante
reconocimiento óptico de datos."*

**Separar dos cosas que no son la misma:**

- **Emitir facturas al cliente final:** territorio de QuickBooks, Jobber, Housecall Pro.
  Compiten con software maduro, integrado con impuestos estatales de USA. No entrar.
- **Digitalizar comprobantes de gasto (OCR):** nicho más chico y real —el dueño junta
  tickets de materiales en la guantera— pero también resuelto por apps de contabilidad.

**Riesgo específico:** tocar impuestos de otro país sin ser contador ahí. Un error en un
sales tax estatal es problema del cliente y responsabilidad de quien armó el sistema.

**Recomendación: no hacerlo.** Es el ítem de peor relación entre esfuerzo, riesgo y
diferenciación de toda la lista. Si un cliente lo pide, la respuesta correcta es
recomendarle QuickBooks y cobrar por configurárselo.

---

## 8. CRM con IA

**Idea original:** *"un sistema de gestión de relaciones con clientes con IA que sugiera
seguimientos personalizados y prediga la demanda."*

**Lo que ya está construido, para Juan:** `gtm/store/` + `gtm/ui/` son exactamente eso
—prospectos, estados, funnel, cohortes, economía— para el pipeline propio. El modelo de
datos y los dashboards existen.

**Lo que sería para el cliente:** el mismo concepto con otras entidades (sus clientes,
sus trabajos, su recurrencia). No es reutilizable directo, pero el aprendizaje sí.

**Sobre la parte de "predecir la demanda":** con los datos de un solo negocio chico no
hay volumen para predecir nada. Lo que sí funciona sin IA: recordatorios por
estacionalidad, que el catálogo ya conoce (`hvac` en verano, `gutters` en otoño,
`pool_service` en temporada). Llamarlo IA sería marketing, no producto.

**Camino realista:** un recordatorio de re-contacto estacional, dentro del bot de
WhatsApp, para el oficio recurrente. No un CRM.

---

## 9. Mantenimiento predictivo — DESCARTADO

**Idea original:** *"un algoritmo para predecir cuándo va a fallar una herramienta o un
vehículo."*

**Por qué no:** requiere telemetría del vehículo o de la herramienta (sensores, OBD-II)
y un histórico de fallas para entrenar. Un plomero con una camioneta no genera ese dato,
y no hay forma de obtenerlo sin hardware. Sin datos no hay modelo, por más que se lo
llame predictivo.

**Lo único viable sin datos** —un recordatorio de service cada X kilómetros o meses— no
es predicción, es un calendario, y ya existe en cualquier app de mantenimiento.

**Se descarta.** Si alguna vez aparece, sería comprando un producto de telemetría de
flota existente, no construyendo.

---

## 10. Asistente de diagnóstico IA — DESCARTADO POR AHORA

**Idea original:** *"un asistente virtual con IA que ayude al técnico a diagnosticar
problemas antes de llegar."*

**El problema de fondo:** el usuario sería un plomero con 20 años de oficio. Un LLM
diagnosticando por él es, en el mejor caso, redundante, y en el peor, un error caro con
responsabilidad civil. Un diagnóstico equivocado en gas o electricidad no es un bug.

**La versión que sí serviría** no es diagnóstico sino **triage**: preguntarle al cliente
final las 4 cosas que determinan si el trabajo se puede tomar y qué herramienta llevar.
Eso ya está contemplado en el bot de WhatsApp, y ahí el que decide sigue siendo el
técnico.

**Se descarta como producto propio**; sobrevive como una función del bot.

---

## 11. Grupos de Facebook

**Idea original:** buscar comunidades de contratistas en USA, participar genuinamente,
compartir casos de éxito.

**Lo que ya se sabe:** [`validation.md:57`](../gtm/validation.md) confirma que existen
(ej. "Plomeros en USA") pero que cambian de nombre y se mezclan con resultados de México
y Argentina, así que no se listaron como fuente fija.

**Encaje real:** es un canal de **descubrimiento cualitativo**, no de venta. Sirve para
las entrevistas de problema de `plan_aprendizaje.md` —leer de qué se quejan, con qué
palabras— no para publicar ofertas. Casi todos esos grupos prohíben la promoción, y
quemarse en uno cierra la puerta para siempre.

**Plan:** entrar a 3 grupos, no publicar nada durante dos semanas, y anotar las diez
quejas más repetidas sobre conseguir clientes. Eso alimenta el guion de venta con las
palabras que ellos usan, que vale más que cualquier post.

---

## Orden recomendado

1. **Ahora:** ítems 1 y 2 — son incoherencias del sistema, no features. Una sesión cada uno.
2. **Durante la Fase B del plan diario:** ítem 11, gratis y alimenta el guion.
3. **Después de la primera venta cobrada:** ítem 3 (WhatsApp), y con él los ítems 4 y 8
   como funciones suyas, no como productos aparte.
4. **Solo si un cliente lo pide y paga:** ítems 5 y 6.
5. **Nunca, salvo que cambie el contexto:** ítems 7, 9 y 10.

## Documentos relacionados

- [`PLAN_DIARIO.md`](PLAN_DIARIO.md) — las 20 sesiones que van antes de todo esto
- [`PROCESOS.md`](PROCESOS.md) — el mapa de lo que sí está construido
- [`WHATSAPP_BOT.md`](WHATSAPP_BOT.md) — el análisis largo del ítem 3
- [`../gtm/decision_criteria.yaml`](../gtm/decision_criteria.yaml) — el experimento que
  decide si algo de esto llega a tener sentido
