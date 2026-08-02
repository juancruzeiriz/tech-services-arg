# Plan de aprendizaje + implementación + simulación

Para no dejar el proyecto a medias por falta de terreno conocido. Corre **antes y
en paralelo** de las 8 semanas de `horizonte_semanas` en
[`decision_criteria.yaml`](decision_criteria.yaml) — no las reemplaza.

Total de horas por semana: el mismo rango ya acordado en
`corte_temprano_por_costo` (5-10 hs/semana). Lo único que cambia semana a semana
es en qué se usan.

## Semana 0 — Inmersión pasiva (4-6 hs, una sola vez)

- Leer completos los reportes citados en [`validation.md`](validation.md)
  (Jobber 2026, b2bleadfinder.io).
- Sumarse sin publicar a: un subreddit (r/Contractor o r/electricians) y a la
  newsletter/redes de una asociación real (NAHICA o Latin Builders Association).
- Elegir 1 oficio + 1 metro del catálogo (`gtm/catalog/trades.yaml`,
  `gtm/catalog/metros.yaml`) y mirar 15-20 negocios reales en Google Maps: cuántos
  no tienen sitio, cuántos no responden reseñas, cuántos tienen web pero no carga
  bien en el celular.
- **Meta de la semana:** poder explicar el problema y 3 objeciones típicas con
  palabras propias, sin leer la nota.

## Semanas 1-2 — Escucha activa, sin vender (5 hs/semana)

- Catalogar objeciones reales leyendo 20-30 hilos en los foros/grupos elegidos.
  Comparar contra la lista de `validation.md` — ¿aparecen objeciones nuevas que
  no estaban documentadas?
- Mandar 5-10 mensajes tipo "entrevista de problema" (no de venta) a dueños
  reales de Google Maps/Facebook: cómo manejan hoy su web, sus reseñas, los
  cobros. Sin ofrecer nada todavía.
- Practicar 2-3 llamadas por roleplay antes de escribirle a una persona real —
  usar el guion de apertura en [`pipeline.md`](pipeline.md).

## Semanas 3-4 — Simulación técnica + calibración del guion (5 hs/semana)

- Correr el pipeline completo con datos sintéticos, sin gastar cuota de Places
  ni PageSpeed:

  ```bash
  python -m gtm.factory.simulate --vertical plumber --metro "Tucson, AZ" --count 18
  python -m gtm.factory.score
  python -m gtm.factory.generate --all
  python -m gtm.factory.contact --queue
  ```

- Revisar la cola generada (`queue.md`): ¿el guion suena natural leído en voz
  alta? Ajustar antes de gastar el primer contacto real.
- Elegir definitivamente 1-2 combinaciones oficio+metro de mayor `rank` para el
  piloto (`trades.yaml`/`metros.yaml` ya vienen ordenados).
- Ensayar el guion completo (apertura + llamada de 20 min) en inglés **y** en
  español — `decision_criteria.yaml` exige segmentar por idioma desde el primer
  contacto, no después.

## Semanas 5-8 — Ejecución real (5-10 hs/semana, ya es el experimento pre-registrado)

- Arrancar los 200 contactos reales según `decision_criteria.yaml`.
- A las primeras `llamadas_de_calibracion: 50`, recalcular el corte por costo
  (ya definido en el yaml — no hay que decidir nada nuevo acá).
- Seguir mirando los foros ~30 min/semana como termómetro cualitativo. Esto
  **no** cambia el criterio congelado — es solo para no perder el hilo de qué
  objeciones son reales.

## Después de la semana 8

Leer el resultado del embudo (`funnel.jsonl` vía `ledger report`) y aplicar la
`regla_dura`: ganador, kill, o no concluyente. Si es kill, `accion_si_kill` ya
dice qué hacer — cambiar de vertical u oferta, no de redacción.
