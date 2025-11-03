# src/agentic_multimodal/skills/web_fetcher.py
import asyncio, httpx, json, hashlib
from typing import Optional

class WebFetcher:
    def __init__(self, base_url: str, rate_limit_per_sec: int = 5, cache=None):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)
        self._sem = asyncio.Semaphore(rate_limit_per_sec)
        self.cache = cache

    async def get(self, params: dict, headers: Optional[dict] = None) -> dict:
        key = None
        if self.cache is not None:
            key = self.cache.key(self.base_url, json.dumps(params, sort_keys=True))
            cached = (self.cache.path_for(key, ".json"))
            if cached.exists():
                return json.loads(cached.read_text(encoding="utf-8"))
        async with self._sem:
            r = await self._client.get(self.base_url, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
        if self.cache is not None and key:
            self.cache.put_json(key, data)
        return data

