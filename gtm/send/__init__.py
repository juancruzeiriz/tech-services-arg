"""Envío con estado: outbox, SMTP, rebotes.

Cablea sobre `gtm/store/` (Postgres es requisito acá, a diferencia del resto
del pipeline) para llevar cada mensaje por una máquina de estados real, en vez
de que "mandar" sea un `print()` de un texto que el operador copia a mano.
"""
