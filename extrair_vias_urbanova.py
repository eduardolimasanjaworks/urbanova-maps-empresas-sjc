#!/usr/bin/env python3
"""
Extrai logradouros do Urbanova via Overpass (OSM) com auditoria.

Saidas:
  - output/vias_urbanova.csv
  - output/vias_urbanova.geojson
  - output/vias_urbanova_auditoria.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple


OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def normalize_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("á", "a").replace("à", "a").replace("ã", "a").replace("â", "a")
    s = s.replace("é", "e").replace("ê", "e")
    s = s.replace("í", "i")
    s = s.replace("ó", "o").replace("ô", "o").replace("õ", "o")
    s = s.replace("ú", "u")
    s = s.replace("ç", "c")
    return s


def get_urbanova_area_id(timeout: int = 60) -> int:
    query = """
[out:json][timeout:60];
area["name"="São José dos Campos"]["admin_level"="8"]["boundary"="administrative"]->.sjc;
rel(area.sjc)["name"~"Urbanova"]["boundary"="administrative"];
out ids;
"""
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    rels = [e for e in payload.get("elements", []) if e.get("type") == "relation"]
    if not rels:
        raise RuntimeError("Nao encontrei relacao administrativa de Urbanova no OSM.")
    # Area ID para relation no Overpass: 3600000000 + relation_id
    rel_id = int(rels[0]["id"])
    return 3600000000 + rel_id


def query_roads(area_id: int, timeout: int = 90) -> Dict:
    query = f"""
[out:json][timeout:90];
area({area_id})->.a;
(
  way(area.a)["highway"]["name"];
);
out body;
>;
out skel qt;
"""
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_node_index(elements: List[Dict]) -> Dict[int, Tuple[float, float]]:
    idx: Dict[int, Tuple[float, float]] = {}
    for e in elements:
        if e.get("type") == "node" and "lat" in e and "lon" in e:
            idx[int(e["id"])] = (float(e["lat"]), float(e["lon"]))
    return idx


def first_point(nodes: List[int], node_idx: Dict[int, Tuple[float, float]]) -> Tuple[float, float]:
    for n in nodes:
        if n in node_idx:
            return node_idx[n]
    return (0.0, 0.0)


def road_type_from_name(name: str) -> str:
    n = normalize_text(name)
    if n.startswith("avenida") or n.startswith("av "):
        return "avenida"
    if n.startswith("rua") or n.startswith("r "):
        return "rua"
    if n.startswith("alameda"):
        return "alameda"
    if n.startswith("travessa"):
        return "travessa"
    return "logradouro"


def is_urbanova_variant(name: str) -> bool:
    n = normalize_text(name)
    return "urbanova" in n


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--delay-ms", type=int, default=200)
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    area_id = get_urbanova_area_id()
    time.sleep(max(args.delay_ms, 0) / 1000.0)
    data = query_roads(area_id)

    elements = data.get("elements", [])
    node_idx = build_node_index(elements)
    ways = [e for e in elements if e.get("type") == "way" and e.get("tags", {}).get("name")]

    rows = []
    audit = []
    dedup = {}

    for w in ways:
        tags = w.get("tags", {})
        name = tags.get("name", "").strip()
        highway = tags.get("highway", "")
        osm_id = int(w.get("id", 0))
        nodes = w.get("nodes", [])
        lat, lon = first_point(nodes, node_idx)
        typ = road_type_from_name(name)
        norm = normalize_text(name)
        key = (norm, highway)

        source_rule = "inside_urbanova_boundary"
        contains_urbanova = is_urbanova_variant(name)
        is_dup = key in dedup
        if not is_dup:
            dedup[key] = osm_id
            rows.append(
                {
                    "nome_via": name,
                    "tipo_via": typ,
                    "highway_tag": highway,
                    "osm_way_id": osm_id,
                    "lat_ref": lat,
                    "lon_ref": lon,
                    "contém_urbanova_no_nome": "sim" if contains_urbanova else "nao",
                    "fonte": "osm_overpass",
                }
            )

        audit.append(
            {
                "nome_via": name,
                "nome_normalizado": norm,
                "highway_tag": highway,
                "osm_way_id": osm_id,
                "lat_ref": lat,
                "lon_ref": lon,
                "regra_inclusao": source_rule,
                "duplicado": "sim" if is_dup else "nao",
                "osm_way_id_canonico": dedup[key],
            }
        )

    rows.sort(key=lambda r: normalize_text(r["nome_via"]))
    audit.sort(key=lambda r: (r["nome_normalizado"], r["osm_way_id"]))

    csv_path = out_dir / "vias_urbanova.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        cols = [
            "nome_via",
            "tipo_via",
            "highway_tag",
            "osm_way_id",
            "lat_ref",
            "lon_ref",
            "contém_urbanova_no_nome",
            "fonte",
        ]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    audit_path = out_dir / "vias_urbanova_auditoria.csv"
    with audit_path.open("w", newline="", encoding="utf-8") as f:
        cols = [
            "nome_via",
            "nome_normalizado",
            "highway_tag",
            "osm_way_id",
            "lat_ref",
            "lon_ref",
            "regra_inclusao",
            "duplicado",
            "osm_way_id_canonico",
        ]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(audit)

    features = []
    for r in rows:
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "nome_via": r["nome_via"],
                    "tipo_via": r["tipo_via"],
                    "highway_tag": r["highway_tag"],
                    "osm_way_id": r["osm_way_id"],
                },
                "geometry": {"type": "Point", "coordinates": [r["lon_ref"], r["lat_ref"]]},
            }
        )
    geojson = {"type": "FeatureCollection", "features": features}
    (out_dir / "vias_urbanova.geojson").write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "vias_unicas": len(rows),
                "vias_auditoria_total": len(audit),
                "arquivos": [
                    str(csv_path),
                    str(audit_path),
                    str(out_dir / "vias_urbanova.geojson"),
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

