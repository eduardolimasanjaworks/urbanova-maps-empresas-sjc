#!/usr/bin/env python3
"""Consolida CSVs de todas as cidades paralelas em um arquivo final."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


def read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolida leads paralelos")
    parser.add_argument("--output-root", default="output_vale_paralelo")
    parser.add_argument("--final-output", default="output_vale_paralelo/leads_vale_consolidado_ate_2000.csv")
    parser.add_argument("--master-output", default="output_vale_paralelo/empresas_consolidado.csv")
    parser.add_argument("--limit", type=int, default=12000)
    args = parser.parse_args()

    root = Path(args.output_root)
    root.mkdir(parents=True, exist_ok=True)

    master_rows: List[Dict[str, str]] = []
    seen_master: set[str] = set()

    city_dirs = sorted([p for p in root.iterdir() if p.is_dir()])
    for city_dir in city_dirs:
        city_csv = city_dir / "empresas_urbanova_scraper.csv"
        for row in read_rows(city_csv):
            key = f"{row.get('place_id', '')}|{row.get('nome', '')}|{row.get('telefone', '')}"
            if key in seen_master:
                continue
            seen_master.add(key)
            master_rows.append(row)

    master_path = Path(args.master_output)
    if master_rows:
        cols = list(master_rows[0].keys())
        with master_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            writer.writerows(master_rows)

    final_path = Path(args.final_output)
    if master_path.exists():
        subprocess.run(
            [
                sys.executable,
                "gerar_csv_leads_vale.py",
                "--input",
                str(master_path),
                "--output",
                str(final_path),
                "--limit",
                str(args.limit),
            ],
            check=False,
        )

    final_rows = read_rows(final_path)
    with_phone = sum(1 for row in final_rows if (row.get("telefone") or "").strip())
    print(f"Consolidado: {len(master_rows)} registros brutos")
    print(f"Leads finais: {len(final_rows)} ({with_phone} com telefone)")
    print(f"Arquivo final: {final_path}")


if __name__ == "__main__":
    main()
