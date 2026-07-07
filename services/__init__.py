"""Blokcheyn API xizmatlari — Professional grade."""

import httpx
import asyncio
import logging
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)

# Umumiy HTTP client sozlamalari
DEFAULT_TIMEOUT: float = 30.0
MAX_RETRIES: int = 5
RETRY_DELAY: float = 2.0


async def safe_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    retries: int = MAX_RETRIES,
    **kwargs: Any,
) -> httpx.Response:
    """Xavfsiz HTTP so'rov — retry logic bilan.

    Args:
        client: HTTPX async client.
        method: HTTP metod (GET, POST).
        url: So'rov URL.
        retries: Qayta urinishlar soni.
        **kwargs: Qo'shimcha parametrlar.

    Returns:
        httpx.Response obyekti.

    Raises:
        httpx.HTTPError: Barcha urinishlar muvaffaqiyatsiz bo'lganda.
    """
    last_error: Exception | None = None

    for attempt in range(retries):
        try:
            response: httpx.Response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            last_error = e
            if e.response.status_code == 429 and attempt < retries - 1:
                wait = RETRY_DELAY * (attempt + 1)
                logger.warning(f"Rate limit (429) for {url}. Waiting {wait}s...")
                await asyncio.sleep(wait)
            else:
                logger.error(f"HTTP error {e.response.status_code} for {url}. Raising immediately.")
                raise e
        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            last_error = e
            if attempt < retries - 1:
                wait = RETRY_DELAY * (attempt + 1)
                logger.warning(f"Network error {e} for {url}. Waiting {wait}s...")
                await asyncio.sleep(wait)
            else:
                logger.error(f"All {retries} retries failed for {url}: {e}")

    raise last_error  # type: ignore
