-- La cola de envío, con su máquina de estados. Vive en Postgres y no en el
-- ledger JSONL a propósito: acá hacen falta UPDATE, reintentos con
-- SELECT ... FOR UPDATE SKIP LOCKED y un next_attempt_at que se consulta por
-- rango. Un archivo append-only de solo-hashes no puede hacer nada de eso.
--
-- Consecuencia asumida: el envío requiere SUPABASE_DB_URL. Sin Postgres, la UI
-- sigue funcionando exactamente como hoy (cola manual, copiar y pegar) y la
-- pantalla de envío muestra por qué está deshabilitada.
create table if not exists outreach_messages (
    id                  bigserial primary key,
    client_id           uuid not null unique,
    run_id              text references runs(id) on delete set null,
    place_id            text not null references prospects(place_id) on delete cascade,
    channel             text not null,        -- email | contact_form | phone
    to_address          text,                 -- email, URL del formulario o teléfono
    subject             text,
    body                text not null,
    link_token          text references demo_links(token) on delete set null,

    status              text not null default 'draft',
    -- draft -> queued -> sending -> sent -> delivered
    --                            \-> bounced / failed -> (reintento) -> queued
    -- manual_pending -> manual_done   (formulario y teléfono)
    -- cancelled  (suprimido antes de salir)

    attempt_count       int not null default 0,
    max_attempts        int not null default 3,
    next_attempt_at     timestamptz,
    provider_message_id text,                 -- Message-ID del RFC 5322
    verp_tag            text unique,          -- para machear el rebote con esta fila

    created_at          timestamptz not null default now(),
    queued_at           timestamptz,
    sent_at             timestamptz,
    delivered_at        timestamptz,          -- confirmado por apertura del link con token
    failed_at           timestamptz,
    failure_kind        text,                 -- hard_bounce | soft_bounce | smtp_error | compliance
    failure_reason      text,
    last_error          text,

    unique (run_id, place_id, channel)
);

create index if not exists idx_msgs_status on outreach_messages(status);
create index if not exists idx_msgs_due on outreach_messages(status, next_attempt_at)
    where status in ('queued', 'sending');
create index if not exists idx_msgs_place on outreach_messages(place_id);
create index if not exists idx_msgs_verp on outreach_messages(verp_tag);

-- Log de cada intento. La tabla de arriba guarda el estado actual; ésta guarda
-- la historia, que es lo que responde "¿por qué falló?" sin tener que adivinar.
create table if not exists outreach_attempts (
    id              bigserial primary key,
    client_id       uuid not null unique,
    message_id      bigint not null references outreach_messages(id) on delete cascade,
    attempt_no      int not null,
    at              timestamptz not null,
    outcome         text not null,   -- accepted | smtp_error | hard_bounce | soft_bounce | opened
    detail          text,
    smtp_code       int
);

create index if not exists idx_attempts_message on outreach_attempts(message_id);
