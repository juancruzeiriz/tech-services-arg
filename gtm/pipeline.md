# Pipeline comercial

Operativa de venta. El código fabrica el artefacto; esto define qué se hace con él.

## La oferta

**Vertical:** home services en USA — plomeros, HVAC, techistas, electricistas.
Criterio: el trabajo vale USD 300-15.000, el negocio es telefónico, las webs son malas,
y una llamada perdida es una pérdida cuantificable. **Evitar salud (HIPAA) y legal.**

Hay una cuarta razón, menos obvia que las anteriores: el servicio del prospecto no se
puede deslocalizar (un plomero de Tucson no compite contra uno de otro país porque el
trabajo se hace en la casa del cliente), así que la venta del sitio se cierra por
confianza y urgencia local, no comparando precio contra un freelancer más barato en
otro lado. Desarrollo del razonamiento en [`docs/WHY.md`](../docs/WHY.md#3-por-qué-oficios-home-services).

**Nicho inicial: un oficio, un metro secundario.** No NYC ni LA. Es la decisión de
apalancamiento más importante: el mismo template sirve a todos, el costo marginal por
demo tiende a cero, y a la tercera venta podés decir "trabajo con otros tres plomeros
de esta ciudad". La especialización sustituye a la fama.

**Paquete:**

| | |
|---|---|
| Entregable | Sitio estático rápido + captura de llamadas perdidas con SMS automático |
| Plazo | 48 horas |
| Precio | **USD 950** una vez |
| Garantía | Devolución total a 14 días, sin preguntas |
| Recurrente (opcional) | **USD 150-200/mes**: hosting, bot y cambios menores |

**El bot no se construye.** Se configura un proveedor existente (AI receptionist /
missed-call-text-back, USD 25-50/mes) con la info real del negocio. El mercado ya está
poblado por startups financiadas; construir el propio significa heredar guardias 24/7,
que es exactamente lo que no entra en 5-10 hs semanales. El margen está en la
instalación, no en el software.

**Estructura anti-soporte**, por diseño y por contrato:

- Sitio **estático**: no hay CMS ni servidor propio que se rompa
- El uptime del bot es del proveedor, no tuyo
- Ventana mensual acotada para cambios, SLA de 48 hs hábiles
- **Sin on-call**, explícito en el contrato

## Secuencia

**Semana 1.** Elegir oficio + metro. Cerrar oferta, precio y garantía. Dar de alta el
proveedor de SMS y configurarlo end-to-end en un caso propio: no se vende algo que
todavía no se instaló una vez.

**Semana 2.** Correr el pipeline. Salida: 50 prospectos rankeados, 10 demos publicadas.

**Semanas 3-6.** 25 demos por semana. Métrica: **respuestas**, no clics.

**Semanas 6-12.** Los 3 pilotos se convierten en casos publicados. Lo repetido se
convierte en el recurrente. El factory se abre como open source.

## El mensaje

El pitch "te hago una web" está quemado: es de los más spameados de USA. Sobrevive solo
si cumple las tres condiciones a la vez:

1. La demo está **realmente publicada y viva**, no adjunta
2. Es hiper-específica: sus reseñas, su teléfono, su zona
3. Trae un dato concreto y **verificable por el prospecto**

El orden del email importa: primero el hecho observado, después el link, y recién al
final el precio. Si el precio va arriba, se lee como publicidad y se cierra.

**Prohibido inventar.** No afirmar que llamaste si no llamaste. El código lo impide —
el gancho de la llamada perdida requiere una observación registrada— pero la regla es
tuya, no del código: el primer teléfono que atiendan destruye la venta y la reputación
que estás tratando de construir.

## Guion de la llamada (20 min)

No es una demo del producto. Es confirmar que el dolor existe y que hay presupuesto.

1. "¿Cómo entran hoy los trabajos?" — dejar hablar
2. "¿Qué pasa cuando llaman y estás en un techo?" — **este es el momento**
3. "¿Cuánto vale un trabajo promedio para vos?" — cuantifica la pérdida sin que la
   cuantifiques vos
4. "¿Cuántas llamadas dirías que se te pasan por semana?"
5. Recién ahí: precio, plazo, garantía

Multiplicar 4 × 3 delante suyo es todo el argumento. Si da menos que USD 950, el
prospecto está mal elegido: volver al paso de discovery, no bajar el precio.

## Resolver la falta de marca

Ordenado por costo. Los cinco primeros son gratis.

| # | Mecanismo | Costo |
|---|---|---|
| 1 | Artefacto entregado antes de vender: la demo viva | 0 |
| 2 | Reversión de riesgo: garantía total 14 días, 50% adelanto | 0 |
| 3 | Marca prestada: primeras 2-3 ventas por Upwork/escrow — presta confianza y resuelve el cobro internacional | ~10% |
| 4 | Prueba social: 3 pilotos a precio reducido por testimonio + caso publicado, **con vencimiento explícito** | ~USD 1.500 |
| 5 | Presencia verificable: sitio propio, LinkedIn real, repo público — te van a googlear | 0 |
| 6 | Especificidad de nicho | 0 |

El punto 4 es comprar casos de estudio, no descontar. Si no vence, el precio piloto se
vuelve el precio.

Descartado explícitamente: freemium (necesita volumen de tráfico que no existe y atrae
a quien nunca paga), trabajar gratis a cielo abierto, bajar precio sin contrapartida.

## Contrato — cláusulas mínimas

- Alcance cerrado y enumerado; lo que no está listado, no está incluido
- **Sin on-call ni garantía de disponibilidad**: el uptime es del proveedor tercero
- Cambios: hasta N por mes dentro del recurrente, SLA 48 hs hábiles
- El cliente es dueño del contenido y del dominio; el hosting es transferible
- Garantía: devolución total a 14 días
- Pago: 50% adelanto / 50% contra entrega, o escrow completo en las primeras ventas

## Riesgos

**No grabar llamadas.** Varios estados de USA exigen consentimiento de ambas partes.
Constatar que no atendieron alcanza; grabar te expone.

**CAN-SPAM.** Permite el email B2B en frío sin consentimiento previo, pero las multas
llegan a ~USD 53.000 por mensaje. El cumplimiento es trivial y está automatizado: correr
`pytest tests/gtm/test_outreach.py -k canspam` antes de cada envío. Y honrar las bajas
en ≤10 días hábiles, de verdad.

**GDPR bloquea esto en Europa.** El beachhead es USA por una razón legal, no cultural:
CAN-SPAM permite el contacto B2B en frío con reglas de forma (remitente real, opt-out
honrado), mientras que GDPR exige consentimiento previo o interés legítimo demostrable.
El mismo pipeline que es legal en USA sería una infracción desde el primer email si se
apuntara a Europa. Razonamiento completo en [`docs/WHY.md`](../docs/WHY.md#2-por-qué-estados-unidos).

**WhatsApp no aplica.** En USA el canal es teléfono y SMS; además la Business API exige
plantillas aprobadas y opt-in previo, así que el envío en frío es inviable.

**Cobro desde USA.** Escrow al principio; después Stripe/Wise con 50% adelanto. Facturar
con Factura E: exportación de servicios, sin IVA ni derechos de exportación, y no computa
contra el límite del monotributo. ARCA cruza comprobantes contra la liquidación bancaria
de divisas, así que se factura todo. **Validar con contador — esto no es asesoramiento
fiscal.**

**Concentración.** Con el recurrente en 2 clientes todavía no es un negocio. Meta: 8-10.

## Decisión

El criterio está pre-registrado en [`decision_criteria.yaml`](decision_criteria.yaml) y
no se modifica durante el experimento.

Resumen: gana la oferta que llegue a **1 venta cobrada** o **3 llamadas agendadas**. Se
mata si a las 60 demos enviadas hay menos de 3 respuestas — y en ese caso se cambia de
vertical o de oferta, **no de redacción**. Retocar el asunto por décima vez es la forma
más común de no aceptar un no.
