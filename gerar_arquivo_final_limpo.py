#!/usr/bin/env python3
"""
Gera CSV minimalista com título conceitual no nome do arquivo:
  output/ARQUIVO FINAL ENRIQUECIDO.csv

Colunas: nome, telefone, validacao_ddi_e_ddd
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def load_nomes_lista(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        r = csv.DictReader(f, dialect=dialect)
        low = {h.lower().strip(): h for h in (r.fieldnames or []) if h}
        k_cnpj = low.get("cnpj")
        k_nome = low.get("nome")
        if not k_cnpj:
            return out
        for row in r:
            c = only_digits(row.get(k_cnpj) or "")
            if len(c) != 14:
                continue
            nome = (row.get(k_nome) or "").strip() if k_nome else ""
            out[c] = nome
    return out


def parse_telefone_br(raw: str) -> Optional[Tuple[str, str, str, str]]:
    d = only_digits(raw)
    if not d:
        return None

    if d.startswith("55") and len(d) >= 12:
        national = d[2:]
    else:
        national = d

    if len(national) not in (10, 11):
        if len(national) > 11:
            national = national[-11:]
        if len(national) not in (10, 11):
            return None

    ddd = national[:2]
    local = national[2:]
    if len(local) not in (8, 9):
        return None

    ddi = "55"
    if len(local) == 9:
        part = f"{local[:5]}-{local[5:]}"
    else:
        part = f"{local[:4]}-{local[4:]}"

    display = f"+{ddi} ({ddd}) {part}"
    return ddi, ddd, local, display


def nome_para_linha(row: Dict[str, str], nome_lista: str) -> str:
    nl = (nome_lista or "").strip()
    rz = (row.get("razao_social") or "").strip()
    if nl:
        return nl
    if rz:
        return rz
    return (row.get("nome_fantasia") or "").strip() or "— sem nome —"


def main() -> int:
    base = Path(__file__).resolve().parent
    inp = base / "output" / "cnpj_FINAL_whatsapp.csv"
    lista = base / "listaatualcnpjtowhatsapp.txt"
    out = base / "output" / "ARQUIVO FINAL ENRIQUECIDO.csv"

    if not inp.exists():
        print(f"Não encontrado: {inp}", file=sys.stderr)
        return 1

    nomes = load_nomes_lista(lista) if lista.exists() else {}

    with inp.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    fieldnames = ["nome", "telefone", "validacao_ddi_e_ddd"]
    linhas: List[Dict[str, str]] = []

    for row in rows:
        cnpj = only_digits(row.get("cnpj", ""))
        nome = nome_para_linha(row, nomes.get(cnpj, ""))
        tel_raw = (row.get("telefone_final") or "").strip()
        if not tel_raw:
            tel_raw = (
                (row.get("telefone_1") or "").strip()
                or (row.get("telefone_maps_v2") or "").strip()
                or (row.get("telefone_maps") or "").strip()
            )

        parsed = parse_telefone_br(tel_raw) if tel_raw else None

        if parsed:
            _, ddd, _, display = parsed
            tel = display
            val = f"Sim — DDI 55 (Brasil) e DDD {ddd} identificados no número."
        else:
            tel = ""
            if not tel_raw:
                val = "Não — sem telefone; DDI/DDD não aplicáveis."
            else:
                val = f"Revisar — bruto: {tel_raw[:40]}"

        linhas.append({"nome": nome, "telefone": tel, "validacao_ddi_e_ddd": val})

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(linhas)

    com = sum(1 for x in linhas if x["telefone"])
    print(f"Salvo: {out}")
    print(f"Total: {len(linhas)} linhas | com telefone (DDI 55 + DDD): {com} | sem telefone: {len(linhas) - com}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
