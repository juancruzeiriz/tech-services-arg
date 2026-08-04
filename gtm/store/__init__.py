"""Store analítico (Postgres/Supabase) para dashboards.

Distinto de `gtm/factory/ledger.py`, que sigue siendo la fuente de verdad local
para supresión y para el criterio de decisión (`gtm/suppression.jsonl`,
`gtm/funnel.jsonl` — commiteados a git, sólo hashes). Este módulo es el almacén
con detalle completo: nombres, teléfonos, el texto de los emails. No reemplaza al
ledger, lo complementa — ver el docstring de `gtm/store/buffer.py` para por qué
el ledger sigue siendo autoritativo para supresión incluso con Postgres andando.
"""
