# Canales de contacto: cuál usar, por qué, y qué se descartó

Este documento responde tres preguntas concretas que el dueño del proyecto hizo en
agosto de 2026: ¿es el email la mejor forma de contactar a un prospecto, o cae en spam?
¿Por qué no hay WhatsApp, Telegram o SMS si el prospecto tiene teléfono pero no sitio ni
mail? ¿Qué hace falta para que el envío de email sea seguro, escalable y no termine en la
carpeta de spam? Las fuentes de cada afirmación están al final.

---

## 1. Ranking de canales, de mejor a peor, para SMBs de oficio en USA

### 1. Teléfono — el canal que ya eligió el pipeline, y sigue siendo el correcto

Cero costo marginal, cero requisito regulatorio para llamar manualmente a un número
comercial publicado, y la conversión más alta con diferencia. `discover.py` ya descarta
cualquier prospecto sin teléfono, y `contact.py` ya prioriza este canal para los
prospectos de mayor dolor (sin sitio o solo redes). No hace falta cambiar nada acá.

### 2. Formulario de contacto del propio sitio — legal, pero no se automatiza

El negocio publicó ese formulario invitando al contacto: no es recolección de
direcciones. **Restricción explícita: no se automatiza el envío.** Muchos formularios
tienen reCAPTCHA o Cloudflare Turnstile, y sortearlos es a la vez violación de los
términos de servicio del formulario y evasión de detección de bots — exactamente el tipo
de acción que este proyecto no hace. El sistema prepara el mensaje y deja el link
abierto; el humano lo pega y aprieta enviar.

### 3. Email a una dirección comercial publicada — legal, pero con dos advertencias

CAN-SPAM es un régimen de **opt-out**, no de opt-in: por eso el mercado elegido es USA y
no Europa (ver `docs/WHY.md`). Cada mensaje necesita dirección postal física, baja
funcional y aviso de mensaje comercial — `outreach.validate_compliance()` ya lo exige y
lo verifica antes de que el mensaje pueda existir.

Dos advertencias, ninguna nueva:

- **Los proveedores de email transaccional prohíben el outreach en frío en sus propios
  términos de servicio.** Ver la sección 3 completa más abajo — es la razón por la que
  el envío usa un buzón propio (SMTP directo) y no Resend/SendGrid/Postmark/SES.
- **La recolección automatizada de direcciones es una *aggravated violation* de
  CAN-SPAM** — agrava las multas en vez de solo aplicarlas. El repo ya decidió no
  scrapear emails (`gtm/factory/types.py`, `ContactChannel`) y esa decisión no cambia acá:
  la dirección se carga a mano cuando el operador la ve publicada en el sitio del
  prospecto, nunca extraída por código.

### 4. SMS — no se implementa

Dos obstáculos independientes, y solo uno tiene arreglo:

- **A2P 10DLC**: desde febrero de 2025 los carriers de USA bloquean el 100% del tráfico
  A2P (aplicación-a-persona) no registrado. Registrarse como *sole proprietor* cuesta
  poco (USD 4 de alta + USD 15 de vetting + USD 2/mes), así que esto por sí solo no es
  un bloqueante duro.
- **TCPA**: el obstáculo real. Exige **consentimiento previo, expreso y por escrito**
  para mensajes comerciales — el registro en A2P 10DLC no lo sustituye, es un requisito
  de los carriers, no del consumidor. Las multas van de USD 500 a USD 1.500 **por
  mensaje**. Contactar 25 prospectos por semana en frío por SMS es una exposición de
  USD 12.500 a 37.500 semanales si algo sale mal. Hay una nueva regla de consentimiento
  de la FCC con vigencia desde el 27 de enero de 2026 — señal de que el terreno legal
  sigue moviéndose, no de que se puso más permisivo.

**Conclusión: sin un mecanismo real de consentimiento previo (por ejemplo, que el
prospecto se suscriba él mismo desde un formulario), SMS en frío queda descartado.**

### 5. WhatsApp Business Platform — no se implementa

Desde julio de 2025 Meta cobra por mensaje entregado (no por conversación): ~USD 0.025
por plantilla de marketing a un número de USA, más el margen del proveedor (BSP),
típicamente USD 0.003–0.010 adicionales. Para iniciar una conversación con alguien que no
escribió primero hace falta una **plantilla pre-aprobada por Meta** — no se puede mandar
texto libre en frío. Y aunque el mecanismo fuera gratis, la penetración de WhatsApp entre
negocios de oficio de USA (la audiencia de este proyecto) es marginal: es el canal
dominante en Latinoamérica, no necesariamente donde vive el prospecto real acá. Pagar y
arriesgar la cuenta de WhatsApp Business por un canal que el prospecto probablemente ni
mira no es un buen cambio.

### 6. Telegram — no se implementa

Cerrado por diseño: un bot de Telegram no puede iniciar una conversación con un usuario
que no lo agregó primero. No hay forma de "mandar un Telegram en frío" sin que el
prospecto ya haya interactuado con el bot antes — la plataforma no lo permite.

---

## 2. Email: cómo evitar que caiga en spam (la pregunta 2 original)

En 2026, Gmail, Yahoo y Microsoft pasaron sus requisitos de "recomendado" a
"**obligatorio**", y el castigo por no cumplirlos ya no es la carpeta de spam — es el
**rechazo directo** del mensaje, que ni siquiera llega. Lista de verificación completa:

- **SPF, DKIM y DMARC alineados**, los tres en `PASS`. DMARC como mínimo en `p=none` para
  arrancar (para poder ver reportes sin bloquear nada), subiendo a `p=quarantine` después
  de 2 semanas de reportes limpios.
- **`List-Unsubscribe` y `List-Unsubscribe-Post`** (RFC 8058): baja en un clic, sin que el
  destinatario tenga que abrir un link ni escribir un email. Yahoo exige honrar el pedido
  dentro de las 48 horas.
- **`multipart/alternative`** con una parte de texto plano real (no generada
  automáticamente a partir del HTML) — un mail solo-HTML es en sí mismo una señal de spam
  para los filtros modernos.
- **Sin píxel de rastreo, sin acortadores de links.** Ambos son heurísticas clásicas de
  detección de spam.
- **Dominio de envío separado del dominio del portfolio** (ver `docs/WHY.md` y la Tarea
  0.2 del plan de trabajo): si el envío en frío daña la reputación de un dominio, no se
  lleva puesta la carta de presentación.
- **Volumen bajo y con rampa**: 20–25 mensajes por día por casilla nueva, subiendo
  gradualmente durante 14–21 días antes de operar a régimen normal. Coincide, sin
  buscarlo, con el volumen real del proyecto (25 prospectos por semana).
- **Tasa de rebote por debajo de 2%**, quejas por debajo de 0.10% (0.30% es el techo de
  emergencia que usan los proveedores para suspender cuentas — tratarlo como objetivo en
  vez de límite de pánico ya es tarde).
- **Una dirección de rebote monitoreada** (`GTM_BOUNCE_ADDRESS`), para poder distinguir un
  rebote duro (dirección inexistente → suprimir) de uno blando (buzón lleno → reintentar).

### Por qué no un proveedor de email transaccional (Resend, SendGrid, Postmark, SES...)

Los cinco evaluados —Resend, Postmark, Amazon SES, SendGrid, Mailchimp, Kit, Brevo,
Acumbamail— exigen consentimiento previo del destinatario en sus propios términos de
servicio, y varios lo dicen explícitamente:

> "Except for transactional emails... you must obtain affirmative consent prior to
> sending any emails to a recipient via the Twilio SendGrid Email Services." — SendGrid

> Mailchimp prohíbe "Third-party lists of email addresses... including lists scraped
> from third-party sources, including public websites."

Postmark directamente solo permite email transaccional, sin excepción. Amazon SES
"desalienta fuertemente" el envío a listas sin opt-in. El patrón se repite en los ocho:
**el plan gratuito existe para captar marketers de opt-in; la política de uso aceptable
es, en los hechos, el producto.** El límite de envíos nunca fue la restricción real — el
consentimiento previo sí. Usar cualquiera de estos para el outreach en frío de este
proyecto es una violación de términos que puede terminar en suspensión de cuenta sin
aviso.

**La alternativa elegida: un buzón propio (Zoho Mail Lite, ~USD 1/mes) sobre un dominio
secundario, con envío por SMTP directo.** Es tu propio buzón: no hay una política de uso
aceptable de terceros que viole, porque no hay tercero — solo vos, mandando mail desde tu
cuenta, exactamente como lo haría cualquier persona a mano. La contrapartida es que hay
que armar la infraestructura de reintentos y detección de rebotes en el propio pipeline
en vez de recibirla de un proveedor por API — eso es lo que construye la Fase 3 de este
plan (`gtm/send/`).

---

## 3. Fuentes

- [Bulk Email Sender Rules For Google, Yahoo, Microsoft & Apple (2026) — PowerDMARC](https://powerdmarc.com/bulk-email-sender-requirements/)
- [Google & Yahoo Sender Requirements for Cold Email (2026) — InboxKit](https://www.inboxkit.com/learn/google-yahoo-sender-requirements-2026)
- [Postmark vs. Resend: a detailed comparison for 2026 — Postmark](https://postmarkapp.com/compare/resend-alternative)
- [SendGrid — Email Opt-in and Opt-out Requirements](https://support.sendgrid.com/hc/en-us/articles/4404315959835-Email-Opt-in-and-Opt-out-Requirements)
- [SendGrid Free Plan Discontinued](https://helpdesk.reusser.com/hc/en-us/articles/38602119422349-SendGrid-Free-Plan-Discontinued)
- [Mailchimp — Requirements and Best Practices for Audiences](https://mailchimp.com/help/requirements-best-practices-audiences/)
- [Kit — Acceptable Use Policy](https://help.kit.com/en/articles/3038130-acceptable-use-policy)
- [Brevo — Best Email API Services 2026](https://www.brevo.com/blog/best-email-api/)
- [Zoho Mail Free Plan Limitations (2026)](https://mail.mailbux.com/blog/email-comparisons/zoho-mail-free-plan-limitations-alternative)
- [Google Workspace Pricing (2026)](https://www.emailvendorselection.com/google-workspace-pricing/)
- [TCPA and SMS Compliance in 2026: Carrier Restrictions, Cold Call Rules](https://subscriberverify.com/blog/tcpa-sms-carrier-restrictions-cold-calling-2026)
- [A2P 10DLC Sole Proprietor Brands FAQ — Twilio](https://support.twilio.com/hc/en-us/articles/9550596959643-A2P-10DLC-Sole-Proprietor-Brands-FAQ)
- [Pricing on the WhatsApp Business Platform — Meta](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing)
