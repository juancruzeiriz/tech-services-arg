"""Modelos de datos del pipeline de prospección.

Flujo: Prospect (discover) -> PainScore (score) -> Demo (generate/deploy) -> OutreachEmail.

Cada etapa es idempotente y se identifica por `Prospect.place_id`, el ID estable de
Google Places. Re-correr una etapa sobre el mismo prospecto produce el mismo resultado.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Import solo para tipos: gtm.factory.findings importa Language de este
    # mismo módulo, así que un import real acá (no bajo TYPE_CHECKING)
    # sería un ciclo. `from __future__ import annotations` ya vuelve string
    # toda anotación, así que en runtime nunca hace falta resolver Finding.
    from gtm.factory.findings import Finding


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


# Dominios que no son un sitio web propio, solo un perfil en plataforma ajena: redes
# sociales, directorios de terceros (Angi, HomeAdvisor, Thumbtack, Porch, Houzz, BBB,
# Yellow Pages) y constructores de subdominio gratis (Weebly, GoDaddy Sites,
# Squarespace, WordPress.com, Google Sites). Un perfil en cualquiera de estos no es
# presencia web propia: el negocio no lo controla, no rankea a su nombre y puede
# desaparecer si el directorio cierra la cuenta.
_THIRD_PARTY_HOSTS: frozenset[str] = frozenset(
    {
        "facebook.com",
        "m.facebook.com",
        "instagram.com",
        "linktr.ee",
        "yelp.com",
        "nextdoor.com",
        "business.site",  # Google Business "sitios" autogenerados
        "wixsite.com",
        "angi.com",
        "homeadvisor.com",
        "thumbtack.com",
        "porch.com",
        "houzz.com",
        "bbb.org",
        "yellowpages.com",
        "weebly.com",
        "godaddysites.com",
        "squarespace.com",
        "wordpress.com",
        "sites.google.com",
    }
)


class DigitalTrace(StrEnum):
    """Qué tan segura es la ausencia digital de un prospecto que Google Maps
    reporta como `WebPresence.NONE`/`SOCIAL_ONLY` -- resultado de la Capa 2 de
    verificación (`gtm.factory.verify.verify_absence`). Google Maps es una
    sola fuente y el negocio pudo no vincular un dominio propio que sí existe;
    este campo es la corroboración antes de asignar el dolor máximo (100) y
    de afirmarle al prospecto, en el primer renglón del mensaje, que no
    tiene sitio -- una afirmación que tiene que ser verdad."""

    OWN_DOMAIN = "own_domain"
    """Se encontró y corroboró un dominio propio: la ausencia era falsa."""

    DIRECTORY_ONLY = "directory_only"
    """Solo aparece en directorios de terceros (Yelp, Angi, Facebook...): sigue
    siendo candidato de ausencia digital real, no tiene sitio que controle."""

    NO_TRACE = "no_trace"
    """Ninguna señal relevante encontrada: candidato de dolor máximo."""

    UNVERIFIED = "unverified"
    """No se pudo verificar (sin `GTM_SEARCH_API_KEY` o falló la red). Default:
    se trata igual que `NO_TRACE` para el score, pero queda documentado que no
    hubo una segunda fuente que lo confirme."""


class Language(StrEnum):
    """Idioma del mensaje enviado al prospecto.

    Determina el texto de los tres builders de mensajes (`outreach.build_body`,
    `contact.build_form_message`, `contact.build_call_script`) y de la demo. Se
    registra en el embudo porque "no responden en inglés" y "no responden en
    español" son hipótesis de vertical distintas — sin esto no se pueden separar.

    Definido acá arriba (no junto a los otros StrEnum del archivo) porque
    `vertical_label`/`vertical_plural`, un poco más abajo, lo usan como default de
    parámetro — y un default se evalúa en el momento de definir la función, no de
    llamarla, así que tiene que existir antes en el archivo pese a que
    `from __future__ import annotations` difiere la evaluación de las anotaciones.
    """

    EN = "en"
    ES = "es"


def _catalog_vertical_labels() -> dict[str, str]:
    """`VERTICAL_LABELS` derivado de `gtm/catalog/trades.yaml`. Función, no un
    diccionario literal, para que quede claro que el catálogo es la fuente de
    verdad y esto es una vista de compatibilidad hacia atrás."""
    from gtm.catalog import trades

    return {trade.key: trade.label_en for trade in trades()}


# Cómo se nombra cada rubro en el inglés que usa el cliente final. Compartido entre
# la demo y el email: si el sitio dice "HVAC contractor" y el email dice "hvac", el
# prospecto nota que hay una plantilla atrás. Antes era el propio catálogo (5
# entradas hardcodeadas); ahora es una vista de `gtm/catalog/trades.yaml` (15).
VERTICAL_LABELS: dict[str, str] = _catalog_vertical_labels()


def vertical_label(vertical: str, language: Language = Language.EN) -> str:
    """Etiqueta legible del rubro.

    Busca primero en el catálogo curado (`gtm/catalog/trades.yaml`); si el vertical
    no está ahí —texto libre desde la UI, un oficio que todavía no se agregó— cae al
    valor crudo. Ese fallback es lo que sostiene la opción "otro oficio": nunca
    debe convertirse en un error.
    """
    from gtm.catalog import get_trade

    trade = get_trade(vertical)
    if trade is not None:
        return trade.label(language.value)
    return VERTICAL_LABELS.get(vertical.lower(), vertical)


def vertical_plural(vertical: str, language: Language = Language.EN) -> str:
    """Plural legible del rubro: "HVAC contractors", no "hvacs".

    Si el catálogo trae un plural curado a mano se usa ese; si no —oficio de texto
    libre— cae a la heurística original (agregar "s" si no termina en una ya), que
    es la que tiene la suite de regresión de "hvacs" -> "HVAC contractors". Existe
    porque interpolar el vertical crudo produce texto que delata la plantilla en la
    primera línea del mensaje, que es exactamente donde no podés perder al lector.
    """
    from gtm.catalog import get_trade

    trade = get_trade(vertical)
    if trade is not None:
        plural = trade.plural(language.value)
        if plural.strip():
            return plural
    label = vertical_label(vertical, language)
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

    if any(host == third_party or host.endswith(f".{third_party}") for third_party in _THIRD_PARTY_HOSTS):
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


# Peso de cada dimensión en el promedio final de `PainScore.score`. Conversión
# pesa más que nada porque "no te pueden llamar" cuesta plata hoy, no en
# abstracto; modernity pesa menos porque es la señal más subjetiva de las
# cinco. mobile queda en 2.0 (no en una escala más "pareja" con las demás) a
# propósito: es exactamente el peso que ya tenía `mobile_friendly is False`
# antes de que existieran dimensiones, y en home services el tráfico es casi
# puro celular — bajarlo habría hecho que un sitio no apto para móvil dejara
# de calificar por sí solo, que es la garantía que este score siempre dio.
_DIMENSION_WEIGHTS: dict[str, float] = {
    "speed": 1.0,
    "mobile": 2.0,
    "seo": 1.0,
    "modernity": 0.8,
    "conversion": 2.0,
}

# Cuánto pain-value de base aporta un Finding a su dimensión, por unidad de
# FindingSpec.weight (que va de 1.0 a 3.0). Un hallazgo CRITICAL (weight 3.0)
# solo aporta 90/100 a su dimensión: ni un hallazgo aislado la satura del
# todo, pero varios hallazgos en la misma dimensión sí pueden acercarse a 100.
_FINDING_PAIN_SCALE = 30.0

# Ranking para ordenar sales_lines() del hallazgo más grave al menos grave.
# Valores literales (no el enum Severity) para no importar gtm.factory.findings
# en tiempo de ejecución — ver el comentario de TYPE_CHECKING más arriba.
_SEVERITY_RANK: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass(frozen=True, slots=True)
class PainScore:
    """Cuánto le duele al negocio su presencia digital actual.

    Escala 0-100, mayor es más dolor y por lo tanto mejor prospecto. Se compone de
    señales de laboratorio (Lighthouse), de campo (CrUX), forenses (HTML crudo) y
    estructurales (no tener sitio).
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

    findings: tuple[Finding, ...] = ()
    """Hallazgos forenses/de campo con evidencia citable — ver gtm.factory.findings."""

    crux_lcp_ms: int | None = None
    crux_inp_ms: int | None = None
    crux_cls: float | None = None
    has_field_data: bool = False
    """True si CrUX tenía datos de campo reales (no solo el laboratorio)."""

    last_changed: date | None = None
    """Última vez que el contenido del sitio cambió de verdad (Wayback CDX)."""

    digital_trace: DigitalTrace = DigitalTrace.UNVERIFIED
    """Resultado de la Capa 2 de verificación (`gtm.factory.verify`) cuando
    `has_web_presence` es False. No participa en `score`: es informativo,
    para que `notes` y el copy de venta sepan qué tan segura es la ausencia."""

    verified_domain: str | None = None
    """El dominio propio encontrado y corroborado, si `digital_trace` es
    `OWN_DOMAIN`. None en cualquier otro caso."""

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

        # Promedio ponderado de (dolor, peso) entre las dimensiones que
        # tuvieron ALGUNA señal (de laboratorio o de hallazgos) y, aparte,
        # accessibility como término directo. Una dimensión sin ninguna señal
        # se EXCLUYE del promedio en vez de contar como "sin dolor" — si no se
        # midió algo, no corresponde que reste.
        blend: list[tuple[float, float]] = []
        for dimension, values in self._dimension_pain_values().items():
            combined = self._combine_pain(values)
            if combined is not None:
                blend.append((combined, _DIMENSION_WEIGHTS[dimension]))

        if self.accessibility is not None:
            # Importa, pero no es lo que le duele al dueño de una plomería, y
            # conceptualmente no es "mobile-friendliness" — por eso queda
            # fuera de toda dimensión, como señal directa de peso bajo, igual
            # que antes de que existieran dimensiones.
            blend.append((100.0 - self.accessibility, 0.5))

        if not blend:
            return 0

        total_weight = sum(weight for _, weight in blend)
        weighted = sum(value * weight for value, weight in blend) / total_weight
        return max(0, min(100, round(weighted)))

    @property
    def is_qualified(self) -> bool:
        """Umbral de corte para gastar tiempo generando una demo."""
        return self.score >= 45

    @property
    def sub_scores(self) -> dict[str, int]:
        """Pain 0-100 por cada una de las cinco dimensiones, para mostrar en
        pantalla o citar en el copy de venta. A diferencia de `score`, acá
        una dimensión sin señal se muestra en 0 — este diccionario es para
        leer, no para promediar (eso ya lo hace `score`)."""
        return {
            dimension: round(self._combine_pain(values) or 0.0)
            for dimension, values in self._dimension_pain_values().items()
        }

    def sales_lines(self, language: Language, *, quotable_only: bool = True) -> list[str]:
        """Las líneas de venta de los hallazgos, del más grave al menos grave.

        `quotable_only=True` (default) es lo que usa `outreach.py` para el gancho del
        email/mensaje: se salta cualquier `Finding` cuyo `spec.quotable` sea False —
        evidencia real pero todavía no validada lo suficiente como para afirmarla en
        frío (ver `FindingSpec.quotable`). El informe interno de `audit.py` pasa
        `quotable_only=False` a propósito: es material de apoyo para la llamada, no
        algo que se le manda al prospecto, así que ahí sí conviene ver todo.
        """
        ordered = sorted(self.findings, key=lambda f: _SEVERITY_RANK[f.spec.severity.value])
        if quotable_only:
            ordered = [f for f in ordered if f.spec.quotable]
        return [f.sales_line(language) for f in ordered]

    def _dimension_pain_values(self) -> dict[str, list[float]]:
        """Valores de dolor (0-100) por dimensión, antes de combinar. `speed`
        y `seo` incluyen la señal de laboratorio correspondiente; `mobile`
        incluye `mobile_friendly is False`; las cinco suman los Finding que
        caen en esa dimensión. `accessibility` NO entra acá — ver `score`."""
        values: dict[str, list[float]] = {d: [] for d in _DIMENSION_WEIGHTS}

        if self.performance is not None:
            values["speed"].append(100.0 - self.performance)
        if self.seo is not None:
            values["seo"].append(100.0 - self.seo)
        if self.mobile_friendly is False:
            # En home services el tráfico es casi puramente móvil: un sitio que
            # no es usable en teléfono domina a cualquier otra señal.
            values["mobile"].append(90.0)

        for finding in self.findings:
            dimension = finding.spec.dimension.value
            values.setdefault(dimension, []).append(min(100.0, finding.weight * _FINDING_PAIN_SCALE))

        return values

    @staticmethod
    def _combine_pain(values: list[float]) -> float | None:
        """Combina las señales de dolor de una misma dimensión con OR
        ruidoso en vez de promediarlas: dos hallazgos reales en la misma
        dimensión tienen que doler MÁS que uno solo, nunca menos, y un
        promedio diluiría al más grave con el más leve. Con una sola señal
        da exactamente esa señal — por eso `score` no cambió para ningún
        caso que ya tenía cobertura de tests antes de que existiera esto.
        """
        if not values:
            return None
        product = 1.0
        for value in values:
            product *= 1.0 - max(0.0, min(100.0, value)) / 100.0
        return (1.0 - product) * 100.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["score"] = self.score
        data["is_qualified"] = self.is_qualified
        data["sub_scores"] = self.sub_scores
        data["digital_trace"] = self.digital_trace.value
        if self.last_changed is not None:
            data["last_changed"] = self.last_changed.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PainScore:
        """Reconstruye desde `to_dict()`. Ignora `score`/`is_qualified`/`sub_scores`:
        son propiedades derivadas, no campos — pasarlas al constructor rompería."""
        from gtm.factory.findings import Finding  # import local: rompe el ciclo en runtime

        last_changed_raw = data.get("last_changed")
        return cls(
            place_id=data["place_id"],
            performance=data.get("performance"),
            seo=data.get("seo"),
            accessibility=data.get("accessibility"),
            mobile_friendly=data.get("mobile_friendly"),
            has_web_presence=data.get("has_web_presence", True),
            reachable=data.get("reachable", True),
            notes=tuple(data.get("notes", ())),
            findings=tuple(
                Finding(
                    code=f["code"],
                    evidence=f["evidence"],
                    weight=f.get("weight", 1.0),
                    extra=f.get("extra", {}),
                )
                for f in data.get("findings", ())
            ),
            crux_lcp_ms=data.get("crux_lcp_ms"),
            crux_inp_ms=data.get("crux_inp_ms"),
            crux_cls=data.get("crux_cls"),
            has_field_data=data.get("has_field_data", False),
            last_changed=date.fromisoformat(last_changed_raw) if last_changed_raw else None,
            digital_trace=DigitalTrace(data.get("digital_trace", DigitalTrace.UNVERIFIED.value)),
            verified_domain=data.get("verified_domain"),
        )


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContactPlan:
        """Reconstruye desde `to_dict()`. Ignora `is_actionable`: es derivado."""
        return cls(
            place_id=data["place_id"],
            channel=ContactChannel(data["channel"]),
            target=data.get("target"),
            rationale=data.get("rationale", ""),
            pain_score=data.get("pain_score", 0),
        )


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

    BOUNCED = "bounced"
    """Un email a esta dirección rebotó duro (5xx): la dirección no existe.
    Reintentar solo sube la tasa de rebote, que es lo que más rápido quema la
    reputación del dominio de envío -- ver docs/CHANNELS.md."""

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

    language: Language = Language.EN
    """Idioma en el que se renderizó esta demo (`gtm.factory.lang.detect_language`
    o el default de la corrida). Vive acá y no en la corrida porque la demo ya
    se renderiza con `lang` adentro (`generate.render`) -- es un hecho de este
    artefacto puntual, no de la corrida entera: dos prospectos de la misma
    corrida pueden terminar en idiomas distintos."""

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
            "language": self.language.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Demo:
        """Reconstruye desde `to_dict()`. Ignora `is_live`: es derivado."""
        deployed_at = data.get("deployed_at")
        return cls(
            place_id=data["place_id"],
            slug=data["slug"],
            html_path=data["html_path"],
            url=data.get("url"),
            deployed_at=datetime.fromisoformat(deployed_at) if deployed_at else None,
            language=Language(data.get("language", Language.EN.value)),
        )


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
    language: Language = Language.EN

    def to_dict(self) -> dict[str, Any]:
        return {
            "place_id": self.place_id,
            "to_email": self.to_email,
            "subject": self.subject,
            "body": self.body,
            "demo_url": self.demo_url,
            "created_at": self.created_at.isoformat(),
            "language": self.language.value,
            # El sender iba ausente antes: el round-trip era con pérdida y
            # `from_dict` no podía existir. Aditivo — nada en el repo leía este
            # dict de vuelta, así que no hay formato previo que romper.
            "from_name": self.sender.from_name,
            "from_email": self.sender.from_email,
            "physical_address": self.sender.physical_address,
            "unsubscribe_url": self.sender.unsubscribe_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutreachEmail:
        return cls(
            place_id=data["place_id"],
            to_email=data.get("to_email"),
            subject=data["subject"],
            body=data["body"],
            sender=SenderIdentity(
                from_name=data["from_name"],
                from_email=data["from_email"],
                physical_address=data["physical_address"],
                unsubscribe_url=data["unsubscribe_url"],
            ),
            demo_url=data.get("demo_url"),
            created_at=datetime.fromisoformat(data["created_at"]),
            language=Language(data.get("language", Language.EN.value)),
        )
