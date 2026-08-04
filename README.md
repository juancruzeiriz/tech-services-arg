# tech-services-arg

Fábrica de demos de prospección para servicios técnicos exportados en USD, arrancando
en frío: sin marca, sin historial, con presupuesto y tiempo acotados.

## El problema y el reencuadre

Sin marca ni casos de estudio, nadie te contrata — y construir reputación de la forma
normal lleva años. La alternativa evaluada era validar demanda con anuncios pagos
(publicar N servicios, medir clics, quedarse con el ganador), y se descartó por
aritmética, no por gusto:

| Variable | Valor |
|---|---|
| CPC promedio B2B (AR, 2026) | ~USD 5,70 |
| Presupuesto disponible | USD 200 |
| Clics comprables | ~35 |
| Repartidos en 5 anuncios | **7 por brazo** |
| Conversión landing→lead típica | 2-5% |
| Leads esperados por brazo | **0** |

Un experimento cuyo resultado esperado es cero en todos los brazos no distingue la
hipótesis buena de la mala: no puede acertar ni fallar.

**El reencuadre:** si sobra capacidad de producción y falta confianza, hay que
**entregar el trabajo antes de la transacción**. El artefacto reemplaza a la marca —no
se pidió permiso, ya está hecho, está online, ahí está el link— y el prospecto no tiene
que creer nada: lo abre y lo ve. Eso solo escala si producir el artefacto es casi
gratis, así que **la automatización va en la prospección, no en la entrega**, que es lo
contrario de lo que se haría por instinto.

Ver [`gtm/README.md`](gtm/README.md) para el razonamiento completo, incluida la
aritmética completa y por qué se descartaron las ofertas tipo auditoría (requieren
credenciales del cliente, así que impiden hacer el trabajo primero).

**¿Por qué Estados Unidos y por qué oficios, puntualmente?** Eso está en
[`docs/WHY.md`](docs/WHY.md) — el documento que responde qué se ofrece exactamente, por
qué el contacto en frío es legal en USA y no en Europa (CAN-SPAM vs. GDPR), y las cuatro
condiciones que tienen que darse a la vez para que home services sea el vertical
correcto (y que ningún otro tipo de negocio chico cumple todas juntas).

## Qué hace

Vertical inicial: home services en USA (plomeros, HVAC, electricistas, techistas).
Pipeline: `discover` (Google Places) → `score` (PageSpeed) → `generate` (demo con datos
reales del negocio) → `deploy` (URL pública) → `contact` (canal + cola de trabajo,
teléfono o formulario — nunca email scrapeado ni SMS en frío) → `ledger` (supresión y
embudo, persistentes entre corridas).

El pipeline **prepara, no envía**: a 25 prospectos por semana, mandar a mano convierte
más y evita dos riesgos legales serios (harvesting de direcciones bajo CAN-SPAM, SMS
comercial en frío bajo TCPA).

## Quickstart

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.personal   # completar credenciales
```

### Opción A — UI (recomendada)

```bash
python -m gtm.ui
```

Abre `http://127.0.0.1:8787` (solo localhost, nunca expuesto a la red). Un
formulario con los ~15 parámetros del pipeline (oficio, metro, idioma, modo
simulado/real, precio de la oferta, etc.), progreso en vivo, cola de contacto
con guion listo para copiar y cronómetro de sesión, y dos dashboards —
embudo contra el criterio pre-registrado (con intervalos de Wilson) y
economía real (USD/hora efectivo, CAC, cohortes, correlación dolor↔conversión).
Sin `SUPABASE_DB_URL` configurada la UI funciona igual: lo que no se pudo
escribir en Postgres queda en un outbox local y se reintenta después. Ver
[`gtm/README.md`](gtm/README.md#ui) para el detalle.

### Opción B — CLI

```bash
export PYTHONPATH=$(pwd)

# Sin credenciales de Google, con datos sintéticos realistas:
python -m gtm.factory.simulate --vertical hvac --metro "Tucson, AZ"
python -m gtm.factory.generate --all --author-name "Tu Nombre" --author-url "https://tusitio.com"
python -m gtm.factory.deploy --base-url "https://demos.tusitio.com" --dry-run
python -m gtm.factory.contact --no-probe --queue
```

Pipeline completo (con credenciales reales en `.env.personal`):

```bash
python -m gtm.factory.discover --vertical hvac --metro "Tucson, AZ" --limit 20
python -m gtm.factory.score
python -m gtm.factory.generate --all
python -m gtm.factory.deploy
python -m gtm.factory.contact --queue
python -m gtm.factory.ledger report --spend 150
```

## Verificación

```bash
pytest tests/ -v                              # suite completa
pytest tests/gtm/test_outreach.py -k canspam   # gate de compliance, aislado
ruff check gtm/ tests/
mypy gtm/ --config-file mypy.ini
```

## Documentación

| Doc | Contenido |
|---|---|
| [`docs/WHY.md`](docs/WHY.md) | **Qué se ofrece, por qué USA, por qué oficios — empezar acá** |
| [`gtm/README.md`](gtm/README.md) | Pipeline técnico: etapas, configuración, reglas que el código hace cumplir |
| [`gtm/pipeline.md`](gtm/pipeline.md) | GTM comercial: oferta, precios, guion de venta, contrato, riesgos legales |
| [`gtm/decision_criteria.yaml`](gtm/decision_criteria.yaml) | Criterio de éxito/kill pre-registrado, verificado por test |
| [`gtm/offers/`](gtm/offers/) | One-pager de oferta, en inglés, para el prospecto |

## Estado

Pipeline completo, funcional end-to-end, con UI local, store en Postgres (con
degradación elegante sin él) y dos dashboards, con 418 tests. Falta la decisión que el
código no puede tomar: elegir el oficio y el metro reales, conseguir una API key de
Google Places, y hacer las primeras ~50 llamadas de calibración con negocios de verdad
— sin eso, "¿esto genera un ingreso extra?" sigue sin respuesta, sea cual sea la UI.
