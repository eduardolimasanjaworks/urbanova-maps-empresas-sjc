#!/usr/bin/env python3
"""
Pipeline completo GRATUITO para coleta de empresas do Urbanova.
Combina múltiplas fontes sem custo:
  1) Google Maps Scraper (Playwright)
  2) OpenStreetMap POIs (Overpass API)
  3) Logradouros OSM (já existente)

Uso:
  python pipeline_gratuito.py
  python pipeline_gratuito.py --skip-scraper   # só OSM
  python pipeline_gratuito.py --skip-osm       # só scraper
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple


def run_script(args: List[str], cwd: Path) -> Dict:
    print(f"\n{'='*60}")
    print(f"  Executando: {' '.join(args)}")
    print(f"{'='*60}")
    proc = subprocess.run(
        [sys.executable] + args,
        cwd=str(cwd),
        capture_output=False,
        text=True,
    )
    return {"args": args, "exit_code": proc.returncode}


def normalize_key(name: str, address: str) -> str:
    raw = f"{name.strip().lower()}|{address.strip().lower()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def read_csv_rows(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_jsonl(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def merge_businesses(scraper_data: List[Dict], osm_data: List[Dict]) -> List[Dict]:
    """
    Merge businesses from multiple sources, deduplicating by name similarity.
    Scraper data takes priority for details (phone, hours, website).
    """
    merged: Dict[str, Dict] = {}

    # First: add all scraper results
    for biz in scraper_data:
        name = biz.get("nome", "").strip()
        addr = biz.get("endereco", "").strip()
        if not name:
            continue
        key = normalize_key(name, addr)
        if key not in merged:
            merged[key] = {
                "id": key,
                "nome": name,
                "endereco": addr,
                "latitude": biz.get("latitude", ""),
                "longitude": biz.get("longitude", ""),
                "telefone": biz.get("telefone", ""),
                "horario": biz.get("horario", ""),
                "website": biz.get("website", ""),
                "avaliacao": biz.get("avaliacao", ""),
                "total_reviews": biz.get("total_reviews", ""),
                "categoria": biz.get("categoria", ""),
                "status_negocio": biz.get("status_negocio", ""),
                "google_maps_url": biz.get("google_maps_url", ""),
                "email": "",
                "osm_id": "",
                "fontes": "google_maps_scraper",
            }
        else:
            # Enrich existing
            existing = merged[key]
            for field in ["telefone", "horario", "website", "avaliacao", "categoria"]:
                if not existing.get(field) and biz.get(field):
                    existing[field] = biz[field]
            if "google_maps_scraper" not in existing["fontes"]:
                existing["fontes"] += ",google_maps_scraper"

    # Then: add/enrich with OSM data
    for poi in osm_data:
        name = poi.get("nome", "").strip()
        addr = poi.get("endereco", "").strip()
        if not name:
            continue

        key = normalize_key(name, addr)

        if key in merged:
            # Enrich existing with OSM data
            existing = merged[key]
            if not existing.get("telefone") and poi.get("telefone"):
                existing["telefone"] = poi["telefone"]
            if not existing.get("horario") and poi.get("horario"):
                existing["horario"] = poi["horario"]
            if not existing.get("website") and poi.get("website"):
                existing["website"] = poi["website"]
            if not existing.get("email") and poi.get("email"):
                existing["email"] = poi["email"]
            if not existing.get("osm_id"):
                existing["osm_id"] = poi.get("osm_id", "")
            if "osm_overpass" not in existing["fontes"]:
                existing["fontes"] += ",osm_overpass"
        else:
            # New from OSM
            merged[key] = {
                "id": key,
                "nome": name,
                "endereco": addr,
                "latitude": poi.get("latitude", ""),
                "longitude": poi.get("longitude", ""),
                "telefone": poi.get("telefone", ""),
                "horario": poi.get("horario", ""),
                "website": poi.get("website", ""),
                "avaliacao": "",
                "total_reviews": "",
                "categoria": poi.get("categoria_osm", ""),
                "status_negocio": "",
                "google_maps_url": "",
                "email": poi.get("email", ""),
                "osm_id": poi.get("osm_id", ""),
                "fontes": "osm_overpass",
            }

    return sorted(merged.values(), key=lambda x: x["nome"].lower())


def export_merged_csv(path: Path, businesses: List[Dict]) -> None:
    cols = [
        "id", "nome", "endereco", "latitude", "longitude",
        "telefone", "horario", "website", "email",
        "avaliacao", "total_reviews", "categoria",
        "status_negocio", "google_maps_url", "osm_id", "fontes",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(businesses)


def export_merged_jsonl(path: Path, businesses: List[Dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for biz in businesses:
            f.write(json.dumps(biz, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline gratuito completo")
    parser.add_argument("--skip-scraper", action="store_true", help="Pular Google Maps scraping")
    parser.add_argument("--skip-osm", action="store_true", help="Pular extração OSM")
    parser.add_argument("--skip-vias", action="store_true", help="Pular extração de vias")
    parser.add_argument("--max-scroll", type=int, default=60, help="Max scrolls no scraper")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument(
        "--buscas-config",
        type=Path,
        default=None,
        help="JSON de segmentos (repassado ao scraper; default: config/buscas_urbanova.json)",
    )
    parser.add_argument(
        "--merge-only",
        action="store_true",
        help="Só gera CSV final a partir dos CSV já em output/ (pula vias, OSM e scraper)",
    )
    args = parser.parse_args()
    if args.merge_only:
        args.skip_vias = True
        args.skip_osm = True
        args.skip_scraper = True

    root = Path(".").resolve()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    phases = []

    # ─── Fase 1: Extrair logradouros via Overpass ─────────────────
    if not args.skip_vias:
        print("\n🗺️  FASE 1: Extraindo logradouros via OpenStreetMap...")
        res = run_script(["extrair_vias_urbanova.py"], cwd=root)
        phases.append({"fase": "vias_osm", "exit_code": res["exit_code"]})
        if res["exit_code"] != 0:
            print("⚠️  Extração de vias falhou (não crítico, continuando...)")
    else:
        print("\n⏭️  FASE 1: Extração de vias pulada")

    # ─── Fase 2: Extrair POIs via OSM ─────────────────────────────
    if not args.skip_osm:
        print("\n🏪  FASE 2: Extraindo POIs (empresas) do OpenStreetMap...")
        res = run_script(
            ["extrair_pois_osm.py", "--output-dir", args.output_dir],
            cwd=root,
        )
        phases.append({"fase": "pois_osm", "exit_code": res["exit_code"]})
        if res["exit_code"] != 0:
            print("⚠️  Extração OSM falhou (continuando com outras fontes...)")
    else:
        print("\n⏭️  FASE 2: Extração OSM pulada")

    # ─── Fase 3: Google Maps Scraper ──────────────────────────────
    if not args.skip_scraper:
        print("\n🕷️  FASE 3: Scraping Google Maps (gratuito)...")
        scraper_cmd = [
            "scraper_google_maps.py",
            "--headless",
            "--max-scroll", str(args.max_scroll),
            "--output-dir", args.output_dir,
        ]
        if args.buscas_config is not None:
            scraper_cmd.extend(["--buscas-config", str(args.buscas_config.resolve())])
        res = run_script(scraper_cmd, cwd=root)
        phases.append({"fase": "scraper_gmaps", "exit_code": res["exit_code"]})
        if res["exit_code"] != 0:
            print("⚠️  Scraper falhou (continuando com dados disponíveis...)")
    else:
        print("\n⏭️  FASE 3: Scraping Google Maps pulado")

    # ─── Fase 4: Merge de todas as fontes ─────────────────────────
    print("\n🔀  FASE 4: Combinando dados de todas as fontes...")

    scraper_data = read_csv_rows(out / "empresas_urbanova_scraper.csv")
    osm_data = read_csv_rows(out / "pois_osm_urbanova.csv")

    print(f"  → Scraper Google Maps: {len(scraper_data)} empresas")
    print(f"  → OSM Overpass: {len(osm_data)} POIs")

    merged = merge_businesses(scraper_data, osm_data)
    print(f"  → Total unificado (deduplicado): {len(merged)} empresas")

    # Filter Urbanova
    urbanova = []
    outros = []
    for biz in merged:
        text = f"{biz.get('endereco', '')} {biz.get('nome', '')}".lower()
        if "urbanova" in text:
            urbanova.append(biz)
        else:
            outros.append(biz)

    # Export
    export_merged_csv(out / "empresas_urbanova_FINAL.csv", merged)
    export_merged_csv(out / "empresas_urbanova_FINAL_filtrada.csv", urbanova)
    export_merged_jsonl(out / "empresas_unificadas.jsonl", merged)

    elapsed = time.time() - start_time

    # ─── Resumo final ─────────────────────────────────────────────
    with_phone = sum(1 for b in merged if b.get("telefone"))
    with_hours = sum(1 for b in merged if b.get("horario"))
    with_site = sum(1 for b in merged if b.get("website"))
    with_email = sum(1 for b in merged if b.get("email"))
    total = len(merged) or 1

    summary = {
        "timestamp_unix": int(time.time()),
        "metodo": "pipeline_gratuito_multi_fonte",
        "custo_total": "R$ 0,00",
        "tempo_execucao_segundos": round(elapsed, 1),
        "fases": phases,
        "fontes": {
            "google_maps_scraper": len(scraper_data),
            "osm_overpass": len(osm_data),
        },
        "resultados": {
            "total_unificado": len(merged),
            "confirmados_urbanova": len(urbanova),
            "arredores": len(outros),
        },
        "cobertura": {
            "com_telefone_pct": round(100.0 * with_phone / total, 2),
            "com_horario_pct": round(100.0 * with_hours / total, 2),
            "com_website_pct": round(100.0 * with_site / total, 2),
            "com_email_pct": round(100.0 * with_email / total, 2),
        },
        "arquivos_finais": [
            "output/empresas_urbanova_FINAL.csv",
            "output/empresas_urbanova_FINAL_filtrada.csv",
            "output/empresas_unificadas.jsonl",
        ],
        "nota": "Nenhuma API paga foi utilizada. Dados extraídos via scraping e OpenStreetMap.",
    }

    (out / "resumo_pipeline_gratuito.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n{'='*60}")
    print("  ✅ PIPELINE GRATUITO CONCLUÍDO!")
    print(f"{'='*60}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
