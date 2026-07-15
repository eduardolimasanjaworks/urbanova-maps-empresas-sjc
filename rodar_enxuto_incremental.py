#!/usr/bin/env python3
"""Coleta enxuta incremental: detalhes/telefone a cada busca, cidades em paralelo."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple


def load_cities(config_path: Path) -> List[str]:
    return list(json.loads(config_path.read_text(encoding="utf-8")).get("cidades", []))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config/buscas_leads_enxutos_sp.json"))
    parser.add_argument("--output-root", default="output_leads_enxutos")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-scroll", type=int, default=8)
    parser.add_argument("--details-per-query", type=int, default=50)
    args = parser.parse_args()

    cities = load_cities(args.config)
    pending = list(cities)
    running: List[Tuple[subprocess.Popen, str]] = []
    started = 0

    print(f"Coleta enxuta incremental | {len(cities)} cidades | {args.workers} workers")

    while pending or running:
        while pending and len(running) < args.workers:
            cidade = pending.pop(0)
            started += 1
            cmd = [
                sys.executable, "-u", "coletar_cidade_vale.py",
                "--cidade", cidade,
                "--config", str(args.config),
                "--output-root", args.output_root,
                "--max-scroll", str(args.max_scroll),
                "--details-per-query", str(args.details_per_query),
                "--final-limit", "12000",
            ]
            print(f"[{started}/{len(cities)}] {cidade}")
            running.append((subprocess.Popen(cmd), cidade))

        still: List[Tuple[subprocess.Popen, str]] = []
        for proc, cidade in running:
            if proc.poll() is None:
                still.append((proc, cidade))
            else:
                print(f"Fim: {cidade} (code={proc.returncode})")
        running = still
        if running:
            time.sleep(8)

    subprocess.run([
        sys.executable, "consolidar_leads_paralelo.py",
        "--output-root", args.output_root,
        "--final-output", f"{args.output_root}/leads_enxutos.csv",
        "--limit", "12000",
    ], check=False)


if __name__ == "__main__":
    main()
