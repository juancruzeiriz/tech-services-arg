-- Suscriptores capturados desde el sitio público (site/functions/api/subscribe.js).
--
-- No confundir con el store analítico del pipeline de prospección (runs,
-- prospects, outreach_messages): esta tabla vive en el mismo Postgres/Supabase
-- por conveniencia operativa, pero es un dato del PORTFOLIO (juancruzeiriz.com),
-- no de una corrida del pipeline. `segment` distingue "dueño de negocio" de
-- "busca un developer" porque cada uno recibe contenido distinto -- ver el
-- comentario en subscribe.js.
--
-- `confirmed_at` existe para un futuro double opt-in real (mandar un mail de
-- confirmación) que todavía no está implementado: hoy la Function solo
-- inserta la fila con confirmed_at NULL. El envío de campañas arranca
-- apagado a propósito (ver docs del proyecto) -- esta tabla junta interés,
-- no dispara ningún mail todavía.
create table if not exists subscribers (
    id              uuid primary key default gen_random_uuid(),
    email           text not null,
    segment         text not null,  -- 'business_owner' | 'developer'
    created_at      timestamptz not null default now(),
    confirmed_at    timestamptz,
    unsubscribed_at timestamptz,
    source          text  -- ej: 'audit_page', para saber qué página convierte
);

create unique index if not exists subscribers_email_key on subscribers (lower(email));

-- La Function corre en el edge con la anon key pública -- igual que
-- demo_views (ver 0002_demo_views_rls.sql), la única barrera real es esta
-- policy, no que la key esté "escondida". Solo puede INSERTAR: ni leer la
-- lista completa de suscriptores, ni confirmar, ni dar de baja a otro desde
-- el edge -- eso lo hace un proceso con la service_role key.
alter table subscribers enable row level security;

create policy subscribers_insert_only
    on subscribers
    for insert
    to anon
    with check (true);
