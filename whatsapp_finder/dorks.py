from __future__ import annotations

from typing import Iterable, List


BASE_PATTERNS = [
    "site:chat.whatsapp.com {kw}",
    '"chat.whatsapp.com" {kw}',
    '"chat.whatsapp.com" "{kw}"',
    '"join chat.whatsapp.com" {kw}',
    '"grupo whatsapp" {kw} "chat.whatsapp.com"',
    '"whatsapp group links" {kw} "chat.whatsapp.com"',
    'intitle:"whatsapp group" {kw} "chat.whatsapp.com"',
    "site:blogspot.com \"chat.whatsapp.com\" {kw}",
    "site:wordpress.com \"chat.whatsapp.com\" {kw}",
    "site:medium.com \"chat.whatsapp.com\" {kw}",
]

LANG_TERMS = {
    "pt": ["grupo", "empreendedorismo", "loja virtual", "networking"],
    "en": ["group", "ecommerce", "online store", "networking"],
    "es": ["grupo", "comercio electronico", "tienda online", "networking"],
}


def generate_dorks(keywords: Iterable[str], langs: Iterable[str]) -> List[str]:
    cleaned_keywords = [k.strip() for k in keywords if k.strip()]
    selected_langs = [l.strip().lower() for l in langs if l.strip()]
    lang_expansions = []
    for lang in selected_langs:
        lang_expansions.extend(LANG_TERMS.get(lang, []))

    all_terms = list(dict.fromkeys(cleaned_keywords + lang_expansions))
    if not all_terms:
        return []

    dorks: List[str] = []
    for term in all_terms:
        for pattern in BASE_PATTERNS:
            dorks.append(pattern.format(kw=term))
    return list(dict.fromkeys(dorks))

