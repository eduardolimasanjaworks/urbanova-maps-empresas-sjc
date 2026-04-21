from __future__ import annotations

import re
from typing import Iterable, List
from urllib.parse import ParseResult, urlparse, urlunparse


WHATSAPP_RE = re.compile(r"https?://chat\.whatsapp\.com/[A-Za-z0-9]{8,80}(?:[^\s\"'<>)\]]*)?")


def extract_whatsapp_links(text: str) -> List[str]:
    if not text:
        return []
    return list(dict.fromkeys(WHATSAPP_RE.findall(text)))


def normalize_whatsapp_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    if "chat.whatsapp.com" not in parsed.netloc.lower():
        return ""

    normalized_path = parsed.path.rstrip(").,;:'\"!?")
    rebuilt = ParseResult(
        scheme="https",
        netloc="chat.whatsapp.com",
        path=normalized_path,
        params="",
        query="",
        fragment="",
    )
    return urlunparse(rebuilt)


def unique_normalized(urls: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in urls:
        normalized = normalize_whatsapp_url(raw)
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out

