from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class FetchResult:
    url: str
    final_url: str
    status_code: int
    content_type: str | None
    body: bytes
    redirect_chain: list[str]
    error: str | None = None


class Fetcher:
    def __init__(self, *, timeout: float, retries: int, user_agent: str) -> None:
        self.retries = retries
        self.client = httpx.Client(follow_redirects=True, timeout=timeout, headers={"User-Agent": user_agent})

    def fetch(self, url: str) -> FetchResult:
        last_error: str | None = None
        for _ in range(self.retries + 1):
            try:
                response = self.client.get(url)
                chain = [str(r.url) for r in response.history] + [str(response.url)]
                return FetchResult(
                    url=url,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    content_type=response.headers.get("content-type"),
                    body=response.content,
                    redirect_chain=chain,
                    error=None if response.status_code < 400 else f"http_{response.status_code}",
                )
            except httpx.HTTPError as exc:
                last_error = exc.__class__.__name__
        return FetchResult(url=url, final_url=url, status_code=0, content_type=None, body=b"", redirect_chain=[url], error=last_error or "fetch_error")

    def close(self) -> None:
        self.client.close()
