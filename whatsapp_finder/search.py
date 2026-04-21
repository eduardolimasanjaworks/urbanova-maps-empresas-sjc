from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import List
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class SearchResult:
    engine: str
    query: str
    result_url: str


def _valid_http_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_engine_internal(url: str, engine: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if engine == "bing" and host.endswith("bing.com") and path.startswith("/ck/a"):
        return False
    if engine == "duckduckgo" and host.endswith("duckduckgo.com") and path.startswith("/l/"):
        return False
    block_hosts = {
        "bing": ["bing.com", "microsoft.com"],
        "duckduckgo": ["duckduckgo.com"],
        "brave": ["brave.com", "search.brave.com"],
    }
    return any(bh in host for bh in block_hosts.get(engine, []))


def _unwrap_redirect(url: str, engine: str) -> str:
    parsed = urlparse(url)
    if engine == "bing" and parsed.netloc.lower().endswith("bing.com") and parsed.path.lower().startswith("/ck/a"):
        encoded = parse_qs(parsed.query).get("u", [""])[0]
        if encoded.startswith("a1"):
            encoded = encoded[2:]
        if encoded:
            padded = encoded + "=" * ((4 - len(encoded) % 4) % 4)
            try:
                decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="ignore")
                if decoded.startswith(("http://", "https://")):
                    return decoded
            except Exception:
                return ""
        # Se não decodificou em URL absoluta, descartamos para evitar links internos irrelevantes.
        return ""
    if engine == "duckduckgo" and parsed.netloc.lower().endswith("duckduckgo.com"):
        uddg = parse_qs(parsed.query).get("uddg", [])
        if uddg:
            return unquote(uddg[0])
    return url


def _extract_result_links(html: str, engine: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    if engine == "bing":
        anchors = soup.select("li.b_algo h2 a[href]")
    elif engine == "duckduckgo":
        anchors = soup.select("a.result__a[href]")
    elif engine == "brave":
        anchors = soup.select("div.snippet a[href], a[data-testid='result-title-a'][href]")
    else:
        anchors = soup.find_all("a", href=True)

    links = []
    for anchor in anchors:
        href = anchor["href"].strip()
        if not _valid_http_url(href):
            continue
        if _is_engine_internal(href, engine):
            continue
        target = _unwrap_redirect(href, engine)
        if _valid_http_url(target):
            links.append(target)
    return list(dict.fromkeys(links))


def _build_engine_url(engine: str, query: str, offset: int) -> str:
    encoded = quote_plus(query)
    if engine == "bing":
        return f"https://www.bing.com/search?q={encoded}&first={offset}"
    if engine == "duckduckgo":
        return f"https://html.duckduckgo.com/html/?q={encoded}&s={offset}"
    if engine == "brave":
        return f"https://search.brave.com/search?q={encoded}&offset={offset}"
    if engine == "searxng":
        return ""
    raise ValueError(f"Engine não suportada: {engine}")


async def search_query(
    client: httpx.AsyncClient,
    engine: str,
    query: str,
    max_results: int,
    page_size: int = 10,
    searx_url: str | None = None,
) -> List[SearchResult]:
    found: List[SearchResult] = []
    if engine == "searxng":
        if not searx_url:
            raise ValueError("Engine searxng requer uma URL base (ex.: --searx-url http://localhost:8080)")
        for page in range(1, max(2, (max_results // page_size) + 2)):
            response = await client.get(
                f"{searx_url.rstrip('/')}/search",
                params={"q": query, "format": "json", "pageno": page},
                timeout=25.0,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("results", [])
            if not rows:
                break
            for row in rows:
                target = row.get("url", "").strip()
                if _valid_http_url(target):
                    found.append(SearchResult(engine=engine, query=query, result_url=target))
            if len(found) >= max_results:
                break
        return list(dict.fromkeys(found))[:max_results]

    headers = {
        # UA curta funciona melhor para respostas HTML completas em alguns buscadores.
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }
    for offset in range(0, max_results, page_size):
        url = _build_engine_url(engine, query, offset)
        response = await client.get(url, timeout=25.0, headers=headers, follow_redirects=True)
        response.raise_for_status()
        page_links = _extract_result_links(response.text, engine=engine)
        if not page_links:
            break
        for link in page_links:
            found.append(SearchResult(engine=engine, query=query, result_url=link))
        if len(found) >= max_results:
            break
    return found[:max_results]

