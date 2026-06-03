import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

_pool: AsyncConnectionPool | None = None

Schema_PATH = Path(__file__).parent / "schema.sql"


def _dsn() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "lensboxd")
    user = os.environ.get("POSTGRES_USER", "lensboxd")
    password = os.environ.get("POSTGRES_PASSWORD", "lensboxd")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


async def init_db() -> None:
    global _pool
    _pool = AsyncConnectionPool(_dsn(), min_size=2, max_size=5)
    async with _pool.connection() as conn:
        schema = Schema_PATH.read_text()
        await conn.execute(schema)
        await conn.commit()


async def close_db() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _pool_get() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _pool


async def upsert_film(data: dict) -> None:
    pool = _pool_get()
    async with pool.connection() as conn:
        await conn.execute(
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
        await conn.commit()


async def get_film(film_id: str) -> dict | None:
    pool = _pool_get()
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT * FROM films WHERE id = %s", (film_id,))
            return await cur.fetchone()


async def upsert_diary_entry(
    user_id: str, film_id: str, rating: float | None, liked: bool
) -> None:
    pool = _pool_get()
    async with pool.connection() as conn:
        await conn.execute(
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
        await conn.commit()


async def upsert_diary_entries(entries: list[dict]) -> None:
    pool = _pool_get()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(
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
        await conn.commit()


async def user_has_diary(user_id: str) -> bool:
    pool = _pool_get()
    async with pool.connection() as conn:
        row = await conn.execute(
            "SELECT 1 FROM diary_entries WHERE user_id = %s LIMIT 1",
            (user_id,),
        )
        return await row.fetchone() is not None


async def diary_entry_exists(user_id: str, film_id: str) -> bool:
    pool = _pool_get()
    async with pool.connection() as conn:
        row = await conn.execute(
            "SELECT 1 FROM diary_entries WHERE user_id = %s AND film_id = %s",
            (user_id, film_id),
        )
        return await row.fetchone() is not None


async def get_user_diary_all(user_id: str) -> list[dict]:
    pool = _pool_get()
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT user_id, film_id, rating, liked FROM diary_entries WHERE user_id = %s",
                (user_id,),
            )
            return await cur.fetchall()
