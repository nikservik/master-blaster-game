"""Клиент сервера Kev: POST /v1/systemone, асинхронно, с ограничением одновременных запросов.

Сервер сам собирает до 64 запросов в батч, поэтому клиент держит пул одновременных запросов, а не шлёт батч.
"""
import asyncio
import time
from dataclasses import dataclass, field

import httpx

URL = "http://localhost:8009/v1/systemone"


@dataclass
class Answer:
    """Ответ на один запрос: распределения по вопросам, время модели и время с дороги."""
    probabilities: dict[str, dict[str, float]]   # вопрос choice -> вариант -> вероятность
    noul: dict[str, float]                       # вопрос noul -> p(да)
    model_ms: float
    total_ms: float


@dataclass
class KevClient:
    url: str = URL
    concurrency: int = 64
    timeout_s: float = 30.0
    _sem: asyncio.Semaphore | None = field(default=None, init=False)
    _http: httpx.AsyncClient | None = field(default=None, init=False)

    async def __aenter__(self):
        self._sem = asyncio.Semaphore(self.concurrency)
        limits = httpx.Limits(max_connections=self.concurrency, max_keepalive_connections=self.concurrency)
        self._http = httpx.AsyncClient(timeout=self.timeout_s, limits=limits)
        return self

    async def __aexit__(self, *exc):
        await self._http.aclose()

    async def ask(self, state: str | dict, questions: dict) -> Answer:
        """questions — как в API: {"имя": {"type": "choice", "criteria": {...}}, "имя2": {"type": "noul", ...}}."""
        async with self._sem:
            start = time.perf_counter()
            r = await self._http.post(self.url, json={"state": state, "questions": questions})
            total = (time.perf_counter() - start) * 1000.0
        r.raise_for_status()
        body = r.json()
        probs, noul = {}, {}
        for name, a in body["answers"].items():
            if "probabilities" in a and isinstance(a["probabilities"], dict):
                probs[name] = a["probabilities"]
            if "noul" in a:
                noul[name] = a["noul"]
        return Answer(probs, noul, float(body.get("latency_ms", 0.0)), total)
