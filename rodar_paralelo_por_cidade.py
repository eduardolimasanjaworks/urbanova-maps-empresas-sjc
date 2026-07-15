#!/usr/bin/env python3
"""Dispara coleta paralela, uma cidade por processo."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import List


def load_cities(config_path: Path) -> List[str]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return list(data.get("cidades", []))


def main() -> None:
    parser = argparse.ArgumentParser(description="Orquestrador paralelo por cidade")
    parser.add_argument("--config", type=Path, default=Path("config/buscas_vale_por_cidade.json"))
    parser.add_argument("--output-root", default="output_vale_paralelo")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-scroll", type=int, default=4)
    parser.add_argument("--details-per-query", type=int, default=40)
    args = parser.parse_args()

    cities = load_cities(args.config)
    if not cities:
        raise SystemExit("Nenhuma cidade encontrada no config.")

    running: List[subprocess.Popen] = []
    pending = list(cities)
    started = 0

    print(f"Cidades: {len(cities)} | workers paralelos: {args.workers}")

    while pending or running:
        while pending and len(running) < args.workers:
            cidade = pending.pop(0)
            started += 1
            cmd = [
                sys.executable,
                "-u",
                "coletar_cidade_vale.py",
                "--cidade",
                cidade,
                "--config",
                str(args.config),
                "--output-root",
                args.output_root,
                "--max-scroll",
                str(args.max_scroll),
                "--details-per-query",
                str(args.details_per_query),
            ]
            print(f"Iniciando worker {started}/{len(cities)}: {cidade}")
            proc = subprocess.Popen(cmd)
            running.append(proc)

        still_running: List[subprocess.Popen] = []
        for proc in running:
            code = proc.poll()
            if code is None:
                still_running.append(proc)
            elif code != 0:
                print(f"Worker finalizou com erro (code={code})")
        running = still_running

        if running:
            time.sleep(5)

    print("Todos os workers finalizaram.")
    subprocess.run([sys.executable, "consolidar_leads_paralelo.py", "--output-root", args.output_root], check=False)


if __name__ == "__main__":
    main()
