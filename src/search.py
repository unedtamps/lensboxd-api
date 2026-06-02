import asyncio
import re

from bs4 import BeautifulSoup

from src.film import get_film_by_id
from src.utils import fetch_html
from src.cache import cache_slow


def extract_text(element):
    return element.get_text(strip=True) if element else None


def upscale_poster(url):
    pattern = r"-0-(\d+)-0-(\d+)-crop"
    new_pattern = "-0-230-0-345-crop"
    new_url = re.sub(pattern, new_pattern, url)
    return new_url


async def fetch_film_details(film_id):
    key = f"film:{film_id}"
    cached = cache_slow.get(key)
    if cached:
        return (film_id, "ok", cached)

    film_status, film_details = await get_film_by_id(film_id)
    if film_status == "ok" and film_details:
        cache_slow.set(key, film_details)
    return (film_id, film_status, film_details)


async def parse_search(html):
    soup = BeautifulSoup(html, "html.parser")
    datas = []
    results = soup.select(".search-result")

    film_tasks = []
    film_info_map = {}

    for result in results:
        title_elem = result.select_one("article > div")
        if not title_elem:
            continue

        title = title_elem.get("data-item-name")
        film_id = title_elem.get("data-item-link")

        film_info_map[film_id] = {"title": title}
        film_tasks.append(fetch_film_details(film_id))

    film_results = await asyncio.gather(*film_tasks, return_exceptions=True)

    for item in film_results:
        if isinstance(item, Exception):
            continue
        film_id, status, film_details = item
        if status != "ok" or film_details is None:
            continue

        info = film_info_map.get(film_id, {})
        datas.append({
            "title": info.get("title"),
            "film_id": film_id,
            "poster": film_details.get("poster"),
        })

    return datas


async def get_film_by_name(query):
    parse_query = query.replace(" ", "+")
    url = f"https://letterboxd.com/s/search/films/{parse_query}/"
    status, html = await fetch_html(url)
    if status != "ok" or not html:
        return (status, None)

    return ("ok", await parse_search(html))
