import asyncio
import random
import time
from typing import Literal

from curl_cffi.requests import Session

IMPERSONATE = "chrome136"
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.0
RETRY_BACKOFF_JITTER = 0.5
RETRY_AFTER_SECONDS = 30
DEFAULT_TIMEOUT = 30
REQUEST_DELAY_MIN = 1.0
REQUEST_DELAY_MAX = 3.0

CHROME_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Chromium";v="136", "Google Chrome";v="136", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Linux"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

FetchStatus = Literal["ok", "blocked", "not_found", "error"]
FetchResult = tuple[FetchStatus, str | None]


def host_of(url: str) -> str | None:
    try:
        return url.split("/", 3)[2]
    except (IndexError, ValueError):
        return None


def _backoff(attempt: int) -> float:
    base = RETRY_BACKOFF_BASE * (2 ** attempt)
    jitter = base * RETRY_BACKOFF_JITTER * random.uniform(-1.0, 1.0)
    return max(0.5, base + jitter)


def _create_session() -> Session:
    return Session(impersonate=IMPERSONATE, headers=CHROME_HEADERS)


def _log_block(url: str, status_code: int, body_snippet: str) -> None:
    challenge_markers = ["cf-chl-bypass", "cf_clearance", "Just a moment", "Checking your browser", "turnstile"]
    detected = [m for m in challenge_markers if m.lower() in body_snippet.lower()]
    if detected:
        print(f"[BLOCKED] {url} | status={status_code} | JS challenge detected: {detected}")
    else:
        print(f"[BLOCKED] {url} | status={status_code} | snippet={body_snippet[:200]}")


async def fetch_html(url: str) -> FetchResult:
    host = host_of(url)
    if not host:
        return ("error", None)

    def _sync_fetch() -> FetchResult:
        last_status: int | None = None

        for attempt in range(MAX_RETRIES + 1):
            session = _create_session()
            try:
                time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

                response = session.get(url, timeout=DEFAULT_TIMEOUT)
                last_status = response.status_code

                if response.status_code == 200:
                    return ("ok", response.text)

                if response.status_code == 404:
                    return ("not_found", None)

                if response.status_code == 403:
                    _log_block(url, 403, response.text[:500] if response.text else "")
                    if attempt < MAX_RETRIES:
                        time.sleep(_backoff(attempt))
                        continue
                    return ("blocked", None)

                if response.status_code in (408, 429, 500, 502, 503, 504):
                    _log_block(url, response.status_code, response.text[:500] if response.text else "")
                    if attempt < MAX_RETRIES:
                        time.sleep(_backoff(attempt))
                        continue
                    if response.status_code in (429, 503):
                        return ("blocked", None)
                    return ("error", None)

                print(f"[UNEXPECTED] {url} | status={response.status_code}")
                return ("error", None)

            except Exception as e:
                print(f"[ERROR] fetching {url}: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(_backoff(attempt))
                    continue
                return ("error", None)
            finally:
                try:
                    session.close()
                except Exception:
                    pass

        if last_status == 403:
            return ("blocked", None)
        return ("error", None)

    return await asyncio.to_thread(_sync_fetch)


async def shutdown() -> None:
    pass
