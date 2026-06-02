import json
import re

from bs4 import BeautifulSoup

from src.utils import fetch_html


def extract_text(element):
    return element.get_text(strip=True) if element else None


def parse_film_data(html, film_id):
    soup = BeautifulSoup(html, "html.parser")
    data = {
        "id": film_id,
        "name": None,
        "year": None,
        "director": None,
        "tagline": None,
        "synopsis": None,
        "poster": None,
        "casts": None,
        "genres": None,
        "themes": None,
        "duration": None,
        "rating": None,
    }

    details_head = soup.select_one(".details")
    if details_head:
        data["name"] = extract_text(details_head.select_one("h1"))

    data["year"] = extract_text(soup.select_one(".releasedate"))
    data["director"] = extract_text(soup.select_one(".contributor"))
    data["tagline"] = extract_text(soup.select_one(".tagline"))
    data["synopsis"] = extract_text(soup.select_one(".truncate"))

    cast_links = soup.select(".cast-list .text-slug")
    if cast_links:
        casts = [c.get_text(strip=True) for c in cast_links]
        data["casts"] = ", ".join(casts)

    genre_lists = soup.select("#tab-genres .text-sluglist")

    if len(genre_lists) > 0:
        g_links = genre_lists[0].select("a")
        data["genres"] = ", ".join([l.get_text(strip=True) for l in g_links])

    if len(genre_lists) > 1:
        t_links = genre_lists[1].select("a")
        data["themes"] = ", ".join([l.get_text(strip=True) for l in t_links])

    if not data["poster"]:
        try:
            script_tag = soup.find("script", type="application/ld+json")
            if script_tag:
                json_content = script_tag.string.replace("/* <![CDATA[ */", "").replace(
                    "/* ]]> */", ""
                )
                ld_data = json.loads(json_content)
                if "image" in ld_data:
                    data["poster"] = ld_data["image"]
                if (
                    "aggregateRating" in ld_data
                    and "ratingValue" in ld_data["aggregateRating"]
                ):
                    data["rating"] = str(ld_data["aggregateRating"]["ratingValue"])
        except Exception:
            pass

    try:
        dur_el = soup.select_one(".text-footer")
        if dur_el:
            dur_text = dur_el.get_text(strip=True)
            match = re.search(r"(\d+)\s+mins", dur_text)
            if match:
                data["duration"] = match.group(1)
            else:
                for p in dur_text.split():
                    if p.isdigit():
                        data["duration"] = p
                        break
    except Exception:
        pass

    return data


async def get_film_by_id(film_id):
    url = f"https://letterboxd.com{film_id}"
    status, html = await fetch_html(url)
    if status != "ok" or not html:
        return (status, None)
    return ("ok", parse_film_data(html, film_id))
