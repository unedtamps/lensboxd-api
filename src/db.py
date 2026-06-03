import os
import asyncio
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None

Schema_PATH = Path(__file__).parent / "schema.sql"


def _dsn() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "lensboxd")
    user = os.environ.get("POSTGRES_USER", "lensboxd")
    password = os.environ.get("POSTGRES_PASSWORD", "lensboxd")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


async def init_db() -> None:
    def _init():
        global _pool
        _pool = ConnectionPool(_dsn(), min_size=2, max_size=5)
        with _pool.connection() as conn:
            schema = Schema_PATH.read_text()
            conn.execute(schema)
            conn.commit()
    await asyncio.to_thread(_init)


async def close_db() -> None:
    global _pool
    if _pool:
        pool = _pool
        _pool = None
        await asyncio.to_thread(pool.close)


def _pool_get() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _pool


async def upsert_film(data: dict) -> None:
    def _upsert():
        pool = _pool_get()
        with pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO films (id, name, year, director, tagline, synopsis,
                                  poster, casts, genres, themes, duration, rating)
                VALUES (%(id)s, %(name)s, %(year)s, %(director)s, %(tagline)s, %(synopsis)s,
                        %(poster)s, %(casts)s, %(genres)s, %(themes)s, %(duration)s, %(rating)s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    year = EXCLUDED.year,
                    director = EXCLUDED.director,
                    tagline = EXCLUDED.tagline,
                    synopsis = EXCLUDED.synopsis,
                    poster = EXCLUDED.poster,
                    casts = EXCLUDED.casts,
                    genres = EXCLUDED.genres,
                    themes = EXCLUDED.themes,
                    duration = EXCLUDED.duration,
                    rating = EXCLUDED.rating,
                    updated_at = NOW()
                """,
                data,
            )
            conn.commit()
    await asyncio.to_thread(_upsert)


async def get_film(film_id: str) -> dict | None:
    def _get():
        pool = _pool_get()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM films WHERE id = %s", (film_id,))
                return cur.fetchone()
    return await asyncio.to_thread(_get)


async def upsert_diary_entry(
    user_id: str, film_id: str, rating: float | None, liked: bool
) -> None:
    def _upsert():
        pool = _pool_get()
        with pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO diary_entries (user_id, film_id, rating, liked)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, film_id) DO UPDATE SET
                    rating = EXCLUDED.rating,
                    liked = EXCLUDED.liked,
                    updated_at = NOW()
                """,
                (user_id, film_id, rating, liked),
            )
            conn.commit()
    await asyncio.to_thread(_upsert)


async def upsert_diary_entries(entries: list[dict]) -> None:
    def _upsert():
        pool = _pool_get()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO diary_entries (user_id, film_id, rating, liked)
                    VALUES (%(user_id)s, %(film_id)s, %(rating)s, %(liked)s)
                    ON CONFLICT (user_id, film_id) DO UPDATE SET
                        rating = EXCLUDED.rating,
                        liked = EXCLUDED.liked,
                        updated_at = NOW()
                    """,
                    entries,
                )
            conn.commit()
    await asyncio.to_thread(_upsert)


async def user_has_diary(user_id: str) -> bool:
    def _has():
        pool = _pool_get()
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM diary_entries WHERE user_id = %s LIMIT 1",
                (user_id,),
            )
            return row.fetchone() is not None
    return await asyncio.to_thread(_has)


async def diary_entry_exists(user_id: str, film_id: str) -> bool:
    def _exists():
        pool = _pool_get()
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM diary_entries WHERE user_id = %s AND film_id = %s",
                (user_id, film_id),
            )
            return row.fetchone() is not None
    return await asyncio.to_thread(_exists)


async def get_user_diary_all(user_id: str) -> list[dict]:
    def _get_all():
        pool = _pool_get()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT user_id, film_id, rating, liked FROM diary_entries WHERE user_id = %s",
                    (user_id,),
                )
                return cur.fetchall()
    return await asyncio.to_thread(_get_all)
