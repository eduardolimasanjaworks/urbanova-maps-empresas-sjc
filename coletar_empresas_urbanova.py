#!/usr/bin/env python3
"""
Coleta empresas do Urbanova usando Google Places API (New).

Uso:
  python coletar_empresas_urbanova.py --api-key SUA_CHAVE

Saidas:
  - output/places_descoberta.jsonl
  - output/places_detalhes.jsonl
  - output/empresas_urbanova.csv
  - output/resumo_execucao.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_BASE_URL = "https://places.googleapis.com/v1/places/"


DISCOVERY_FIELDS = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.primaryType",
        "places.types",
        "places.googleMapsUri",
    ]
)

DETAIL_FIELDS = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "location",
        "internationalPhoneNumber",
        "nationalPhoneNumber",
        "regularOpeningHours",
        "websiteUri",
        "businessStatus",
        "googleMapsUri",
        "primaryType",
        "types",
        "editorialSummary",
    ]
)


# Evita termos vagos (ex.: "empresas"), priorizando segmentos reais.
SEGMENT_QUERIES = [
    "restaurante",
    "lanchonete",
    "cafeteria",
    "padaria",
    "mercado",
    "farmacia",
    "clinica",
    "dentista",
    "academia",
    "escola",
    "advocacia",
    "contabilidade",
    "imobiliaria",
    "pet shop",
    "salão de beleza",
    "barbearia",
    "auto eletrica",
    "mecanica",
]

TYPE_GROUPS = [
    ["restaurant", "cafe", "bakery"],
    ["hospital", "dentist", "pharmacy", "doctor"],
    ["beauty_salon", "lawyer", "accounting", "real_estate_agency"],
    ["school", "university"],
    ["store", "supermarket", "convenience_store"],
    ["car_repair", "gas_station"],
]


@dataclass
class BBox:
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float


def load_geo(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_bbox(path: Path) -> BBox:
    data = load_geo(path)
    b = data["envelope_operacional"]
    return BBox(
        lat_min=float(b["lat_min"]),
        lat_max=float(b["lat_max"]),
        lon_min=float(b["lon_min"]),
        lon_max=float(b["lon_max"]),
    )


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def grid_points(bbox: BBox, step_meters: int = 300) -> Iterable[Tuple[float, float]]:
    lat_step = step_meters / 111_320.0
    avg_lat = (bbox.lat_min + bbox.lat_max) / 2.0
    lon_step = step_meters / (111_320.0 * max(math.cos(math.radians(avg_lat)), 0.2))

    lat = bbox.lat_min
    while lat <= bbox.lat_max + 1e-9:
        lon = bbox.lon_min
        while lon <= bbox.lon_max + 1e-9:
            yield (round(lat, 7), round(lon, 7))
            lon += lon_step
        lat += lat_step


def _request_json(
    url: str,
    api_key: str,
    method: str = "GET",
    field_mask: str | None = None,
    payload: Dict | None = None,
    timeout: int = 40,
) -> Dict:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
    }
    if field_mask:
        headers["X-Goog-FieldMask"] = field_mask

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    retries = 3
    backoff = 0.8
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8")
                return json.loads(text)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            retriable = exc.code in {429, 500, 502, 503, 504}
            if attempt < retries and retriable:
                time.sleep(backoff * (2**attempt))
                continue
            raise RuntimeError(f"HTTP {exc.code} {url} -> {body}") from exc
        except urllib.error.URLError as exc:
            if attempt < retries:
                time.sleep(backoff * (2**attempt))
                continue
            raise RuntimeError(f"URL_ERROR {url} -> {exc}") from exc


def search_nearby(
    api_key: str, lat: float, lon: float, radius: int, types: List[str] | None
) -> List[Dict]:
    payload: Dict = {
        "maxResultCount": 20,
        "rankPreference": "DISTANCE",
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": float(radius),
            }
        },
    }
    if types:
        payload["includedTypes"] = types

    out = _request_json(
        NEARBY_URL,
        api_key=api_key,
        method="POST",
        field_mask=DISCOVERY_FIELDS,
        payload=payload,
    )
    return out.get("places", [])


def search_text(api_key: str, query: str, location_bias: Dict) -> List[Dict]:
    payload = {
        "textQuery": query,
        "maxResultCount": 20,
        "locationBias": location_bias,
        "languageCode": "pt-BR",
    }
    out = _request_json(
        TEXT_URL,
        api_key=api_key,
        method="POST",
        field_mask=DISCOVERY_FIELDS,
        payload=payload,
    )
    return out.get("places", [])


def place_details(api_key: str, place_id: str) -> Dict:
    url = DETAILS_BASE_URL + urllib.parse.quote(place_id, safe="")
    return _request_json(url, api_key=api_key, method="GET", field_mask=DETAIL_FIELDS)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def jsonl_write(path: Path, rows: Iterable[Dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def flatten_hours(hours: Dict | None) -> str:
    if not hours:
        return ""
    texts = hours.get("weekdayDescriptions") or []
    return " | ".join(texts)


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def extract_roads(geo_data: Dict) -> List[Dict]:
    refs = geo_data.get("referencias", [])
    return [r for r in refs if r.get("tipo") in {"avenida", "rua"}]


def extract_roads_from_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    roads = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                roads.append(
                    {
                        "nome": row.get("nome_via", "").strip(),
                        "tipo": row.get("tipo_via", "logradouro"),
                        "lat": float(row.get("lat_ref", 0) or 0),
                        "lon": float(row.get("lon_ref", 0) or 0),
                    }
                )
            except ValueError:
                continue
    return [r for r in roads if r["nome"] and (r["lat"] != 0 or r["lon"] != 0)]


def build_text_queries(city: str = "sao jose dos campos", bairro: str = "urbanova") -> List[str]:
    queries: List[str] = []
    for segment in SEGMENT_QUERIES:
        queries.append(f"{segment} {bairro} {city}")
    return queries


def csv_export(path: Path, details: List[Dict], lineage: Dict[str, Dict]) -> None:
    cols = [
        "place_id",
        "nome",
        "endereco",
        "latitude",
        "longitude",
        "telefone_nacional",
        "telefone_internacional",
        "horario",
        "website",
        "status_negocio",
        "tipo_principal",
        "tipos",
        "google_maps_url",
        "descricao",
        "origens",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for item in details:
            place_id = item.get("id", "")
            loc = item.get("location", {})
            display = item.get("displayName", {})
            summary = item.get("editorialSummary", {}) or {}
            writer.writerow(
                {
                    "place_id": place_id,
                    "nome": display.get("text", ""),
                    "endereco": item.get("formattedAddress", ""),
                    "latitude": loc.get("latitude", ""),
                    "longitude": loc.get("longitude", ""),
                    "telefone_nacional": item.get("nationalPhoneNumber", ""),
                    "telefone_internacional": item.get("internationalPhoneNumber", ""),
                    "horario": flatten_hours(item.get("regularOpeningHours")),
                    "website": item.get("websiteUri", ""),
                    "status_negocio": item.get("businessStatus", ""),
                    "tipo_principal": item.get("primaryType", ""),
                    "tipos": ",".join(item.get("types", [])),
                    "google_maps_url": item.get("googleMapsUri", ""),
                    "descricao": summary.get("text", ""),
                    "origens": json.dumps(lineage.get(place_id, {}), ensure_ascii=False),
                }
            )


def csv_export_filtered(path: Path, details: List[Dict], bairro_token: str = "urbanova") -> None:
    token = bairro_token.lower()
    cols = [
        "place_id",
        "nome",
        "endereco",
        "latitude",
        "longitude",
        "telefone_nacional",
        "telefone_internacional",
        "horario",
        "website",
        "status_negocio",
        "tipo_principal",
        "tipos",
        "google_maps_url",
        "descricao",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for item in details:
            addr = str(item.get("formattedAddress", ""))
            if token not in addr.lower():
                continue
            loc = item.get("location", {})
            display = item.get("displayName", {})
            summary = item.get("editorialSummary", {}) or {}
            writer.writerow(
                {
                    "place_id": item.get("id", ""),
                    "nome": display.get("text", ""),
                    "endereco": addr,
                    "latitude": loc.get("latitude", ""),
                    "longitude": loc.get("longitude", ""),
                    "telefone_nacional": item.get("nationalPhoneNumber", ""),
                    "telefone_internacional": item.get("internationalPhoneNumber", ""),
                    "horario": flatten_hours(item.get("regularOpeningHours")),
                    "website": item.get("websiteUri", ""),
                    "status_negocio": item.get("businessStatus", ""),
                    "tipo_principal": item.get("primaryType", ""),
                    "tipos": ",".join(item.get("types", [])),
                    "google_maps_url": item.get("googleMapsUri", ""),
                    "descricao": summary.get("text", ""),
                }
            )


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=os.environ.get("MAPS_SERVER_API_KEY", ""))
    parser.add_argument("--radius", type=int, default=300)
    parser.add_argument("--step", type=int, default=300)
    parser.add_argument("--road-radius", type=int, default=200, help="Raio para varredura no ponto de cada rua/avenida")
    parser.add_argument("--road-threshold-m", type=int, default=180, help="Distancia maxima para considerar que uma via teve cobertura")
    parser.add_argument("--skip-road-scan", action="store_true", help="Desabilita varredura por ruas/avenidas de referencia")
    parser.add_argument("--skip-text-scan", action="store_true", help="Desabilita buscas textuais por segmento")
    parser.add_argument("--roads-file", default="output/vias_urbanova.csv", help="CSV de logradouros extraido via Overpass.")
    parser.add_argument("--sleep-ms", type=int, default=120)
    parser.add_argument(
        "--geo-file",
        default="urbanova_referencias_geograficas.json",
        help="Arquivo com envelope_operacional.",
    )
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit("Informe --api-key ou MAPS_SERVER_API_KEY no .env")

    geo_file = Path(args.geo_file)
    geo_data = load_geo(geo_file)
    bbox = load_bbox(geo_file)
    out_dir = Path("output")
    ensure_dir(out_dir)

    sleep_s = max(args.sleep_ms, 0) / 1000.0
    discovered: Dict[str, Dict] = {}
    lineage: Dict[str, Dict] = {}
    discovery_rows: List[Dict] = []

    # 1) nearby por grid + tipos (coluna vertebral da cobertura)
    cells = list(grid_points(bbox, step_meters=args.step))
    for idx, (lat, lon) in enumerate(cells):
        for group in TYPE_GROUPS:
            places = search_nearby(args.api_key, lat, lon, args.radius, group)
            for p in places:
                pid = p.get("id")
                if not pid:
                    continue
                discovered.setdefault(pid, p)
                lineage.setdefault(pid, {"nearby": [], "text": [], "roads": []})
                lineage[pid]["nearby"].append({"cell_index": idx, "lat": lat, "lon": lon, "types": group})
                discovery_rows.append({"source": "nearby", "cell_index": idx, "types": group, "place": p})
            time.sleep(sleep_s)

    # 2) text search por segmentos (evita termos vagos)
    center = {
        "circle": {
            "center": {
                "latitude": round((bbox.lat_min + bbox.lat_max) / 2.0, 7),
                "longitude": round((bbox.lon_min + bbox.lon_max) / 2.0, 7),
            },
            "radius": 2500.0,
        }
    }
    text_queries = build_text_queries()
    if not args.skip_text_scan:
        for query in text_queries:
            places = search_text(args.api_key, query, center)
            for p in places:
                pid = p.get("id")
                if not pid:
                    continue
                discovered.setdefault(pid, p)
                lineage.setdefault(pid, {"nearby": [], "text": [], "roads": []})
                lineage[pid]["text"].append({"query": query})
                discovery_rows.append({"source": "text", "query": query, "place": p})
            time.sleep(sleep_s)

    # 3) scan por ruas/avenidas de referencia (proximidade + consulta textual por via)
    roads = extract_roads(geo_data)
    roads_file = Path(args.roads_file)
    roads_csv = extract_roads_from_csv(roads_file)
    if roads_csv:
        roads = roads_csv
    if not args.skip_road_scan:
        for road in roads:
            road_name = road.get("nome", "")
            lat = float(road.get("lat"))
            lon = float(road.get("lon"))

            # Nearby direto no ponto da via para cada grupo.
            for group in TYPE_GROUPS:
                places = search_nearby(args.api_key, lat, lon, args.road_radius, group)
                for p in places:
                    pid = p.get("id")
                    if not pid:
                        continue
                    discovered.setdefault(pid, p)
                    lineage.setdefault(pid, {"nearby": [], "text": [], "roads": []})
                    lineage[pid]["roads"].append({"road": road_name, "mode": "nearby", "types": group})
                    discovery_rows.append({"source": "road_nearby", "road": road_name, "types": group, "place": p})
                time.sleep(sleep_s)

            # Text query por segmento + rua.
            for segment in SEGMENT_QUERIES:
                query = f"{segment} {road_name} urbanova sao jose dos campos"
                places = search_text(args.api_key, query, center)
                for p in places:
                    pid = p.get("id")
                    if not pid:
                        continue
                    discovered.setdefault(pid, p)
                    lineage.setdefault(pid, {"nearby": [], "text": [], "roads": []})
                    lineage[pid]["roads"].append({"road": road_name, "mode": "text", "segment": segment})
                    discovery_rows.append(
                        {"source": "road_text", "road": road_name, "segment": segment, "query": query, "place": p}
                    )
                time.sleep(sleep_s)

    # 4) details de cada place deduplicado
    details_rows: List[Dict] = []
    for pid in sorted(discovered.keys()):
        # Detalhes pedem id simples; caso venha "places/XXX", normaliza.
        detail_key = pid.split("/")[-1]
        try:
            detail = place_details(args.api_key, detail_key)
        except Exception as exc:  # noqa: BLE001
            detail = {"id": detail_key, "error": str(exc)}
        details_rows.append(detail)
        time.sleep(sleep_s)

    # 5) persistencia
    jsonl_write(out_dir / "places_descoberta.jsonl", discovery_rows)
    jsonl_write(out_dir / "places_detalhes.jsonl", details_rows)
    csv_export(out_dir / "empresas_urbanova.csv", details_rows, lineage)
    csv_export_filtered(out_dir / "empresas_urbanova_filtrada.csv", details_rows, bairro_token="urbanova")

    # 6) auditoria por via: quais ruas/avenidas ainda parecem sem cobertura
    detail_locations = []
    for d in details_rows:
        loc = d.get("location") or {}
        if "latitude" in loc and "longitude" in loc:
            detail_locations.append((float(loc["latitude"]), float(loc["longitude"])))

    road_coverage = []
    for road in roads:
        road_name = road.get("nome", "")
        lat = float(road.get("lat"))
        lon = float(road.get("lon"))
        min_dist = None
        if detail_locations:
            min_dist = min(haversine_meters(lat, lon, p_lat, p_lon) for p_lat, p_lon in detail_locations)
        road_coverage.append(
            {
                "road": road_name,
                "lat": lat,
                "lon": lon,
                "nearest_place_distance_m": None if min_dist is None else round(min_dist, 1),
                "covered": bool(min_dist is not None and min_dist <= args.road_threshold_m),
            }
        )
    uncovered_roads = [r for r in road_coverage if not r["covered"]]
    (out_dir / "cobertura_por_via.json").write_text(
        json.dumps({"roads": road_coverage, "uncovered_roads": uncovered_roads}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 7) resumo
    with_phone = sum(1 for d in details_rows if d.get("nationalPhoneNumber") or d.get("internationalPhoneNumber"))
    with_hours = sum(1 for d in details_rows if d.get("regularOpeningHours"))
    with_site = sum(1 for d in details_rows if d.get("websiteUri"))
    with_location = sum(1 for d in details_rows if d.get("location"))
    total = len(details_rows) or 1

    summary = {
        "timestamp_unix": int(time.time()),
        "cells": len(cells),
        "roads_scanned": 0 if args.skip_road_scan else len(roads),
        "total_unique_places": len(details_rows),
        "requests_profile": {
            "grid_search_enabled": True,
            "text_search_enabled": not args.skip_text_scan,
            "road_scan_enabled": not args.skip_road_scan,
            "segments": len(SEGMENT_QUERIES),
            "roads_source": "csv_overpass" if roads_csv else "geo_referencias",
        },
        "coverage": {
            "with_phone_pct": round(100.0 * with_phone / total, 2),
            "with_hours_pct": round(100.0 * with_hours / total, 2),
            "with_website_pct": round(100.0 * with_site / total, 2),
            "with_location_pct": round(100.0 * with_location / total, 2),
            "uncovered_roads_count": len(uncovered_roads),
        },
        "notes": [
            "Dados sujeitos a termos de uso da Google Maps Platform.",
            "Cobertura pode variar por atualização do indice local.",
            "Email e WhatsApp nao sao campos dedicados nativos da Places API.",
            "Consultas vagas foram removidas por padrao para reduzir ruído.",
        ],
    }
    (out_dir / "resumo_execucao.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

