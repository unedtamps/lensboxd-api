from bs4 import BeautifulSoup

from src.utils import fetch_html


def _normalize_list_path(list_path: str) -> str:
    for prefix in ("https://letterboxd.com", "http://letterboxd.com"):
        if list_path.startswith(prefix):
            list_path = list_path[len(prefix):]
            break
    list_path = list_path.rstrip("/")
    if not list_path.startswith("/"):
        list_path = f"/{list_path}"
    return list_path


def parse_list_entries(html: str):
    soup = BeautifulSoup(html, "html.parser")

    entries = soup.select("ul.js-list-entries > li.posteritem")

    if not entries:
        entries = soup.select("ul.grid > li.griditem")

    for entry in entries:
        react_component = entry.select_one("div.react-component")
        if not react_component:
            continue

        film_id = react_component.get("data-item-link")
        title = react_component.get("data-item-name")

        if film_id and title:
            yield {
                "title": title.strip(),
                "film_id": film_id,
            }


async def fetch_list_page(list_id: str, page: int):
    url = f"https://letterboxd.com{list_id}/page/{page}/"
    status, html = await fetch_html(url)
    if status != "ok" or not html:
        return (status, [])

    return ("ok", list(parse_list_entries(html)))


async def get_list(list_path: str, page: int = None, limit: int = None):
    list_id = _normalize_list_path(list_path)

    if page:
        status, page_results = await fetch_list_page(list_id, page)
        if status == "ok" and limit:
            page_results = page_results[:limit]
        return (status, page_results)

    results: list[dict] = []
    current_page = 1
    last_status = "ok"

    while True:
        if limit and len(results) >= limit:
            break

        status, entries = await fetch_list_page(list_id, current_page)
        last_status = status

        if status != "ok":
            break

        if not entries:
            break

        results.extend(entries)
        current_page += 1

    if limit:
        results = results[:limit]

    return (last_status, results)
