#!/usr/bin/env python3
"""Roda o scraper original do Urbanova em paralelo, uma cidade por processo."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[\s_]+", "_", value, flags=re.UNICODE)
    return value.strip("_")


def load_master_config(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def city_config(master: Dict, cidade: str) -> Dict:
    return {
        "bairros": master.get("bairros", [""]),
        "cidades": [cidade],
        "incluir_buscas_amplas": master.get("incluir_buscas_amplas", True),
        "segmentos": master.get("segmentos", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawler Urbanova paralelo por cidade")
    parser.add_argument("--config", type=Path, default=Path("config/buscas_vale_leads_multicidade.json"))
    parser.add_argument("--output-root", default="output_vale_crawler")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-scroll", type=int, default=60)
    parser.add_argument("--details-limit", type=int, default=0, help="0 = sem limite (padrão Urbanova)")
    parser.add_argument("--final-output", default="")
    parser.add_argument("--final-limit", type=int, default=12000)
    args = parser.parse_args()

    master = load_master_config(args.config)
    cities: List[str] = list(master.get("cidades", []))
    if not cities:
        raise SystemExit("Nenhuma cidade no config.")

    config_dir = Path(args.output_root) / "_configs"
    config_dir.mkdir(parents=True, exist_ok=True)

    pending = list(cities)
    running: List[tuple[subprocess.Popen, str]] = []
    started = 0

    print(f"Crawler Urbanova | {len(cities)} cidades | {args.workers} workers paralelos")
    print(f"max-scroll={args.max_scroll} | details-limit={args.details_limit or 'sem limite'}")
    print(f"amplas={master.get('incluir_buscas_amplas')} | segmentos={len(master.get('segmentos', []))}")

    while pending or running:
        while pending and len(running) < args.workers:
            cidade = pending.pop(0)
            started += 1
            slug = slugify(cidade)
            city_cfg_path = config_dir / f"{slug}.json"
            out_dir = Path(args.output_root) / slug
            out_dir.mkdir(parents=True, exist_ok=True)
            city_cfg_path.write_text(json.dumps(city_config(master, cidade), ensure_ascii=False, indent=2), encoding="utf-8")

            cmd = [
                sys.executable,
                "-u",
                "scraper_google_maps.py",
                "--headless",
                "--buscas-config",
                str(city_cfg_path),
                "--output-dir",
                str(out_dir),
                "--max-scroll",
                str(args.max_scroll),
            ]
            if args.details_limit > 0:
                cmd.extend(["--details-limit", str(args.details_limit)])

            print(f"[{started}/{len(cities)}] Iniciando: {cidade}")
            proc = subprocess.Popen(cmd)
            running.append((proc, cidade))

        still_running: List[tuple[subprocess.Popen, str]] = []
        for proc, cidade in running:
            code = proc.poll()
            if code is None:
                still_running.append((proc, cidade))
            else:
                status = "OK" if code == 0 else f"ERRO {code}"
                print(f"Finalizado ({status}): {cidade}")
        running = still_running

        if running:
            time.sleep(10)

    final_output = args.final_output or f"{args.output_root}/leads_consolidado.csv"
    print("Consolidando...")
    subprocess.run(
        [
            sys.executable,
            "consolidar_leads_paralelo.py",
            "--output-root",
            args.output_root,
            "--master-output",
            f"{args.output_root}/empresas_consolidado.csv",
            "--final-output",
            final_output,
            "--limit",
            str(args.final_limit),
        ],
        check=False,
    )


if __name__ == "__main__":
    main()
