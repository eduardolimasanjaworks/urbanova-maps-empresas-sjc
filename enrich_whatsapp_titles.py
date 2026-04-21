#!/usr/bin/env python3
"""Busca og:title em convites chat.whatsapp.com e pontua networking vs. achadinho (lento, respeitar rate limit)."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import httpx
from bs4 import BeautifulSoup

_TITLE_POS = (
    "lojista",
    "lojistas",
    "fornecedor",
    "fornecedores",
    "dropship",
    "revenda",
    "atacado",
    "b2b",
    "seller",
    "vendedor",
    "vendedores",
    "empreendedor",
    "empreendedores",
    "afiliad",
    "hotmart",
    "shopify",
    "marketplace",
    "ecommerce",
    "e-commerce",
    "marketing digital",
    "tráfego",
    "trafego",
    "network",
    "networking",
    "negócio",
    "negocio",
)

_TITLE_NEG = (
    "achadin",
    "oferta",
    "promo",
    "cupom",
    "desconto",
    "shopee",
    "mercado livre",
    "mercadolivre",
    "olx",
    "compras",
    "consumidor",
    "varejo",
    "grátis",
    "gratis",
    "bug",
    "cupons",
)


def _title_score(title: str) -> float:
    t = (title or "").lower()
    s = 0.0
    for w in _TITLE_POS:
        if w in t:
            s += 1.2
    for w in _TITLE_NEG:
        if w in t:
            s -= 2.0
    return s


async def _fetch_title(client: httpx.AsyncClient, url: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"url": url, "http_status": None, "og_title": "", "title_score": 0.0}
    try:
        r = await client.get(url)
        out["http_status"] = r.status_code
        if r.status_code != 200:
            return out
        soup = BeautifulSoup(r.text, "lxml")
        tag = soup.find("meta", attrs={"property": "og:title"})
        og = (tag.get("content") if tag else "") or ""
        out["og_title"] = og.strip()
        out["title_score"] = round(_title_score(out["og_title"]), 3)
    except Exception as e:
        out["error"] = str(e)
    return out


async def main_async(args: argparse.Namespace) -> int:
    ranked = json.loads(Path(args.input).read_text(encoding="utf-8"))
    take = ranked[: args.limit]

    sem = asyncio.Semaphore(1)
    results: List[Dict[str, Any]] = []

    limits = httpx.Limits(max_connections=5, max_keepalive_connections=2)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }

    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers=headers, limits=limits) as client:

        async def one(row: Dict[str, Any]) -> None:
            async with sem:
                meta = await _fetch_title(client, row["url"])
                merged = {**row, **meta, "checked_at": datetime.now(timezone.utc).isoformat()}
                results.append(merged)
                await asyncio.sleep(args.sleep_sec + random.uniform(0, args.sleep_jitter))

        await asyncio.gather(*(one(r) for r in take))

    results.sort(key=lambda x: (-(x.get("network_ecommerce_score", 0) + x.get("title_score", 0)), x["url"]))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    txt_path = Path(args.output_txt)
    good = [r for r in results if (r.get("network_ecommerce_score", 0) + r.get("title_score", 0)) >= args.min_combined]
    txt_path.write_text("\n".join(r["url"] for r in good) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "processed": len(results),
                "combined_pass": len(good),
                "output_json": str(out_path),
                "output_txt": str(txt_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--input",
        type=Path,
        default=Path("output/whatsapp_groups_manual/groups_br_network_ecommerce_ranked.json"),
    )
    p.add_argument("--limit", type=int, default=80, help="Quantidade de links do topo da lista ranqueada")
    p.add_argument("--sleep-sec", type=float, default=2.5, help="Pausa base entre requests")
    p.add_argument("--sleep-jitter", type=float, default=1.5)
    p.add_argument(
        "--output",
        type=Path,
        default=Path("output/whatsapp_groups_manual/groups_br_network_enriched_titles.json"),
    )
    p.add_argument(
        "--output-txt",
        type=Path,
        default=Path("output/whatsapp_groups_manual/groups_br_network_enriched_pass.txt"),
    )
    p.add_argument("--min-combined", type=float, default=1.0, help="network_ecommerce_score + title_score")
    return p


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
