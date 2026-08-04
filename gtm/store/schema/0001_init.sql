-- Esquema inicial del store analítico.
--
-- gtm/factory/ledger.py (gtm/suppression.jsonl, gtm/funnel.jsonl) sigue siendo
-- la fuente de verdad LOCAL para supresión y para el criterio de decisión
-- pre-registrado — esos archivos son hashes, van a git, y no dependen de la red.
-- Esto es el almacén CON detalle completo (nombres, teléfonos, el texto de los
-- emails) para hacer dashboards; nunca la fuente de la que el pipeline decide a
-- quién no volver a contactar.
--
-- No se edita este archivo una vez aplicado: ver gtm/store/migrate.py — el
-- runner rechaza correr si el checksum de una migración ya aplicada cambió.

-- id es `text`, no `uuid`: RunContext.run_id (gtm/factory/pipeline.py) es un hex
-- corto (uuid4().hex[:12]) para que sirva de nombre de directorio legible en
-- gtm/build/runs/<run_id>/, no un UUID completo. client_id más abajo sí es un
-- UUID real, generado aparte, con el propósito distinto de des-duplicar el
-- replay del outbox.
create table if not exists runs (
    id              text primary key,
    started_at      timestamptz not null,
    finished_at     timestamptz,
    vertical        text not null,
    metro           text not null,
    language        text not null default 'en',
    limit_n         int,
    simulated       boolean not null default false,
    dry_run         boolean not null default true,
    seed            int,
    author_name     text,
    base_url        text,
    status          text not null default 'running',  -- running | ok | failed
    error           text
);

-- Prospectos son un hecho GLOBAL, con clave place_id — no por corrida. Un mismo
-- negocio puede aparecer en varias corridas (re-escanear el mismo metro); guardar
-- por corrida perdería la pregunta "¿ya vimos este negocio antes?", que es la
-- que justifica tener esta tabla en primer lugar.
create table if not exists prospects (
    place_id        text primary key,
    first_seen_at   timestamptz not null,
    last_seen_at    timestamptz not null,
    name            text not null,
    vertical        text not null,
    metro           text not null,
    phone           text,
    website         text,
    rating          numeric(2,1),
    review_count    int not null default 0,
    address         text,
    web_presence    text not null
);

create table if not exists run_prospects (
    run_id      text not null references runs(id) on delete cascade,
    place_id    text not null references prospects(place_id) on delete cascade,
    position    int,
    primary key (run_id, place_id)
);

-- score/is_qualified se denormalizan a propósito: son lo que se filtra y se
-- grafica, y el peso de PainScore.score puede cambiar con el tiempo — acá queda
-- el valor tal como era en el momento de la medición, no recalculado después.
create table if not exists scores (
    id                  bigserial primary key,
    run_id              text references runs(id) on delete cascade,
    place_id            text not null references prospects(place_id) on delete cascade,
    measured_at         timestamptz not null,
    performance         int,
    seo                 int,
    accessibility       int,
    mobile_friendly     boolean,
    has_web_presence    boolean not null,
    reachable           boolean not null,
    score               int not null,
    is_qualified        boolean not null,
    notes               text[] not null default '{}',
    unique (run_id, place_id)
);

create table if not exists demos (
    id              bigserial primary key,
    run_id          text references runs(id) on delete cascade,
    place_id        text not null references prospects(place_id) on delete cascade,
    slug            text not null,
    html_path       text,
    url             text,
    deployed_at     timestamptz,
    language        text not null default 'en',
    bytes           int,
    unique (run_id, place_id)
);

create table if not exists contacts (
    id              bigserial primary key,
    run_id          text references runs(id) on delete cascade,
    place_id        text not null references prospects(place_id) on delete cascade,
    channel         text not null,
    target          text,
    rationale       text,
    pain_score      int,
    is_actionable   boolean,
    unique (run_id, place_id)
);

create table if not exists outreach_emails (
    id                  bigserial primary key,
    run_id              text references runs(id) on delete cascade,
    place_id            text not null references prospects(place_id) on delete cascade,
    to_email            text,
    subject             text not null,
    body                text not null,
    demo_url            text,
    language            text not null default 'en',
    from_name           text,
    from_email          text,
    physical_address    text,
    unsubscribe_url     text,
    created_at          timestamptz not null,
    sent_at             timestamptz,
    unique (run_id, place_id)
);

-- Espeja funnel.jsonl casi exactamente, para que el backfill sea una copia
-- directa. place_id_hash es la clave de unión (lo único que el JSONL siempre
-- tiene); place_id es nullable porque los registros backfillados desde el JSONL
-- nunca tuvieron el valor real, solo el hash.
create table if not exists funnel_events (
    id              bigserial primary key,
    place_id_hash   text not null,
    place_id        text,
    run_id          text references runs(id) on delete set null,
    event           text not null,
    level           int not null,
    at              timestamptz not null,
    vertical        text,
    metro           text,
    channel         text,
    language        text,
    pain_score      int,
    amount_usd      numeric(10,2) not null default 0,
    note            text,
    unique (place_id_hash, event, at)
);

create table if not exists suppressions (
    key         text primary key,
    kind        text not null,
    reason      text not null,
    at          timestamptz not null,
    note        text
);

-- Sin esto, FunnelReport.spend_usd es un número que se tipea a mano en
-- `ledger report --spend`, y cost_per_call nunca fue un dato real.
--
-- client_id: estas tres tablas (costs, time_log, demo_views) son logs de
-- eventos puros -- no hay una combinación de columnas de negocio que sea
-- naturalmente única para des-duplicar un reintento del outbox (a diferencia de
-- scores/demos/contacts, que tienen (run_id, place_id)). client_id lo genera
-- Python al armar la fila, antes de intentar escribir; así "on conflict
-- (client_id) do nothing" hace que reintentar el mismo envelope del outbox dos
-- veces no duplique la fila.
create table if not exists costs (
    id          bigserial primary key,
    client_id   uuid not null unique,
    at          timestamptz not null,
    category    text not null,
    vendor      text,
    amount_usd  numeric(10,2) not null,
    run_id      text references runs(id) on delete set null,
    note        text
);

-- Sin esto, horas_mes_por_cliente (el desempate por mantenibilidad de
-- decision_criteria.yaml) nunca tuvo un dato real, y "¿esto da un ingreso extra
-- por hora?" es literalmente incalculable.
create table if not exists time_log (
    id          bigserial primary key,
    client_id   uuid not null unique,
    at          timestamptz not null,
    minutes     int not null,
    activity    text not null,
    run_id      text references runs(id) on delete set null,
    place_id    text,
    note        text
);

-- Token por (demo, canal): el link que efectivamente se manda no es la URL de la
-- demo, es una redirección a través de esto — ver gtm/store/... y la Cloudflare
-- Pages Function. Así se sabe qué mensaje concreto generó qué apertura.
create table if not exists demo_links (
    token       text primary key,
    demo_slug   text not null,
    place_id    text not null,
    channel     text not null,
    run_id      text references runs(id) on delete set null,
    created_at  timestamptz not null
);

-- Nivel 1 de la escalera de compromiso (decision_criteria.yaml). Deliberadamente
-- en su propia tabla, NUNCA en funnel_events: un click mide curiosidad, no
-- disposición a pagar, y decision_criteria.yaml existe justamente para que nada
-- decida con esa señal.
-- client_id: la Cloudflare Pages Function que inserta acá lo genera del lado
-- del cliente por el mismo motivo que costs/time_log (ver el comentario ahí):
-- una recarga de red que reintenta la misma request no debe duplicar la vista.
create table if not exists demo_views (
    id              bigserial primary key,
    client_id       uuid not null unique,
    token           text references demo_links(token) on delete set null,
    demo_slug       text not null,
    place_id        text,
    at              timestamptz not null,
    ip_hash         text,
    user_agent      text,
    referer         text,
    is_probable_bot boolean not null default false
);

create index if not exists idx_scores_run on scores(run_id);
create index if not exists idx_demos_run on demos(run_id);
create index if not exists idx_contacts_run on contacts(run_id);
create index if not exists idx_outreach_emails_run on outreach_emails(run_id);
create index if not exists idx_funnel_events_place_hash on funnel_events(place_id_hash);
create index if not exists idx_funnel_events_run on funnel_events(run_id);
create index if not exists idx_demo_links_slug on demo_links(demo_slug);
create index if not exists idx_demo_views_slug on demo_views(demo_slug);
create index if not exists idx_demo_views_token on demo_views(token);
create index if not exists idx_costs_run on costs(run_id);
create index if not exists idx_time_log_run on time_log(run_id);
