#!/usr/bin/env python3
"""
Une telefone da Receita (telefone_1/2) com telefone_maps e gera whatsapp_sugerido (link wa.me).

Uso:
  python3 consolidar_cnpj_whatsapp.py -i output/cnpj_passo3_retry.csv -o output/cnpj_FINAL.csv
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


def only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def wa_link(raw: str) -> str:
    d = only_digits(raw)
    if not d:
        return ""
    if d.startswith("55") and len(d) >= 12:
        return f"https://wa.me/{d}"
    if len(d) in (10, 11):
        return f"https://wa.me/55{d}"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", type=Path, required=True)
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()

    with args.input.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    extras = ["telefone_final", "fonte_telefone", "whatsapp_sugerido"]
    fields = list(rows[0].keys()) if rows else []
    for e in extras:
        if e not in fields:
            fields.append(e)

    out = []
    for r in rows:
        t1 = (r.get("telefone_1") or "").strip()
        t2 = (r.get("telefone_2") or "").strip()
        tm = (r.get("telefone_maps") or "").strip()
        tm2 = (r.get("telefone_maps_v2") or "").strip()
        tw = (r.get("telefone_web") or "").strip()
        final = t1 or t2 or tm or tm2 or tw
        fonte = ""
        if t1:
            fonte = "receita_telefone_1"
        elif t2:
            fonte = "receita_telefone_2"
        elif tm:
            fonte = "google_maps"
        elif tm2:
            fonte = "google_maps_multi_resultado"
        elif tw:
            fonte = "busca_web"
        nr = dict(r)
        nr["telefone_final"] = final
        nr["fonte_telefone"] = fonte
        nr["whatsapp_sugerido"] = wa_link(final) if final else ""
        out.append(nr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, "") for k in fields})

    n_tel = sum(1 for r in out if r["telefone_final"])
    n_wa = sum(1 for r in out if r["whatsapp_sugerido"])
    print(f"OK: {len(out)} linhas | com telefone: {n_tel} | com link wa.me: {n_wa}")
    print(f"Salvo: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
