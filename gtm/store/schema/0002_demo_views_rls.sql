-- Row Level Security para las dos tablas que toca la Cloudflare Pages Function
-- (cloudflare/functions/v/[token].js) con la anon key pública -- esa key corre
-- en el edge, visible para cualquiera que inspeccione el bundle, así que la
-- única barrera real es qué le permite hacer la policy de Postgres, no que la
-- key esté "escondida".
--
-- demo_views: la Function solo necesita poder INSERTAR una vista. Ni SELECT,
-- ni UPDATE, ni DELETE -- un token filtrado no debe poder leer ni alterar
-- vistas ajenas.
alter table demo_views enable row level security;

create policy demo_views_insert_only
    on demo_views
    for insert
    to anon
    with check (true);

-- demo_links: la Function necesita LEER (resolver token -> demo_slug para
-- redirigir), pero nunca escribir ni borrar desde el edge -- los tokens los
-- mina el backend (gtm/store/links.py) con la service_role key, no la anon key.
alter table demo_links enable row level security;

create policy demo_links_select_only
    on demo_links
    for select
    to anon
    using (true);
