"""Modelos de datos del pipeline de prospección.

Flujo: Prospect (discover) -> PainScore (score) -> Demo (generate/deploy) -> OutreachEmail.

Cada etapa es idempotente y se identifica por `Prospect.place_id`, el ID estable de
Google Places. Re-correr una etapa sobre el mismo prospecto produce el mismo resultado.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class GTMError(Exception):
    """Error base del pipeline de prospección."""


class DiscoveryError(GTMError):
    """Fallo al descubrir prospectos (Places API)."""


class ScoringError(GTMError):
    """Fallo al puntuar el sitio de un prospecto (PageSpeed API)."""


class GenerationError(GTMError):
    """Fallo al renderizar la demo de un prospecto."""


class DeploymentError(GTMError):
    """Fallo al publicar la demo."""


class ComplianceError(GTMError):
    """El artefacto generado viola una regla de cumplimiento (CAN-SPAM)."""


class WebPresence(StrEnum):
    """Estado de la presencia web del prospecto.

    Determina el ángulo de venta: NONE y SOCIAL_ONLY son los de mayor conversión
    porque el negocio no tiene nada que defender.
    """

    NONE = "none"
    """Sin sitio web. Máxima oportunidad."""

    SOCIAL_ONLY = "social_only"
    """Solo Facebook/Instagram como "sitio". No controlan su presencia."""

    HAS_SITE = "has_site"
    """Tiene sitio propio. La venta depende de qué tan malo sea (ver PainScore)."""


# Dominios que no son un sitio web propio, solo un perfil en plataforma ajena.
_SOCIAL_HOSTS: frozenset[str] = frozenset(
    {
        "facebook.com",
        "m.facebook.com",
        "instagram.com",
        "linktr.ee",
        "yelp.com",
        "nextdoor.com",
        "business.site",  # Google Business "sitios" autogenerados
        "wixsite.com",
    }
)


# Cómo se nombra cada rubro en el inglés que usa el cliente final. Compartido entre
# la demo y el email: si el sitio dice "HVAC contractor" y el email dice "hvac", el
# prospecto nota que hay una plantilla atrás.
VERTICAL_LABELS: dict[str, str] = {
    "plumber": "plumber",
    "hvac": "HVAC contractor",
    "electrician": "electrician",
    "roofer": "roofing contractor",
    "landscaper": "landscaper",
}


def vertical_label(vertical: str) -> str:
    """Etiqueta legible del rubro; cae al valor crudo si no está mapeado."""
    return VERTICAL_LABELS.get(vertical.lower(), vertical)


def vertical_plural(vertical: str) -> str:
    """Plural legible del rubro: "HVAC contractors", no "hvacs".

    Existe porque interpolar el vertical crudo produce texto que delata la plantilla
    en la primera línea del mensaje, que es exactamente donde no podés perder al lector.
    """
    label = vertical_label(vertical)
    return label if label.endswith("s") else f"{label}s"


# Consonantes cuyo nombre en inglés empieza con vocal: "an HVAC", "an L-shaped".
# Sin esto, un acrónimo con inicial consonante recibe "a" y el error queda impreso
# en el producto que ve el cliente.
_VOWEL_SOUND_INITIALS = frozenset("AEFHILMNORSX")


def indefinite_article(phrase: str) -> str:
    """Devuelve "a" o "an" según cómo se pronuncia el inicio de `phrase`."""
    stripped = phrase.strip()
    if not stripped:
        return "a"

    first_word = stripped.split()[0]

    # Acrónimo (HVAC, AC, EV): se deletrea, así que manda el nombre de la letra.
    if first_word.isupper() and len(first_word) > 1:
        return "an" if first_word[0] in _VOWEL_SOUND_INITIALS else "a"

    return "an" if stripped[0].lower() in "aeiou" else "a"


def classify_web_presence(website: str | None) -> WebPresence:
    """Clasifica la presencia web a partir de la URL declarada en Places."""
    if not website or not website.strip():
        return WebPresence.NONE

    host = re.sub(r"^https?://", "", website.strip().lower()).split("/")[0]
    host = host.removeprefix("www.")

    if any(host == social or host.endswith(f".{social}") for social in _SOCIAL_HOSTS):
        return WebPresence.SOCIAL_ONLY

    return WebPresence.HAS_SITE


@dataclass(frozen=True, slots=True)
class Prospect:
    """Un negocio candidato, tal como lo devuelve Google Places.

    Frozen porque el resultado del discovery es un hecho observado: las etapas
    posteriores producen objetos nuevos en vez de mutar este.
    """

    place_id: str
    name: str
    vertical: str
    metro: str
    phone: str | None = None
    website: str | None = None
    rating: float | None = None
    review_count: int = 0
    address: str | None = None
    services: tuple[str, ...] = ()
    top_reviews: tuple[str, ...] = ()

    @property
    def web_presence(self) -> WebPresence:
        return classify_web_presence(self.website)

    @property
    def slug(self) -> str:
        """Slug estable y único para URLs de demo.

        Combina el nombre legible con un hash corto del place_id: legible para el
        prospecto, pero sin colisiones entre negocios homónimos del mismo rubro.
        """
        base = re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")[:40]
        digest = hashlib.sha256(self.place_id.encode()).hexdigest()[:6]
        return f"{base or 'business'}-{digest}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Prospect:
        return cls(
            place_id=data["place_id"],
            name=data["name"],
            vertical=data["vertical"],
            metro=data["metro"],
            phone=data.get("phone"),
            website=data.get("website"),
            rating=data.get("rating"),
            review_count=data.get("review_count", 0),
            address=data.get("address"),
            services=tuple(data.get("services", ())),
            top_reviews=tuple(data.get("top_reviews", ())),
        )


@dataclass(frozen=True, slots=True)
class PainScore:
    """Cuánto le duele al negocio su presencia digital actual.

    Escala 0-100, mayor es más dolor y por lo tanto mejor prospecto. Se compone de
    señales objetivas (Lighthouse) y estructurales (no tener sitio).
    """

    place_id: str
    performance: int | None = None
    """Lighthouse performance 0-100. None si no hay sitio que medir."""

    seo: int | None = None
    accessibility: int | None = None
    mobile_friendly: bool | None = None
    has_web_presence: bool = True
    reachable: bool = True
    """False si el sitio declarado da timeout o 5xx: el ángulo de venta más fuerte."""

    notes: tuple[str, ...] = ()

    @property
    def score(self) -> int:
        """Pain score compuesto 0-100.

        No tener sitio es el máximo dolor posible (100): no hay nada que arreglar,
        solo que construir, y no hay incumbente que defienda la posición.
        """
        if not self.has_web_presence:
            return 100
        if not self.reachable:
            return 95

        # Promedio ponderado de (dolor, peso). Invertimos los scores de Lighthouse:
        # bajo rendimiento = alto dolor. Los pesos van aparte del valor a propósito:
        # bajar el valor y promediar por conteo completo diluiría el score global en
        # vez de restarle importancia solo a esa señal.
        signals: list[tuple[float, float]] = []
        if self.performance is not None:
            signals.append((100 - self.performance, 1.0))
        if self.seo is not None:
            signals.append((100 - self.seo, 1.0))
        if self.accessibility is not None:
            # Importa, pero no es lo que le duele al dueño de una plomería.
            signals.append((100 - self.accessibility, 0.5))
        if self.mobile_friendly is False:
            # En home services el tráfico es casi puramente móvil: un sitio que no
            # es usable en teléfono domina a cualquier otra señal.
            signals.append((90, 2.0))

        if not signals:
            return 0

        total_weight = sum(weight for _, weight in signals)
        weighted = sum(value * weight for value, weight in signals) / total_weight
        return max(0, min(100, round(weighted)))

    @property
    def is_qualified(self) -> bool:
        """Umbral de corte para gastar tiempo generando una demo."""
        return self.score >= 45

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["score"] = self.score
        data["is_qualified"] = self.is_qualified
        return data


class ContactChannel(StrEnum):
    """Canal por el que se contacta a un prospecto.

    Deliberadamente **no** existe un canal "email scrapeado". Recolectar direcciones
    de forma automatizada desde sitios web es una *aggravated violation* de CAN-SPAM
    —agrava las multas en vez de solo aplicarlas— y además falla justo con los mejores
    prospectos, que son los que no tienen sitio del cual scrapear nada.

    Tampoco existe SMS: el TCPA exige consentimiento previo expreso por escrito para
    mensajes comerciales, con multas de USD 500-1.500 por mensaje.
    """

    PHONE = "phone"
    """Llamada. Convierte más que nada y las llamadas B2B a líneas comerciales están
    mayormente exentas del registro de no-llamar. No escala, y no necesita hacerlo:
    es el canal de los prospectos de mayor dolor, que son pocos."""

    CONTACT_FORM = "contact_form"
    """Formulario del propio sitio del negocio. Llega a la bandeja que sí leen y no
    es recolección de direcciones. Se completa a mano."""

    UNREACHABLE = "unreachable"
    """Sin teléfono y sin formulario ubicable. Se descarta."""


@dataclass(frozen=True, slots=True)
class ContactPlan:
    """Cómo contactar a un prospecto concreto, y por qué así."""

    place_id: str
    channel: ContactChannel
    target: str | None
    """Teléfono a marcar o URL del formulario. None si es UNREACHABLE."""

    rationale: str
    pain_score: int = 0

    @property
    def is_actionable(self) -> bool:
        return self.channel is not ContactChannel.UNREACHABLE and bool(self.target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "place_id": self.place_id,
            "channel": self.channel.value,
            "target": self.target,
            "rationale": self.rationale,
            "pain_score": self.pain_score,
            "is_actionable": self.is_actionable,
        }


class SuppressionReason(StrEnum):
    """Por qué un prospecto no debe volver a ser contactado."""

    CONTACTED = "contacted"
    """Ya se le escribió. Evita la segunda corrida sobre el mismo metro."""

    OPTED_OUT = "opted_out"
    """Pidió no ser contactado. CAN-SPAM obliga a honrarlo en ≤10 días hábiles."""

    NOT_INTERESTED = "not_interested"
    CUSTOMER = "customer"
    """Ya compró: sacarlo de prospección, no de la lista de clientes."""

    INVALID = "invalid"
    """Datos incorrectos o el negocio cerró."""

    @property
    def is_permanent(self) -> bool:
        """OPTED_OUT no vence nunca. CONTACTED sí puede reintentarse más adelante."""
        return self in (SuppressionReason.OPTED_OUT, SuppressionReason.CUSTOMER)


class FunnelEvent(StrEnum):
    """Escalones de la escalera de compromiso, en orden.

    El clic no está: mide curiosidad y no disposición a pagar, así que registrarlo
    invitaría a decidir con él.
    """

    CONTACTED = "contacted"
    REPLIED = "replied"
    CALL_BOOKED = "call_booked"
    PROPOSAL_SENT = "proposal_sent"
    PAID = "paid"

    @property
    def level(self) -> int:
        return _FUNNEL_LEVELS[self]


_FUNNEL_LEVELS: dict[FunnelEvent, int] = {
    FunnelEvent.CONTACTED: 1,
    FunnelEvent.REPLIED: 2,
    FunnelEvent.CALL_BOOKED: 3,
    FunnelEvent.PROPOSAL_SENT: 4,
    FunnelEvent.PAID: 5,
}


@dataclass(frozen=True, slots=True)
class Demo:
    """Una demo renderizada y (opcionalmente) publicada."""

    place_id: str
    slug: str
    html_path: str
    url: str | None = None
    deployed_at: datetime | None = None

    @property
    def is_live(self) -> bool:
        """Una demo sin URL pública no sirve para prospectar: es un mockup."""
        return self.url is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "place_id": self.place_id,
            "slug": self.slug,
            "html_path": self.html_path,
            "url": self.url,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "is_live": self.is_live,
        }


@dataclass(frozen=True, slots=True)
class SenderIdentity:
    """Identidad del remitente. CAN-SPAM exige que sea real y verificable.

    La dirección postal física es obligatoria en todo email comercial; no es
    opcional ni decorativa.
    """

    from_name: str
    from_email: str
    physical_address: str
    unsubscribe_url: str

    def validate(self) -> None:
        """Falla ruidosamente antes de enviar, no después."""
        if not self.from_name.strip():
            raise ComplianceError("from_name vacío: CAN-SPAM exige remitente identificable")
        if "@" not in self.from_email:
            raise ComplianceError(f"from_email inválido: {self.from_email!r}")
        # Una dirección postal real tiene número y calle; 5 caracteres no alcanzan.
        if len(self.physical_address.strip()) < 15:
            raise ComplianceError(
                "physical_address demasiado corta: CAN-SPAM exige dirección postal válida"
            )
        if not self.unsubscribe_url.startswith(("http://", "https://", "mailto:")):
            raise ComplianceError(
                f"unsubscribe_url debe ser http(s) o mailto: {self.unsubscribe_url!r}"
            )


@dataclass(frozen=True, slots=True)
class OutreachEmail:
    """Email de prospección listo para enviar, ya validado contra CAN-SPAM."""

    place_id: str
    to_email: str | None
    subject: str
    body: str
    sender: SenderIdentity
    demo_url: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "place_id": self.place_id,
            "to_email": self.to_email,
            "subject": self.subject,
            "body": self.body,
            "demo_url": self.demo_url,
            "created_at": self.created_at.isoformat(),
        }
