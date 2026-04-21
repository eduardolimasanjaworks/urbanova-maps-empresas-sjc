from __future__ import annotations

import asyncio
import random
from collections import defaultdict, deque
from dataclasses import dataclass
from time import perf_counter
from typing import Deque, Dict, List, Tuple
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .extractor import extract_whatsapp_links, unique_normalized
from .search import SearchResult, search_query
from .storage import ResultStore


USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]


@dataclass
class CrawlConfig:
    engines: List[str]
    dorks: List[str]
    per_query: int
    target: int
    depth: int
    delay_min: float
    delay_max: float
    concurrency: int
    max_dorks: int
    searx_url: str | None


def _pick_headers() -> dict:
    return {"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}


def _extract_page_links(html: str, base_domain: str | None = None) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    discovered: List[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href.startswith(("http://", "https://")):
            continue
        if base_domain and urlparse(href).netloc != base_domain:
            continue
        discovered.append(href)
    return list(dict.fromkeys(discovered))


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url, timeout=25.0, follow_redirects=True, headers=_pick_headers())
    response.raise_for_status()
    if "text/html" not in response.headers.get("content-type", ""):
        return ""
    return response.text


async def run_crawler(cfg: CrawlConfig, store: ResultStore) -> Dict[str, object]:
    started = perf_counter()
    per_engine_counter = defaultdict(int)
    per_keyword_counter = defaultdict(int)
    total_candidates = 0
    errors = 0

    limits = httpx.Limits(max_connections=max(20, cfg.concurrency * 4), max_keepalive_connections=20)
    async with httpx.AsyncClient(limits=limits) as client:
        queue: Deque[Tuple[str, int, str, str]] = deque()  # (url, depth, engine, query)
        semaphore = asyncio.Semaphore(cfg.concurrency)
        dorks_consideradas = 0

        async def worker(url: str, depth: int, engine: str, query: str) -> None:
            nonlocal total_candidates, errors
            if url in store.visited_pages:
                return
            store.mark_page_visited(url)
            try:
                async with semaphore:
                    html = await _fetch_text(client, url)
                    await asyncio.sleep(random.uniform(cfg.delay_min, cfg.delay_max))
            except Exception:
                errors += 1
                return
            if not html:
                return

            candidates = unique_normalized(extract_whatsapp_links(html))
            if candidates:
                added = store.add_links(candidates, source_url=url, engine=engine, query=query)
                total_candidates += len(candidates)
                per_engine_counter[engine] += added
                per_keyword_counter[query] += added

            if depth < cfg.depth:
                base_domain = urlparse(url).netloc
                for sub_link in _extract_page_links(html, base_domain=base_domain):
                    if sub_link not in store.visited_pages:
                        queue.append((sub_link, depth + 1, engine, query))

        batch_size = max(10, cfg.concurrency * 2)

        async def drain_queue() -> None:
            while queue and len(store.unique_links) < cfg.target:
                batch: List[Tuple[str, int, str, str]] = []
                while queue and len(batch) < batch_size:
                    batch.append(queue.popleft())
                await asyncio.gather(*(worker(url, depth, engine, query) for url, depth, engine, query in batch))
                store.save_checkpoint()
                print(
                    f"[progresso] unicos={len(store.unique_links)} visitadas={len(store.visited_pages)} "
                    f"fila={len(queue)} erros={errors}",
                    flush=True,
                )

        for engine in cfg.engines:
            if len(store.unique_links) >= cfg.target:
                break
            for query in cfg.dorks:
                if len(store.unique_links) >= cfg.target:
                    break
                if dorks_consideradas >= cfg.max_dorks:
                    break
                if store.is_query_done(engine, query):
                    continue
                dorks_consideradas += 1
                try:
                    results: List[SearchResult] = await search_query(
                        client=client,
                        engine=engine,
                        query=query,
                        max_results=cfg.per_query,
                        searx_url=cfg.searx_url,
                    )
                except Exception:
                    errors += 1
                    continue
                for result in results:
                    queue.append((result.result_url, 0, result.engine, result.query))
                store.mark_query_done(engine, query)
                await drain_queue()
                await asyncio.sleep(random.uniform(cfg.delay_min, cfg.delay_max))

            if dorks_consideradas >= cfg.max_dorks:
                break

        # Se sobrou fila, drena no final.
        await drain_queue()

    elapsed = round(perf_counter() - started, 2)
    return {
        "total_unico": len(store.unique_links),
        "total_candidatos_extraidos": total_candidates,
        "duplicados_removidos": max(0, total_candidates - len(store.unique_links)),
        "visitadas": len(store.visited_pages),
        "erros": errors,
        "por_engine": dict(per_engine_counter),
        "por_keyword": dict(sorted(per_keyword_counter.items(), key=lambda kv: kv[1], reverse=True)[:30]),
        "dorks_consideradas": dorks_consideradas,
        "tempo_execucao_segundos": elapsed,
        "target": cfg.target,
    }

