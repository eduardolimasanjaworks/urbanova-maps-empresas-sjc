"""Filtra convites: exclui achadinhos/C2C óbvios e ranqueia networking / e-commerce B2B."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse


def _base_source(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")


def _path(url: str) -> str:
    return (urlparse(url).path or "").lower()


# Rejeição dura: qualquer página de origem com estes trechos no path
_HARD_EXCLUDE_PATH = (
    "achadin",
    "cupom",
    "cupons",
    "oferta",
    "promo",
    "desconto",
    "black-friday",
    "bug",
    "frete-gratis",
    "figurinha",
    "figurinhas",
    "doacao",
    "doação",
    "oracao",
    "oração",
    "evangel",
    "biblia",
    "feira-do-rolo",
    "memes",
    "humor",
    "games",
    "jogos",
    "divulgacao",
    "divulgação",
)

# Penalidades leves (varejo / consumidor), não excluem sozinhas
_SOFT_NEGATIVE_PATH = (
    ("shopee", 1.5),
    ("mercado-livre", 1.5),
    ("mercadolivre", 1.5),
    ("olx", 1.8),
    ("compras-e-vendas", 0.8),
    ("compra-e-venda", 0.8),
    ("varejo", 1.2),
    ("consumidor", 1.5),
)

# Sinais positivos (B2B / vendedor digital / networking)
_POSITIVE_PATH = (
    ("dropship", 5.0),
    ("fornecedor", 5.0),
    ("fornecedores", 5.0),
    ("lojista", 5.0),
    ("lojistas", 5.0),
    ("revenda", 3.5),
    ("atacado", 4.0),
    ("b2b", 5.0),
    ("ecommerce", 4.0),
    ("e-commerce", 4.0),
    ("empreendedorismo", 5.0),
    ("empreendedor", 4.0),
    ("empreendedores", 4.0),
    ("negocio", 3.0),
    ("negócio", 3.0),
    ("afiliad", 4.0),
    ("hotmart", 4.0),
    ("monetizze", 3.5),
    ("braip", 3.5),
    ("shopify", 4.0),
    ("amazon", 2.5),
    ("fba", 4.0),
    ("marketplace", 3.5),
    ("supplier", 4.0),
    ("wholesale", 4.0),
    ("marketing-digital", 3.5),
    ("marketing digital", 3.5),
    ("trafego", 2.5),
    ("tráfego", 2.5),
)

_STRONG_POSITIVE_HOSTS = (
    "dinka.com.br",
    "ldo.lojadedropshipping.com.br",
    "trabalhardigital.com.br",
    "caiquedourado.com.br",
    "forum.empreender.com.br",
    "ecommplus.com.br",
)


def _source_features(base_url: str) -> Tuple[bool, float, List[str], List[str]]:
    """Retorna (hard_exclude, score, pos_tags, neg_tags)."""
    path = _path(base_url)
    host = urlparse(base_url).netloc.lower()

    for token in _HARD_EXCLUDE_PATH:
        if token in path:
            return True, -999.0, [], [f"exclude:{token}"]

    score = 0.0
    pos: List[str] = []
    neg: List[str] = []

    for token, w in _POSITIVE_PATH:
        if token in path:
            score += w
            pos.append(token)

    for token, w in _SOFT_NEGATIVE_PATH:
        if token in path:
            score -= w
            neg.append(token)

    for h in _STRONG_POSITIVE_HOSTS:
        if h in host:
            score += 4.0
            pos.append(f"host:{h}")

    if "grupo-de-vendas-whatsapp" in path:
        score -= 1.2
        neg.append("mega-lista-vendas")

    return False, score, pos, neg


def score_network_ecommerce(sources: List[str]) -> Tuple[float, Dict[str, Any]]:
    bases = sorted({_base_source(s) for s in sources})

    hard = False
    exclude_reasons: List[str] = []
    per_scores: List[float] = []
    all_pos: List[str] = []
    all_neg: List[str] = []

    for b in bases:
        h, sc, pos, neg = _source_features(b)
        if h:
            hard = True
            exclude_reasons.extend(neg)
        per_scores.append(sc)
        all_pos.extend(pos)
        all_neg.extend(neg)

    if hard:
        return -999.0, {
            "excluded": True,
            "exclude_reasons": sorted(set(exclude_reasons)),
            "unique_source_pages": len(bases),
        }

    best = max(per_scores) if per_scores else 0.0

    if len(bases) >= 14:
        best -= 2.5
        all_neg.append("many_source_pages")

    if len(bases) == 1 and urlparse(bases[0]).path in ("", "/"):
        best -= 2.0
        all_neg.append("only_homepage")

    return best, {
        "excluded": False,
        "best_source_score": round(best, 3),
        "unique_source_pages": len(bases),
        "positive_hits": sorted(set(all_pos))[:25],
        "negative_hits": sorted(set(all_neg))[:25],
    }


def filter_crawl_json(
    input_path: Path,
    output_json: Path,
    output_txt: Path,
    min_score: float = 0.0,
    top_n: int = 400,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = json.loads(input_path.read_text(encoding="utf-8"))
    enriched: List[Dict[str, Any]] = []
    excluded_count = 0

    for row in rows:
        sources = row.get("sources") or []
        score, meta = score_network_ecommerce(sources)
        if meta.get("excluded"):
            excluded_count += 1
            continue
        if score < min_score:
            continue
        enriched.append({"url": row["url"], "network_ecommerce_score": round(score, 3), **meta})

    enriched.sort(
        key=lambda x: (
            -x["network_ecommerce_score"],
            -x.get("unique_source_pages", 0),
            x["url"],
        )
    )

    top = enriched[:top_n]
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(top, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_txt.write_text("\n".join(r["url"] for r in top) + "\n", encoding="utf-8")

    return {
        "input_total": len(rows),
        "hard_excluded": excluded_count,
        "remaining_after_score_cut": len(enriched),
        "min_score": min_score,
        "exported_top": len(top),
        "output_json": str(output_json),
        "output_txt": str(output_txt),
    }
