import asyncio
from typing import Optional

from bs4 import BeautifulSoup

from src.film import get_film_by_id
from src.utils import fetch_html
from src.cache import cache
from src.db import upsert_diary_entries, user_has_diary, diary_entry_exists, get_user_diary_all

FAVORITES_FANOUT = 3


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
    """Scrape diary page for user. user_id is raw (e.g. 'megbitchell')."""
    cache_key = f"diary:{user_id}:{page}"
    cached = cache.get(cache_key)
    if cached is not None:
        return ("ok", cached)

    datas = []
    diary_url = f"https://letterboxd.com/{user_id}/films/page/{page}/"

    status, html = await fetch_html(diary_url)
    if status != "ok" or not html:
        return (status, [])

    db_entries = []
    for entry in parse_diary(html):
        film_id = clean_film_url(entry["film_href"])
        if not film_id:
            continue

        rating = convert_stars_to_number(entry["rating"])
        liked = entry["liked"]

        data = {
            "user_id": user_id,
            "film_id": film_id,
            "rating": rating,
            "liked": liked,
        }
        datas.append(data)
        db_entries.append({
            "user_id": user_id,
            "film_id": film_id,
            "rating": rating,
            "liked": liked,
        })

    if db_entries:
        try:
            await upsert_diary_entries(db_entries)
        except Exception as e:
            print(f"[DB] Failed to upsert diary entries for {user_id}: {e}")

    cache.set(cache_key, datas)
    return ("ok", datas)


async def sync_diary(user_id: str) -> None:
    """Incremental scrape: stop when hitting an entry that already exists in DB."""
    has_entries = await user_has_diary(user_id)

    if not has_entries:
        page = 1
        while True:
            status, entries = await scrape_user(user_id, page)
            if status != "ok" or not entries:
                break
            page += 1
        return

    page = 1
    MAX_SYNC_PAGES = 5
    while page <= MAX_SYNC_PAGES:
        diary_url = f"https://letterboxd.com/{user_id}/films/page/{page}/"
        status, html = await fetch_html(diary_url)
        if status != "ok" or not html:
            break

        page_entries = []
        all_existing = True
        for entry in parse_diary(html):
            film_id = clean_film_url(entry["film_href"])
            if not film_id:
                continue

            if await diary_entry_exists(user_id, film_id):
                continue

            all_existing = False
            rating = convert_stars_to_number(entry["rating"])
            liked = entry["liked"]
            page_entries.append({
                "user_id": user_id,
                "film_id": film_id,
                "rating": rating,
                "liked": liked,
            })

        if page_entries:
            try:
                await upsert_diary_entries(page_entries)
            except Exception as e:
                print(f"[DB] Failed to upsert diary entries for {user_id}: {e}")

        if all_existing:
            break

        page += 1


async def get_user_diary_page(user_id: str, page: int):
    return await scrape_user(user_id, page)


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

    cached = cache.get(cache_key)
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

    cache.set(cache_key, datas)
    return ("ok", datas)
