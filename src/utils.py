import asyncio
import random
from typing import Literal

from curl_cffi.requests import AsyncSession

IMPERSONATE = "chrome136"
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.0
RETRY_BACKOFF_JITTER = 0.5
RETRY_AFTER_SECONDS = 30
PER_HOST_CONCURRENCY = 2
DEFAULT_TIMEOUT = 30

FetchStatus = Literal["ok", "blocked", "not_found", "error"]
FetchResult = tuple[FetchStatus, str | None]

_HOST_SEMAPHORES: dict[str, asyncio.Semaphore] = {}
_HOST_SESSIONS: dict[str, AsyncSession] = {}
_WARMED_HOSTS: set[str] = set()


def host_of(url: str) -> str | None:
    try:
        return url.split("/", 3)[2]
    except (IndexError, ValueError):
        return None


def _semaphore_for(host: str) -> asyncio.Semaphore:
    if host not in _HOST_SEMAPHORES:
        _HOST_SEMAPHORES[host] = asyncio.Semaphore(PER_HOST_CONCURRENCY)
    return _HOST_SEMAPHORES[host]


def _session_for(host: str) -> AsyncSession:
    if host not in _HOST_SESSIONS:
        _HOST_SESSIONS[host] = AsyncSession(impersonate=IMPERSONATE)
    return _HOST_SESSIONS[host]


def _reset_host(host: str) -> None:
    _WARMED_HOSTS.discard(host)
    _HOST_SESSIONS.pop(host, None)


def _backoff(attempt: int) -> float:
    base = RETRY_BACKOFF_BASE * (2 ** attempt)
    jitter = base * RETRY_BACKOFF_JITTER * random.uniform(-1.0, 1.0)
    return max(0.5, base + jitter)


async def _warm(session: AsyncSession, host: str) -> bool:
    try:
        response = await session.get(f"https://{host}/", timeout=DEFAULT_TIMEOUT)
        if response.status_code == 200:
            _WARMED_HOSTS.add(host)
            return True
        return False
    except Exception as e:
        print(f"Warmup error for {host}: {e}")
        return False


async def fetch_html(url: str) -> FetchResult:
    host = host_of(url)
    if not host:
        return ("error", None)

    semaphore = _semaphore_for(host)

    async with semaphore:
        session = _session_for(host)

        if host not in _WARMED_HOSTS:
            await _warm(session, host)

        last_status: int | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await session.get(url, timeout=DEFAULT_TIMEOUT)
                last_status = response.status_code

                if response.status_code == 200:
                    return ("ok", response.text)

                if response.status_code == 404:
                    return ("not_found", None)

                if response.status_code == 403:
                    _reset_host(host)
                    session = _session_for(host)
                    await _warm(session, host)
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(_backoff(attempt))
                        continue
                    return ("blocked", None)

                if response.status_code in (408, 429, 500, 502, 503, 504):
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(_backoff(attempt))
                        continue
                    if response.status_code in (429, 503):
                        return ("blocked", None)
                    return ("error", None)

                return ("error", None)

            except Exception as e:
                print(f"Error fetching {url}: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(_backoff(attempt))
                    continue
                return ("error", None)

        if last_status == 403:
            return ("blocked", None)
        return ("error", None)


async def shutdown() -> None:
    for session in list(_HOST_SESSIONS.values()):
        try:
            await session.close()
        except Exception:
            pass
    _HOST_SESSIONS.clear()
    _HOST_SEMAPHORES.clear()
    _WARMED_HOSTS.clear()
