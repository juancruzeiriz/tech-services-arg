-- Sub-scores por dimensión, datos de campo (CrUX) y hallazgos forenses.
--
-- Los sub-scores se denormalizan por el mismo motivo que ya documenta 0001
-- para score/is_qualified: acá queda el valor tal como era en el momento de
-- la medición, no recalculado con los pesos de mañana si `PainScore.score`
-- cambia de fórmula más adelante.
alter table scores add column if not exists speed_score       int;
alter table scores add column if not exists mobile_score      int;
alter table scores add column if not exists seo_score         int;
alter table scores add column if not exists modernity_score   int;
alter table scores add column if not exists conversion_score  int;

-- Datos de campo reales (Chrome UX Report), no simulados como el resto de
-- PainScore. has_field_data distingue "sin datos de campo" de "0 = bueno":
-- sin esto, un sitio chico sin tráfico suficiente para CrUX se vería igual
-- que un sitio con LCP de 0ms.
alter table scores add column if not exists crux_lcp_ms       int;
alter table scores add column if not exists crux_inp_ms       int;
alter table scores add column if not exists crux_cls          numeric(4,3);
alter table scores add column if not exists has_field_data    boolean not null default false;

-- Última vez que el contenido del sitio cambió de verdad, según la Wayback
-- Machine (collapse=digest -- ver gtm/factory/archive.py). Null si el
-- Archive no tenía capturas o no respondió.
alter table scores add column if not exists last_changed      date;

-- Un array de objetos {code, evidence, weight}, no columnas por hallazgo:
-- la lista de hallazgos posibles crece en gtm/factory/findings.py sin que
-- este esquema tenga que migrar cada vez que se agrega uno.
alter table scores add column if not exists findings          jsonb not null default '[]';

create index if not exists idx_scores_findings on scores using gin (findings);
