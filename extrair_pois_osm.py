#!/usr/bin/env python3
"""
Extrai POIs (pontos de interesse / empresas) do Urbanova via Overpass (OSM).
Fonte 100% gratuita e aberta.

Saídas:
  - output/pois_osm_urbanova.csv
  - output/pois_osm_urbanova.jsonl
  - output/pois_osm_urbanova.geojson
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple


OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def overpass_query(query: str, timeout: int = 120) -> Dict:
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data, method="POST")
    retries = 3
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Overpass API error: {e}")


def get_urbanova_pois() -> List[Dict]:
    """
    Query all commercial/service POIs inside Urbanova boundary.
    Includes: shops, amenities, offices, tourism, healthcare, etc.
    """
    query = """
[out:json][timeout:120];
area["name"="São José dos Campos"]["admin_level"="8"]["boundary"="administrative"]->.sjc;
rel(area.sjc)["name"~"Urbanova"]["boundary"="administrative"]->.urb;
area.urb->.urbArea;
(
  // Shops (all types)
  node(area.urbArea)["shop"];
  way(area.urbArea)["shop"];

  // Amenities (restaurants, pharmacies, banks, etc.)
  node(area.urbArea)["amenity"];
  way(area.urbArea)["amenity"];

  // Offices
  node(area.urbArea)["office"];
  way(area.urbArea)["office"];

  // Healthcare
  node(area.urbArea)["healthcare"];
  way(area.urbArea)["healthcare"];

  // Tourism (hotels, etc.)
  node(area.urbArea)["tourism"];
  way(area.urbArea)["tourism"];

  // Leisure
  node(area.urbArea)["leisure"]["name"];
  way(area.urbArea)["leisure"]["name"];

  // Craft
  node(area.urbArea)["craft"];
  way(area.urbArea)["craft"];
);
out center;
"""
    return overpass_query(query).get("elements", [])


def get_bbox_pois(bbox: Dict) -> List[Dict]:
    """
    Fallback: query POIs by bounding box if boundary-based query fails.
    """
    lat_min = bbox["lat_min"]
    lat_max = bbox["lat_max"]
    lon_min = bbox["lon_min"]
    lon_max = bbox["lon_max"]

    query = f"""
[out:json][timeout:120];
(
  node["shop"]({lat_min},{lon_min},{lat_max},{lon_max});
  way["shop"]({lat_min},{lon_min},{lat_max},{lon_max});
  node["amenity"]({lat_min},{lon_min},{lat_max},{lon_max});
  way["amenity"]({lat_min},{lon_min},{lat_max},{lon_max});
  node["office"]({lat_min},{lon_min},{lat_max},{lon_max});
  way["office"]({lat_min},{lon_min},{lat_max},{lon_max});
  node["healthcare"]({lat_min},{lon_min},{lat_max},{lon_max});
  way["healthcare"]({lat_min},{lon_min},{lat_max},{lon_max});
  node["tourism"]["name"]({lat_min},{lon_min},{lat_max},{lon_max});
  way["tourism"]["name"]({lat_min},{lon_min},{lat_max},{lon_max});
  node["leisure"]["name"]({lat_min},{lon_min},{lat_max},{lon_max});
  way["leisure"]["name"]({lat_min},{lon_min},{lat_max},{lon_max});
  node["craft"]({lat_min},{lon_min},{lat_max},{lon_max});
  way["craft"]({lat_min},{lon_min},{lat_max},{lon_max});
);
out center;
"""
    return overpass_query(query).get("elements", [])


def element_to_poi(el: Dict) -> Dict:
    tags = el.get("tags", {})

    # Get coordinates
    lat = el.get("lat", 0.0)
    lon = el.get("lon", 0.0)
    if not lat and "center" in el:
        lat = el["center"].get("lat", 0.0)
        lon = el["center"].get("lon", 0.0)

    # Determine category
    category = ""
    for key in ["shop", "amenity", "office", "healthcare", "tourism", "leisure", "craft"]:
        if key in tags:
            category = f"{key}:{tags[key]}"
            break

    # Build phone from multiple possible tags
    phone = tags.get("phone", "") or tags.get("contact:phone", "") or tags.get("contact:mobile", "")

    # Build website
    website = tags.get("website", "") or tags.get("contact:website", "") or tags.get("url", "")

    # Opening hours
    hours = tags.get("opening_hours", "")

    # Name
    name = tags.get("name", "") or tags.get("name:pt", "") or tags.get("brand", "")

    # Address
    addr_parts = []
    if tags.get("addr:street"):
        addr_parts.append(tags["addr:street"])
    if tags.get("addr:housenumber"):
        addr_parts.append(tags["addr:housenumber"])
    if tags.get("addr:suburb"):
        addr_parts.append(tags["addr:suburb"])
    if tags.get("addr:city"):
        addr_parts.append(tags["addr:city"])
    address = ", ".join(addr_parts)

    return {
        "osm_id": f"{el['type']}/{el['id']}",
        "nome": name,
        "endereco": address,
        "latitude": lat,
        "longitude": lon,
        "telefone": phone,
        "horario": hours,
        "website": website,
        "categoria_osm": category,
        "email": tags.get("email", "") or tags.get("contact:email", ""),
        "whatsapp": tags.get("contact:whatsapp", ""),
        "descricao": tags.get("description", ""),
        "operador": tags.get("operator", ""),
        "marca": tags.get("brand", ""),
        "tags_raw": json.dumps(tags, ensure_ascii=False),
        "fonte": "osm_overpass",
    }


def export_csv(path: Path, pois: List[Dict]) -> None:
    if not pois:
        return
    cols = [
        "osm_id", "nome", "endereco", "latitude", "longitude",
        "telefone", "horario", "website", "categoria_osm",
        "email", "whatsapp", "descricao", "operador", "marca", "fonte",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(pois)


def export_jsonl(path: Path, pois: List[Dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for poi in pois:
            f.write(json.dumps(poi, ensure_ascii=False) + "\n")


def export_geojson(path: Path, pois: List[Dict]) -> None:
    features = []
    for poi in pois:
        if not poi.get("latitude"):
            continue
        props = {k: v for k, v in poi.items() if k not in ("latitude", "longitude", "tags_raw")}
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {
                "type": "Point",
                "coordinates": [poi["longitude"], poi["latitude"]],
            },
        })
    geojson = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrai POIs do Urbanova via OSM/Overpass")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--geo-file", default="urbanova_referencias_geograficas.json")
    parser.add_argument("--use-bbox-fallback", action="store_true",
                        help="Usar bounding box ao invés de boundary administrativa")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("🗺️  Extraindo POIs do Urbanova via OpenStreetMap...")

    geo_data = json.loads(Path(args.geo_file).read_text(encoding="utf-8"))
    bbox = geo_data["envelope_operacional"]

    try:
        if args.use_bbox_fallback:
            raise RuntimeError("Forçando fallback por bbox")

        elements = get_urbanova_pois()
        print(f"  → {len(elements)} elementos encontrados (via boundary)")

        # Auto-fallback if boundary returns too few results
        if len(elements) < 5:
            print(f"  ⚠ Poucos resultados via boundary, complementando com bbox...")
            bbox_elements = get_bbox_pois(bbox)
            existing_ids = {(e.get("type"), e.get("id")) for e in elements}
            for el in bbox_elements:
                key = (el.get("type"), el.get("id"))
                if key not in existing_ids:
                    elements.append(el)
                    existing_ids.add(key)
            print(f"  → {len(elements)} elementos total (boundary + bbox)")
    except Exception as e:
        print(f"  ⚠ Boundary falhou ({e}), usando bounding box...")
        elements = get_bbox_pois(bbox)
        print(f"  → {len(elements)} elementos encontrados (via bbox)")

    # Convert to POIs
    pois = []
    seen = set()
    for el in elements:
        poi = element_to_poi(el)
        key = poi["osm_id"]
        if key not in seen:
            seen.add(key)
            pois.append(poi)

    # Separate named vs unnamed
    named_pois = [p for p in pois if p["nome"]]
    unnamed_pois = [p for p in pois if not p["nome"]]

    print(f"  → {len(named_pois)} POIs com nome")
    print(f"  → {len(unnamed_pois)} POIs sem nome (amenities genéricas)")

    # Export
    export_csv(out_dir / "pois_osm_urbanova.csv", named_pois)
    export_jsonl(out_dir / "pois_osm_urbanova.jsonl", pois)
    export_geojson(out_dir / "pois_osm_urbanova.geojson", named_pois)

    # Summary
    with_phone = sum(1 for p in named_pois if p["telefone"])
    with_hours = sum(1 for p in named_pois if p["horario"])
    with_site = sum(1 for p in named_pois if p["website"])
    total = len(named_pois) or 1

    summary = {
        "timestamp_unix": int(time.time()),
        "metodo": "osm_overpass_gratuito",
        "custo": "R$ 0,00",
        "total_elementos": len(pois),
        "pois_com_nome": len(named_pois),
        "pois_sem_nome": len(unnamed_pois),
        "cobertura": {
            "com_telefone_pct": round(100.0 * with_phone / total, 2),
            "com_horario_pct": round(100.0 * with_hours / total, 2),
            "com_website_pct": round(100.0 * with_site / total, 2),
        },
        "arquivos": [
            "output/pois_osm_urbanova.csv",
            "output/pois_osm_urbanova.jsonl",
            "output/pois_osm_urbanova.geojson",
        ],
    }
    (out_dir / "resumo_pois_osm.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✅ Extração OSM concluída!")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
