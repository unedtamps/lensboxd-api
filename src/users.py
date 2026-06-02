import asyncio
from typing import Optional

from bs4 import BeautifulSoup

from src.film import get_film_by_id
from src.utils import fetch_html
from src.cache import cache, cache_slow

FAVORITES_FANOUT = 3
DIARY_CACHE_PREFIX = "diary"


def convert_stars_to_number(star_str: Optional[str]) -> Optional[float]:
    if not star_str:
        return None
    return star_str.count("★") + star_str.count("½") * 0.5


def clean_film_url(raw_href: Optional[str]) -> Optional[str]:
    if not raw_href or "/film/" not in raw_href:
        return None
    return raw_href[raw_href.find("/film/"):]


def parse_diary(html: str):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select(".griditem")

    for row in rows:
        component = row.select_one(".react-component")
        viewing_data = row.select_one(".poster-viewingdata")
        if not component or not viewing_data:
            continue

        film_a = component.get("data-item-link")
        rating_el = viewing_data.select_one(".rating")
        like_icon = bool(viewing_data.select_one(".icon-liked"))

        yield {
            "film_href": film_a,
            "rating": rating_el.get_text(strip=True) if rating_el else None,
            "liked": like_icon,
        }


async def scrape_user(user_id: str, page: int):
    cache_key = f"{DIARY_CACHE_PREFIX}:{user_id}:{page}"
    cached = cache.get(cache_key)
    if cached is not None:
        return ("ok", cached)

    datas = []
    diary_url = f"https://letterboxd.com{user_id}films/page/{page}/"

    status, html = await fetch_html(diary_url)
    if status != "ok" or not html:
        return (status, [])

    for entry in parse_diary(html):
        film_id = clean_film_url(entry["film_href"])
        if not film_id:
            continue

        data = {
            "user_id": user_id,
            "film_id": film_id,
            "rating": convert_stars_to_number(entry["rating"]),
            "liked": entry["liked"],
        }
        datas.append(data)

    cache.set(cache_key, datas)
    return ("ok", datas)


async def get_user_diary_page(user_id: str, page: int):
    formatted_uid = f"/{user_id}/"
    return await scrape_user(formatted_uid, page)


def parse_favorites(html: str):
    soup = BeautifulSoup(html, "html.parser")
    favorites = soup.select("#favourites .favourite-production-poster-container > div")

    for film in favorites:
        film_id = film.get("data-item-link")
        if film_id:
            yield film_id


async def get_user_favorites_handler(user_id: str):
    formatted_uid = f"/{user_id}/"
    cache_key = f"favorites:{formatted_uid}"

    cached = cache_slow.get(cache_key)
    if cached is not None:
        return ("ok", cached)

    status, html = await fetch_html(f"https://letterboxd.com{formatted_uid}")
    if status != "ok" or not html:
        return (status, [])

    film_ids = list(parse_favorites(html))

    semaphore = asyncio.Semaphore(FAVORITES_FANOUT)

    async def fetch_with_cap(film_id):
        async with semaphore:
            return await get_film_by_id(film_id)

    tasks = [fetch_with_cap(film_id) for film_id in film_ids]
    results = await asyncio.gather(*tasks)

    datas = [
        data for s, data in results
        if s == "ok" and data is not None
    ]

    cache_slow.set(cache_key, datas)
    return ("ok", datas)
