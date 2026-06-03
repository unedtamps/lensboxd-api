import asyncio
import os
import sys

from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cache import cache
from src.db import init_db
from src.film import get_film_by_id
from src.search import get_film_by_name

app = Flask(__name__)
cache.init_app(app)

FILM_IDS = [
    "/film/the-matrix/",
    "/film/the-matrix-1999/",
    "/film/inception/",
    "/film/interstellar/",
    "/film/the-godfather/",
    "/film/the-godfather-part-ii/",
    "/film/pulp-fiction/",
    "/film/the-dark-knight/",
    "/film/parasite-2019/",
    "/film/spirited-away/",
    "/film/la-la-land/",
    "/film/whiplash-2014/",
    "/film/the-grand-budapest-hotel/",
    "/film/mad-max-fury-road/",
    "/film/joker-2019/",
]

SEARCH_QUERIES = [
    "matrix",
    "nolan",
    "godfather",
    "tarantino",
    "kubrick",
]


async def warm_film(film_id):
    key = f"film:{film_id}"
    with app.app_context():
        if cache.get(key):
            print(f"skip {key}")
            return
        status, data = await get_film_by_id(film_id)
        if status == "ok" and data:
            cache.set(key, data)
            print(f"ok   {key}")
        else:
            print(f"miss {key} status={status}")


async def warm_search(query):
    key = f"search:{query}"
    with app.app_context():
        if cache.get(key):
            print(f"skip {key}")
            return
        status, data = await get_film_by_name(query)
        if status == "ok" and data:
            cache.set(key, data)
            print(f"ok   {key}")
        else:
            print(f"miss {key} status={status}")


async def main():
    await init_db()
    for film_id in FILM_IDS:
        await warm_film(film_id)
    for query in SEARCH_QUERIES:
        await warm_search(query)


if __name__ == "__main__":
    asyncio.run(main())
