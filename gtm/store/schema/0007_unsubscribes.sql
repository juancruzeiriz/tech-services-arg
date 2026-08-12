-- Mecanismo de baja de CAN-SPAM (Día 19 de docs/PLAN_DIARIO.md).
--
-- `outreach.py::SenderIdentity.unsubscribe_url` es UNA URL global, no un link
-- personalizado por prospecto -- `gtm/factory/outreach.py` no genera tokens por
-- email (a diferencia de `demo_links`/`v/[token].js`, que trackea aperturas de
-- demo). Por eso esta tabla identifica por EMAIL, no por `place_id`: la persona
-- que hace clic en el link fijo tiene que decirnos a qué dirección le llegó el
-- mensaje. Es una limitación real, no un descuido -- personalizar el link exige
-- generar y guardar un token por email enviado, que es una etapa nueva.
--
-- `site/functions/api/unsubscribe.js` inserta acá con la anon key (misma
-- barrera de RLS insert-only que `subscribers`/`demo_views`, ver
-- 0002_demo_views_rls.sql y 0005_subscribers.sql). `gtm/factory/ledger.py
-- sync-unsubscribes` -- con `SUPABASE_DB_URL`, no la anon key -- es lo único
-- que lee de acá, y vuelca cada fila nueva a `SuppressionList` (fuente de
-- verdad local, `gtm/suppression.jsonl`) vía `SuppressionReason.OPTED_OUT`.
-- `synced_at` marca qué filas ya se volcaron, para que `sync-unsubscribes` sea
-- idempotente sin necesitar borrar nada.
create table if not exists unsubscribes (
    id          uuid primary key default gen_random_uuid(),
    email       text not null,
    at          timestamptz not null default now(),
    source      text,       -- ej: 'unsubscribe_page'
    synced_at   timestamptz -- NULL hasta que `ledger sync-unsubscribes` la procesa
);

create index if not exists unsubscribes_email_idx on unsubscribes (lower(email));
create index if not exists unsubscribes_unsynced_idx on unsubscribes (synced_at) where synced_at is null;

-- La Function corre en el edge con la anon key pública -- igual que
-- `subscribers` y `demo_views`, la única barrera real es esta policy. Solo
-- puede INSERTAR: ni leer quién se dio de baja, ni marcar `synced_at` (eso lo
-- hace `sync-unsubscribes` con la conexión de servicio).
alter table unsubscribes enable row level security;

create policy unsubscribes_insert_only
    on unsubscribes
    for insert
    to anon
    with check (true);
