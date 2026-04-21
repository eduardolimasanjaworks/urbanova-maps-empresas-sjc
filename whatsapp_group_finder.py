#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import List

from whatsapp_finder.crawler import CrawlConfig, run_crawler
from whatsapp_finder.dorks import generate_dorks
from whatsapp_finder.storage import ResultStore


DEFAULT_ENGINES = ["bing", "duckduckgo", "brave"]


def _parse_csv(value: str) -> List[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def load_keywords(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de keywords não encontrado: {path}")
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [x for x in lines if x and not x.startswith("#")]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Descoberta OSINT de links públicos chat.whatsapp.com",
    )
    parser.add_argument(
        "--keywords-file",
        type=Path,
        default=Path("config/keywords_ecommerce.txt"),
        help="Arquivo com uma keyword por linha",
    )
    parser.add_argument(
        "--engines",
        type=str,
        default=",".join(DEFAULT_ENGINES),
        help="Motores: bing,duckduckgo,brave,searxng",
    )
    parser.add_argument(
        "--searx-url",
        type=str,
        default="",
        help="URL base do SearXNG (ex.: http://localhost:8080) quando usar engine searxng",
    )
    parser.add_argument("--target", type=int, default=15000, help="Meta de links únicos")
    parser.add_argument("--depth", type=int, default=2, help="Profundidade recursiva por domínio")
    parser.add_argument("--per-query", type=int, default=30, help="Resultados por query em cada engine")
    parser.add_argument(
        "--max-dorks",
        type=int,
        default=350,
        help="Limite de dorks por execução (controle de tempo/custos)",
    )
    parser.add_argument("--delay-min", type=float, default=1.2, help="Delay mínimo entre requests")
    parser.add_argument("--delay-max", type=float, default=3.2, help="Delay máximo entre requests")
    parser.add_argument("--lang", type=str, default="pt,en,es", help="Idiomas para expansão de dorks")
    parser.add_argument("--concurrency", type=int, default=12, help="Concorrência HTTP do crawler")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("output/whatsapp_groups"),
        help="Diretório de saída",
    )
    return parser


async def async_main(args: argparse.Namespace) -> int:
    keywords = load_keywords(args.keywords_file)
    engines = _parse_csv(args.engines)
    langs = _parse_csv(args.lang)
    dorks = generate_dorks(keywords, langs=langs)

    if not dorks:
        raise RuntimeError("Nenhuma dork foi gerada; verifique keywords e idiomas.")

    print(
        f"[inicio] keywords={len(keywords)} dorks={len(dorks)} engines={engines} "
        f"target={args.target} depth={args.depth} max_dorks={args.max_dorks}",
        flush=True,
    )
    store = ResultStore(args.out)
    cfg = CrawlConfig(
        engines=engines,
        dorks=dorks,
        per_query=args.per_query,
        target=args.target,
        depth=args.depth,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        concurrency=max(2, args.concurrency),
        max_dorks=max(1, args.max_dorks),
        searx_url=args.searx_url.strip() or None,
    )
    summary = await run_crawler(cfg, store)
    store.save_checkpoint()
    store.export_unique(summary)
    print(f"[fim] links_unicos={summary['total_unico']} output={args.out}", flush=True)
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())

