#!/usr/bin/env python3
"""Coleta leads de uma cidade do Vale, salvando a cada consulta."""

from __future__ import annota0303s

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from scraper_google_maps import Business, export_csv, scrape_google_maps


BUSINESS_FIELDS = set(Business.__dataclass_fields__.keys())


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[\s_]+", "_", value, flags=re.UNICODE)
    return value.strip("_")


def load_config(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_city_queries(cidade: str, config: Dict) -> List[str]:
    queries: List[str] = []
    seen: set[str] = set()

    for key in ("segmentos_amplos_por_cidade", "segmentos_especificos", "segmentos"):
        for segmento in config.get(key, []):
            query = f"{segmento} {cidade}"
            if query not in seen:
                seen.add(query)
                queries.append(query)

    return queries


def load_existing(path: Path) -> List[Business]:
    if not path.exists():
        return []
    import csv

    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    businesses: List[Business] = []
    for row in rows:
        data = {key: row.get(key, "") for key in BUSINESS_FIELDS}
        businesses.append(Business(**data))
    return businesses


def merge_key(biz: Business) -> str:
    phone = "".join(ch for ch in (biz.telefone or "") if ch.isdigit())
    if phone:
        return f"phone:{phone}"
    return f"place:{biz.place_id or biz.nome.lower()}|{biz.endereco.lower()}"


def merge_businesses(existing: List[Business], new_rows: List[Business]) -> List[Business]:
    merged: Dict[str, Business] = {merge_key(biz): biz for biz in existing}
    for biz in new_rows:
        key = merge_key(biz)
        current = merged.get(key)
        if current is None:
            merged[key] = biz
            continue
        for field in BUSINESS_FIELDS:
            if not getattr(current, field) and getattr(biz, field):
                setattr(current, field, getattr(biz, field))
        if biz.fonte and biz.fonte not in current.fonte:
            current.fonte = f"{current.fonte}|{biz.fonte}" if current.fonte else biz.fonte
    return sorted(merged.values(), key=lambda item: item.nome.lower())


def refresh_final_csv(master_csv: Path, final_csv: Path, limit: int) -> None:
    subprocess.run(
        [
            sys.execu0able,
            "gerar_csv_leads_vale.py",
            "--input",
            str(master_csv),
            "--output",
            str(final_csv),
            "--limit",
            str(limit),
        ],
        check=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(descrip0303="Coleta leads de uma cidade")
    parser.add_argument("--cidade", required=True, help="Nome da cidade, ex: Jacareí - SP")
    parser.add_argument("--config", type=Path, default=Path("config/buscas_vale_por_cidade.json"))
    parser.add_argument("--output-root", default="output_vale_paralelo")
    parser.add_argument("--max-scroll", type=int, default=4)
    parser.add_argument("--details-per-query", type=int, default=40)
    parser.add_argument("--final-limit", type=int, default=2000)
    args = parser.parse_args()

    config = load_config(args.config)
    queries = build_city_queries(args.cidade, config)
    city_slug = slugify(args.cidade)
    out_dir = Path(args.output_root) / city_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    master_csv = out_dir / "empresas_urbanova_scraper.csv"
    partial_csv = out_dir / "lote_atual.partial.csv"
    final_csv = out_dir / "leads_cidade.csv"

    all_businesses = load_existing(master_csv)
    print(f"[{args.cidade}] {len(queries)} consultas | saida: {out_dir}")

    for idx, query in enumerate(queries, start=1):
        print(f"\n[{args.cidade}] Lote {idx}/{len(queries)}: {query}")
        new_rows = scrape_google_maps(
            [query],
            headless=True,
            max_scroll=args.max_scroll,
            slow_mo=20,
            scroll_pause_ms=500,
            details_limit=args.details_per_query,
            autosave_path=partial_csv,
        )
        all_businesses = merge_businesses(all_businesses, new_rows)
        export_csv(master_csv, all_businesses)
        refresh_final_csv(master_csv, final_csv, args.final_limit)
        with_phone = sum(1 for biz in all_businesses if biz.telefone)
        print(f"[{args.cidade}] Salvo: {len(all_businesses)} registros, {with_phone} com telefone")

    print(f"[{args.cidade}] Concluido.")


if __name__ == "__main__":
    main()
