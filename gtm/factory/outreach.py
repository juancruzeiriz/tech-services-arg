"""Etapa 5: redactar el email de prospección, validado contra CAN-SPAM.

CAN-SPAM permite el email comercial B2B en frío sin consentimiento previo, pero exige
en **cada** mensaje: remitente real, asunto no engañoso, dirección postal física,
identificación como comunicación comercial y un mecanismo de baja honrado en ≤10 días
hábiles. Las multas se cuentan por mensaje, así que la validación corre antes de que
el email exista, no después de enviarlo.

Regla de honestidad del módulo: el gancho de la llamada perdida **solo** se renderiza
si se registró una observación real (`missed_call_at`). El pipeline no inventa hechos
sobre el negocio del prospecto; si la observación no existe, se usa el ángulo medido
por Lighthouse, que es verificable por el propio prospecto.

Uso:
    python -m gtm.factory.outreach --input gtm/build/data/demos.json
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from gtm.factory import artifacts, config
from gtm.factory.logs import get_logger
from gtm.factory.types import (
    ComplianceError,
    Demo,
    Language,
    OutreachEmail,
    PainScore,
    Prospect,
    SenderIdentity,
    vertical_label,
)

_logger = get_logger(__name__)

# Frase que identifica el mensaje como comunicación comercial (CAN-SPAM). CAN-SPAM
# aplica sin importar el idioma del mensaje, así que hace falta un equivalente
# fielmente exacto en español, no una paráfrasis.
#
# Deliberadamente DOS constantes de texto plano, no un dict {Language: str}: el test
# de compliance (`tests/gtm/test_outreach.py::TestCanspamCompliance`, el gate de CI)
# importa `_AD_DISCLOSURE` directo y hace `in email.body` — si esto fuera un dict esa
# importación seguiría funcionando pero la comparación fallaría en silencio.
_AD_DISCLOSURE_EN = "This is a commercial message from an independent web developer."
_AD_DISCLOSURE_ES = "Este es un mensaje comercial de un desarrollador web independiente."
_AD_DISCLOSURE = _AD_DISCLOSURE_EN  # nombre histórico; ver el comentario de arriba.

# weekday(): lunes=0 ... domingo=6. No se usa strftime("%A") en español porque
# depende del locale del sistema operativo -- exactamente el tipo de bug de "%-I"
# que ya rompió esto una vez en Windows (ver build_body).
_DIAS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _ad_disclosure(language: Language) -> str:
    return _AD_DISCLOSURE_ES if language is Language.ES else _AD_DISCLOSURE_EN


def build_subject(prospect: Prospect, *, language: Language = Language.EN) -> str:
    """Asunto descriptivo y verdadero.

    Sin clickbait ni falsos "Re:" — un asunto engañoso es una violación de CAN-SPAM
    por sí solo, y además destruye la conversión cuando el prospecto abre.
    """
    if language is Language.ES:
        return f"Hice un sitio de muestra para {prospect.name}"
    return f"Built a preview site for {prospect.name}"


def _pain_line_en(score: PainScore | None) -> str:
    if score is None:
        return "I noticed your business does not have much of a website."

    if not score.has_web_presence:
        return (
            "I noticed you do not have a website — everything runs through your "
            "Google listing."
        )
    if not score.reachable:
        return "I tried opening your website and it did not load."
    if score.performance is not None and score.performance < 50:
        return (
            f"Your site scores {score.performance}/100 on Google's own mobile speed "
            "test — you can check it yourself at pagespeed.web.dev."
        )
    if score.seo is not None and score.seo < 70:
        return (
            f"Your site scores {score.seo}/100 on Google's SEO check — "
            "you can verify it at pagespeed.web.dev."
        )
    return "I think your site could convert a lot more of the calls you already get."


def _pain_line_es(score: PainScore | None) -> str:
    if score is None:
        return "Noté que tu negocio no tiene mucho sitio web."

    if not score.has_web_presence:
        return "Noté que no tenés sitio web — todo pasa por tu ficha de Google."
    if not score.reachable:
        return "Intenté abrir tu sitio y no cargó."
    if score.performance is not None and score.performance < 50:
        return (
            f"Tu sitio saca {score.performance}/100 en el test de velocidad móvil de "
            "Google — lo podés verificar vos mismo en pagespeed.web.dev."
        )
    if score.seo is not None and score.seo < 70:
        return (
            f"Tu sitio saca {score.seo}/100 en el chequeo de SEO de Google — "
            "lo podés verificar en pagespeed.web.dev."
        )
    return "Creo que tu sitio podría convertir muchas más de las llamadas que ya recibís."


def _pain_line(score: PainScore | None, language: Language = Language.EN) -> str:
    """Una línea concreta y verificable sobre el estado actual del prospecto."""
    return _pain_line_es(score) if language is Language.ES else _pain_line_en(score)


def build_body(
    prospect: Prospect,
    demo: Demo,
    sender: SenderIdentity,
    score: PainScore | None = None,
    missed_call_at: datetime | None = None,
    *,
    language: Language = Language.EN,
    link_url: str | None = None,
    price_usd: int = 950,
) -> str:
    """Redacta el cuerpo del email, con todos los elementos exigidos por CAN-SPAM.

    `price_usd`: el precio de la oferta, la única variable que de verdad define
    el experimento (ver `gtm/decision_criteria.yaml`) — 950 es el default
    porque es el que ya estaba hardcodeado acá, no una preferencia.

    `link_url`, si se pasa, reemplaza a `demo.url` como el link que efectivamente
    ve el prospecto — es el hueco por el que entra el link de redirección con
    token (`gtm/store/links.py`) que registra la apertura sin que la demo en sí
    tenga que hacer ni un request externo. `demo.is_live` sigue siendo lo que
    determina si hay algo que mandar; `link_url` solo cambia qué URL se escribe.
    """
    if not demo.is_live:
        raise ComplianceError(
            f"La demo de {prospect.name!r} no tiene URL pública: un mockup adjunto no "
            "es prueba de trabajo y es el pitch que el prospecto ya descartó veinte veces."
        )
    link = link_url or demo.url

    if missed_call_at is not None:
        # "%-I" (sin cero a la izquierda) es una extensión de glibc: no existe en el
        # strftime de Windows ("%#I" ahí, ninguna de las dos es portable). Se arma a
        # mano para que corra igual en CI (Linux) y en desarrollo (Windows).
        hour_12 = int(missed_call_at.strftime("%I"))
        if language is Language.ES:
            dia = _DIAS_ES[missed_call_at.weekday()]
            hook = (
                f"Te llamé el {dia} a las {hour_12}{missed_call_at.strftime(':%M')} y "
                "no atendió nadie. Tampoco había buzón de voz."
            )
        else:
            hook = (
                f"I called {missed_call_at.strftime('%A at')} {hour_12}"
                f"{missed_call_at.strftime(':%M %p')} and nobody picked up. No voicemail either."
            )
    else:
        hook = _pain_line(score, language)

    if language is Language.ES:
        vertical = vertical_label(prospect.vertical, language)
        return f"""Hola — {hook}

Te armé un sitio nuevo y lo subí:

{link}

Está online ahora mismo. Abrilo desde el celular. Usa tu número de teléfono real,
tus reseñas reales de Google y tu zona de servicio — no hay nada inventado.

Dos cosas que hace que tu configuración actual no hace:

  1. Carga al instante en el celular, que es donde están tus clientes.
  2. Cuando se te escapa una llamada, quien llamó recibe un mensaje de texto en
     segundos preguntando qué necesita, así el trabajo no se va al próximo
     {vertical} de la lista.

Si lo querés, son USD {price_usd} por única vez y lo puedo apuntar a tu dominio en 48
horas. Reembolso completo dentro de los 14 días, sin preguntas. Si no lo querés,
quedate con el link igual — no me costó nada hacerlo y es tuyo.

¿Vale una llamada de 10 minutos?

{sender.from_name}
{sender.from_email}

--
{_ad_disclosure(language)} Recibiste esto en la dirección de contacto pública de tu
negocio. Para que no te vuelva a escribir, usá este link y te voy a sacar de la
lista dentro de los 10 días hábiles: {sender.unsubscribe_url}
{sender.physical_address}
"""

    return f"""Hi — {hook}

So I built you a new site and put it online:

{link}

It is live right now. Open it on your phone. It uses your real phone number,
your actual Google reviews and your service area — nothing is made up.

Two things it does that your current setup does not:

  1. It loads instantly on a phone, which is where your customers are.
  2. When you miss a call, the caller gets a text back within seconds asking
     what they need, so the job does not go to the next {vertical_label(prospect.vertical)}
     on the list.

If you want it, it is ${price_usd} one time and I can point it at your domain within
48 hours. Full refund within 14 days, no questions. If you do not want it,
keep the link anyway — it cost me nothing to make and it is yours.

Worth a 10-minute call?

{sender.from_name}
{sender.from_email}

--
{_ad_disclosure(language)} You received this at your publicly listed business address.
To never hear from me again, use this link and I will remove you within
10 business days: {sender.unsubscribe_url}
{sender.physical_address}
"""


def validate_compliance(email: OutreachEmail) -> None:
    """Verifica que el email cumpla CAN-SPAM. Falla ruidosamente si no.

    Raises:
        ComplianceError: si falta cualquier elemento obligatorio.
    """
    email.sender.validate()

    if not email.subject.strip():
        raise ComplianceError("asunto vacío")

    # Asuntos que fingen ser una conversación previa: engañosos por definición.
    lowered = email.subject.strip().lower()
    if lowered.startswith(("re:", "fwd:", "fw:")):
        raise ComplianceError(f"asunto engañoso (finge un hilo previo): {email.subject!r}")

    if email.sender.physical_address not in email.body:
        raise ComplianceError("el cuerpo no incluye la dirección postal física")

    if email.sender.unsubscribe_url not in email.body:
        raise ComplianceError("el cuerpo no incluye el mecanismo de baja")

    if _ad_disclosure(email.language) not in email.body:
        raise ComplianceError("el cuerpo no se identifica como comunicación comercial")

    if email.demo_url and email.demo_url not in email.body:
        raise ComplianceError("el cuerpo no incluye el link de la demo")


def build_email(
    prospect: Prospect,
    demo: Demo,
    sender: SenderIdentity,
    score: PainScore | None = None,
    missed_call_at: datetime | None = None,
    to_email: str | None = None,
    *,
    language: Language = Language.EN,
    link_url: str | None = None,
    price_usd: int = 950,
) -> OutreachEmail:
    """Construye y valida un email de prospección listo para enviar.

    `link_url`: ver el docstring de `build_body`. Se guarda también en
    `OutreachEmail.demo_url` (mismo valor) para que `validate_compliance` siga
    verificando, sin cambios, que el link que se manda está en el cuerpo.
    """
    link = link_url or demo.url
    email = OutreachEmail(
        place_id=prospect.place_id,
        to_email=to_email,
        subject=build_subject(prospect, language=language),
        body=build_body(
            prospect, demo, sender, score, missed_call_at,
            language=language, link_url=link_url, price_usd=price_usd,
        ),
        sender=sender,
        demo_url=link,
        language=language,
    )
    validate_compliance(email)
    return email


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera los emails de prospección")
    parser.add_argument("--prospects", default=None, help="default: gtm/build/data/prospects.json")
    parser.add_argument("--demos", default=None, help="default: gtm/build/data/demos.json")
    parser.add_argument("--scores", default=None, help="default: gtm/build/data/scores.json")
    parser.add_argument("--output", default=None, help="default: gtm/build/data/emails.json")
    args = parser.parse_args(argv)

    config.ensure_dirs()
    prospects_path = args.prospects or str(config.DATA_DIR / "prospects.json")
    demos_path = args.demos or str(config.DATA_DIR / "demos.json")
    scores_path = args.scores or str(config.DATA_DIR / "scores.json")
    output_path = args.output or str(config.DATA_DIR / "emails.json")

    sender = config.load_sender_identity()

    prospects = {p.place_id: p for p in artifacts.read_prospects(prospects_path)}
    demos = artifacts.read_demos(demos_path)

    scores: dict[str, PainScore] = {}
    try:
        scores = {s.place_id: s for s in artifacts.read_scores(scores_path)}
    except FileNotFoundError:
        _logger.warning("sin scores; se usa el ángulo genérico", extra={"event": "no_scores"})

    emails: list[OutreachEmail] = []
    for demo in demos:
        prospect = prospects.get(demo.place_id)
        if prospect is None:
            continue
        try:
            emails.append(build_email(prospect, demo, sender, scores.get(demo.place_id)))
        except ComplianceError as exc:
            _logger.error(
                "email descartado por incumplimiento",
                extra={
                    "event": "compliance_rejected",
                    "place_id": demo.place_id,
                    "error": str(exc),
                },
            )

    artifacts.write_emails(output_path, emails)

    print(f"{len(emails)}/{len(demos)} emails conformes -> {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
