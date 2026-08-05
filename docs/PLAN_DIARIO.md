# Plan diario — 20 sesiones de 30-60 min

Se lee junto a [`docs/PROCESOS.md`](PROCESOS.md). Corre **antes y en paralelo** de
[`gtm/plan_aprendizaje.md`](../gtm/plan_aprendizaje.md) — lo complementa, no lo reemplaza: ese
plan cubre inmersión de mercado (foros, entrevistas de problema) y calibración de guion; este
plan cubre entender y debuggear el mecanismo del pipeline mismo, nodo por nodo.

**No arranca el experimento pre-registrado.** Los 200 contactos reales de
[`decision_criteria.yaml`](../gtm/decision_criteria.yaml) empiezan después del día 20. Cambiar
el guion o el criterio a mitad del experimento es exactamente lo que ese archivo existe para
bloquear — así que toda la iteración tiene que pasar antes del primer contacto real.

## Ritual de cada sesión

1. **5 min** — releer la ficha del nodo de hoy en `PROCESOS.md`.
2. **20-40 min** — el ejercicio del día. Uno solo. Si no entra en el tiempo, se corta y se anota
   dónde se quedó — no se estira la sesión.
3. **5-10 min** — escribir el hallazgo en la ficha del nodo (Problemas conocidos / Bitácora) y
   tildar el día acá abajo.

**Regla dura de la Fase B**: todo hallazgo se escribe como *hipótesis falsable + medición
barata*, nunca como opinión suelta. Ejemplo: no "el corte de 45 deja pasar sitios que están
bien", sino "de 10 sitios que el score califica, yo a mano descarto N — si N≥4 el corte está mal
calibrado".

---

## Fase A — El QUÉ (días 1-8): entender antes de opinar

- [ ] **Día 1** (60 min, setup) — Commit+push del incremento pendiente del sitio. Confirmar que
  `docs/PROCESOS.md` está creado con los 3 diagramas y las 14 fichas. Publicar el Artifact
  navegable. *Salida: el mapa existe y se puede mirar desde el celular.*

- [ ] **Día 2** (45 min, Nodo 0) — Abrir juancruzeiriz.com en celular **y** desktop. Escribir la
  lista de qué está mal, priorizada. El gap ya identificado —el nav desaparece en <860px sin
  reemplazo por hamburguesa— entra en la lista, no la agota. *Salida: lista priorizada con
  captura de pantalla.*

- [ ] **Día 3** (45 min, Nodo 1) — Leer `gtm/catalog/trades.yaml` y `metros.yaml` completos.
  Reconstruir a mano las dos fórmulas de `rank` con 3 ejemplos del catálogo. Elegir 1 oficio × 1
  metro y escribir en 5 renglones por qué ese y no el #2 del ranking. *Salida: par elegido, con
  justificación escrita.*

- [ ] **Día 4** (45 min, Nodo 2) — Leer `gtm/factory/discover.py` completo. Correr `simulate`
  con el par elegido, después `discover` real con `--limit 10`. Contar cuántos de los devueltos
  califican y por qué filtro se cae cada uno de los descartados. *Salida: ratio de calificación
  real, no supuesto.*

  > Verificado el pipeline en simulación en esta máquina: `simulate` → `generate --all` →
  > `deploy` → `contact --queue` corren sin errores (requiere `PYTHONPATH=$(pwd)`,
  > `GTM_FROM_NAME` seteado, y los paquetes de `requirements.txt` runtime: `httpx`,
  > `python-dotenv`, `beautifulsoup4`, `PyYAML`). Con datos simulados, `contact` necesita
  > `--no-probe` — las URLs simuladas no responden de verdad, así que sin esa flag todo cae a
  > "no se ubicó formulario" en vez de detectar el formulario real.

- [ ] **Día 5** (60 min, Nodos 3+4) — Leer `score.py` y `PainScore.score` en `types.py` línea por
  línea. Correr `score` sobre los 10 del día 4. Mirar `sub_scores` de cada uno. Recién después,
  abrir 3 de esos sitios a mano en el celular. *Salida: comparación score-vs-juicio en 3 casos.*

- [ ] **Día 6** (45 min, Nodos 5+6) — `generate --all` + `deploy --dry-run`. Abrir 3 demos en el
  celular. Cronometrar cuánto tardan en cargar y en cuántos segundos se nota que es plantilla.
  *Salida: nota de 3 renglones por demo.*

- [ ] **Día 7** (45 min, Nodos 7+8+9) — `contact --queue`. Leer la cola completa. Leer el guion
  de llamada **en voz alta** y el email generado completo. *Salida: marcas en el texto de lo que
  suena falso o forzado.*

- [ ] **Día 8** (60 min, Nodos 10-13, cierre de fase) — Leer `pipeline.md` (guiones, objeciones),
  `validation.md`, `decision_criteria.yaml` completos. Correr `ledger report`. Releer el mapa
  entero y corregir lo que resultó distinto de lo que creías al empezar. *Salida: mapa
  corregido.*

## Fase B — El CÓMO (días 9-16): debuggear cada pata

- [ ] **Día 9** (45 min, Nodo 1) — Los `avg_ticket_usd` marcados "estimado" en `trades.yaml` no
  tienen fuente. Buscar 2 fuentes reales para el oficio elegido. Además: si `mini_tcpa_risk:
  true` en el metro elegido, leer la ley de telemarketing de ese estado.

- [ ] **Día 10** (45 min, Nodo 2) — ¿`MIN_REVIEWS=50` y `MIN_RATING=4.0` dejan afuera a los
  mejores prospectos? Correr con los filtros bajados (ej. 20/3.5) y comparar los dos conjuntos.
  Medir también el costo de Places por prospecto útil.

- [ ] **Día 11** (60 min, Nodo 3 — el día más denso) — Calibrar el score contra tu propio juicio
  en 10 sitios reales: puntuar vos primero de 0-100 a ojo, después mirar el score del pipeline.
  Si la correlación es mala, el problema son los pesos de dimensión o el corte de 45 — no el
  código.

- [ ] **Día 12** (45 min, Nodo 4) — ¿Cuántos hallazgos salen por prospecto en promedio? ¿Hay
  falsos positivos (revisar en particular `dated_palette`, `legacy_jquery`)? ¿La línea de venta
  del hallazgo más grave se lee natural en voz alta delante de un plomero?

- [ ] **Día 13** (45 min, Nodos 5+6) — ¿La demo se reconoce como plantilla? Mostrarle 2 demos a
  alguien que no sabe nada del proyecto y preguntarle qué negocio es. Medir el Lighthouse de la
  propia demo generada.

- [ ] **Día 14** (45 min, Nodo 7) — Tasa de detección de formulario: de N sitios con presencia
  web, cuántos resuelven a `CONTACT_FORM`, cuántos caen a teléfono y cuántos quedan
  `UNREACHABLE`. Cada `UNREACHABLE` es un prospecto puntuado y tirado.

- [ ] **Día 15** (45 min, Nodo 8) — Leer los 3 mensajes en los 2 idiomas, en voz alta. El
  español no es traducción del inglés: ¿suena a alguien de Argentina hablándole a un dueño de
  negocio en Houston, o a traducción automática?

- [ ] **Día 16** (60 min, Nodos 10+11) — Roleplay completo: apertura de 20 s + llamada de 20
  min, ensayando las 3 objeciones documentadas en `validation.md`. Cronometrar. Si la apertura
  pasa de 25 segundos, sobra texto.

## Fase C — El PARA QUÉ (días 17-20)

- [ ] **Día 17** (60 min) — **Números unitarios.** Con los tiempos medidos en las fases A y B:
  minutos por prospecto en cada etapa, USD/hora proyectado, y cuántas horas cuesta llegar a los
  200 contactados de `decision_criteria.yaml` al ritmo de 5-10 hs/semana. *Salida: tabla de
  economía unitaria agregada a `PROCESOS.md`.*

- [ ] **Día 18** (45 min) — **El criterio.** Releer `decision_criteria.yaml` entero, incluido el
  comentario sobre por qué v1 estaba mal calibrado (el error de potencia estadística). Correr
  `pytest tests/gtm/test_ledger_criteria.py`. Confirmar por escrito, con fecha, que no se toca.

- [ ] **Día 19** (45 min) — **Riesgo.** Correr `pytest tests/gtm/test_outreach.py -k canspam`.
  Revisar: ley mini-TCPA del estado elegido, no grabar llamadas, Factura E para el cobro desde
  USA. Dar de alta el email de envío (Zoho Mail) — es la única credencial que falta hoy.

- [ ] **Día 20** (60 min) — **Cierre.** Reescribir `PROCESOS.md` con todo lo aprendido en las 19
  sesiones anteriores, republicar el Artifact. Escribir el plan concreto de las primeras 25
  llamadas reales: qué días, a qué hora del huso horario del metro elegido, con qué guion ya
  calibrado.

---

## Después del día 20

Empieza la Fase de ejecución de `gtm/plan_aprendizaje.md` (semanas 5-8): los 200 contactos
reales. A las primeras `llamadas_de_calibracion: 50` del `corte_temprano_por_costo`, se
recalcula el corte por costo — ya definido en el yaml, no hay que decidir nada nuevo ahí.
