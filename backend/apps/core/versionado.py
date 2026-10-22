"""Secuencia global de versiones de catálogo para la sincronización.

En PostgreSQL usa la secuencia ``catalogo_version_seq`` (creada en la
migración 0002 de core). En otros motores (pruebas locales) usa el reloj.
"""
import time

from django.db import connection


def siguiente_version() -> int:
    if connection.vendor == "postgresql":
        with connection.cursor() as cur:
            cur.execute("SELECT nextval('catalogo_version_seq')")
            return cur.fetchone()[0]
    return time.time_ns() // 1000