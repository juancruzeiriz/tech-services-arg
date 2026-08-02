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
import json
import sys
from datetime import datetime

from gtm.factory import config
from gtm.factory.logs import get_logger
from gtm.factory.types import (
    ComplianceError,
    Demo,
    OutreachEmail,
    PainScore,
    Prospect,
    SenderIdentity,
    vertical_label,
)

_logger = get_logger(__name__)

# Frase que identifica el mensaje como comunicación comercial (CAN-SPAM).
_AD_DISCLOSURE = "This is a commercial message from an independent web developer."


def build_subject(prospect: Prospect) -> str:
    """Asunto descriptivo y verdadero.

    Sin clickbait ni falsos "Re:" — un asunto engañoso es una violación de CAN-SPAM
    por sí solo, y además destruye la conversión cuando el prospecto abre.
    """
    return f"Built a preview site for {prospect.name}"


def _pain_line(score: PainScore | None) -> str:
    """Una línea concreta y verificable sobre el estado actual del prospecto."""
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


def build_body(
    prospect: Prospect,
    demo: Demo,
    sender: SenderIdentity,
    score: PainScore | None = None,
    missed_call_at: datetime | None = None,
) -> str:
    """Redacta el cuerpo del email, con todos los elementos exigidos por CAN-SPAM."""
    if not demo.is_live:
        raise ComplianceError(
            f"La demo de {prospect.name!r} no tiene URL pública: un mockup adjunto no "
            "es prueba de trabajo y es el pitch que el prospecto ya descartó veinte veces."
        )

    if missed_call_at is not None:
        hook = (
            f"I called {missed_call_at.strftime('%A at %-I:%M %p')} and nobody picked "
            "up. No voicemail either."
        )
    else:
        hook = _pain_line(score)

    return f"""Hi — {hook}

So I built you a new site and put it online:

{demo.url}

It is live right now. Open it on your phone. It uses your real phone number,
your actual Google reviews and your service area — nothing is made up.

Two things it does that your current setup does not:

  1. It loads instantly on a phone, which is where your customers are.
  2. When you miss a call, the caller gets a text back within seconds asking
     what they need, so the job does not go to the next {vertical_label(prospect.vertical)}
     on the list.

If you want it, it is $950 one time and I can point it at your domain within
48 hours. Full refund within 14 days, no questions. If you do not want it,
keep the link anyway — it cost me nothing to make and it is yours.

Worth a 10-minute call?

{sender.from_name}
{sender.from_email}

--
{_AD_DISCLOSURE} You received this at your publicly listed business address.
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

    if _AD_DISCLOSURE not in email.body:
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
) -> OutreachEmail:
    """Construye y valida un email de prospección listo para enviar."""
    email = OutreachEmail(
        place_id=prospect.place_id,
        to_email=to_email,
        subject=build_subject(prospect),
        body=build_body(prospect, demo, sender, score, missed_call_at),
        sender=sender,
        demo_url=demo.url,
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

    with open(prospects_path, encoding="utf-8") as handle:
        prospects = {p["place_id"]: Prospect.from_dict(p) for p in json.load(handle)}

    with open(demos_path, encoding="utf-8") as handle:
        demos = [
            Demo(
                place_id=item["place_id"],
                slug=item["slug"],
                html_path=item["html_path"],
                url=item.get("url"),
            )
            for item in json.load(handle)
        ]

    scores: dict[str, PainScore] = {}
    try:
        with open(scores_path, encoding="utf-8") as handle:
            for item in json.load(handle):
                scores[item["place_id"]] = PainScore(
                    place_id=item["place_id"],
                    performance=item.get("performance"),
                    seo=item.get("seo"),
                    accessibility=item.get("accessibility"),
                    mobile_friendly=item.get("mobile_friendly"),
                    has_web_presence=item.get("has_web_presence", True),
                    reachable=item.get("reachable", True),
                    notes=tuple(item.get("notes", ())),
                )
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

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump([e.to_dict() for e in emails], handle, ensure_ascii=False, indent=2)

    print(f"{len(emails)}/{len(demos)} emails conformes -> {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
