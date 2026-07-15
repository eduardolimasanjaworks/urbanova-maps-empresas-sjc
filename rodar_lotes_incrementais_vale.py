#!/usr/bin/env python3
"""Roda buscas em lotes pequenos e salva resultados a cada consulta."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from scraper_google_maps import Business, build_search_queries, export_csv, scrape_google_maps


BUSINESS_FIELDS = set(Business.__dataclass_fields__.keys())


def load_existing(path: Path) -> List[Business]:
    if not path.exists():
        return []
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
            sys.executable,
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
    parser = argparse.ArgumentParser(description="Coleta incremental por consulta")
    parser.add_argument("--buscas-config", type=Path, required=True)
    parser.add_argument("--output-dir", default="output_vale_esportes_escolas_condominios")
    parser.add_argument("--query-offset", type=int, default=0)
    parser.add_argument("--query-limit", type=int, default=30)
    parser.add_argument("--max-scroll", type=int, default=1)
    parser.add_argument("--details-per-query", type=int, default=20)
    parser.add_argument("--final-limit", type=int, default=2000)
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    master_csv = out_dir / "empresas_urbanova_scraper.csv"
    partial_csv = out_dir / "lote_atual.partial.csv"
    final_csv = out_dir / "leads_vale_publicos_ate_2000.csv"

    queries = build_search_queries(args.buscas_config)
    if args.query_offset > 0:
        queries = queries[args.query_offset:]
    if args.query_limit > 0:
        queries = queries[: args.query_limit]

    all_businesses = load_existing(master_csv)
    print(f"Iniciando lotes incrementais: {len(queries)} consultas")
    print(f"CSV mestre: {master_csv}")
    print(f"CSV final: {final_csv}")

    for idx, query in enumerate(queries, start=1):
        print(f"\n=== Lote {idx}/{len(queries)}: {query} ===")
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
        print(f"Salvo apos lote {idx}: {len(all_businesses)} registros, {with_phone} com telefone")


if __name__ == "__main__":
    main()
