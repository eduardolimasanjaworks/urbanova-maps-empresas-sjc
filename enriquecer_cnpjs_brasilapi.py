#!/usr/bin/env python3
"""
Consulta cadastro de CNPJs na BrasilAPI (gratuita, sem chave de API).

Entrada: arquivo texto (um CNPJ por linha) ou CSV com coluna "cnpj" / "CNPJ".

Saída: CSV com razão social, endereço, telefones (ddd_telefone_1/2, fax), e-mail,
situação cadastral, CNAE, etc.

Uso:
  python3 enriquecer_cnpjs_brasilapi.py cnpjs.txt -o resultado.csv
  python3 enriquecer_cnpjs_brasilapi.py planilha.csv -o resultado.csv --delay 1.0

Limite: a BrasilAPI pode aplicar rate limit; use --delay maior se receber HTTP 429.
Os telefone vêm da base pública da Receita (muitos CNPJs vêm vazios ou desatualizados).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

BRASILAPI_URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
DEFAULT_DELAY_S = 0.85
USER_AGENT = "urbanova-cnpj-enricher/1.0 (python urllib; uso moderado)"


def normalize_cnpj(raw: str) -> Optional[str]:
    d = re.sub(r"\D", "", raw.strip())
    if len(d) != 14:
        return None
    return d


def read_cnpjs_from_txt(path: Path) -> List[str]:
    out: List[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        n = normalize_cnpj(line)
        if n:
            out.append(n)
    return out


def read_cnpjs_from_csv(path: Path) -> List[str]:
    rows: List[str] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        if not reader.fieldnames:
            return read_cnpjs_from_txt(path)
        lowered = {h.lower().strip(): h for h in reader.fieldnames if h}
        key = None
        for cand in ("cnpj", "cnpj_base", "documento"):
            if cand in lowered:
                key = lowered[cand]
                break
        if not key:
            # primeira coluna como fallback
            key = reader.fieldnames[0]
        for row in reader:
            if not row:
                continue
            val = (row.get(key) or "").strip()
            n = normalize_cnpj(val)
            if n:
                rows.append(n)
    return rows


def read_cnpjs(path: Path) -> List[str]:
    suf = path.suffix.lower()
    if suf == ".csv":
        ids = read_cnpjs_from_csv(path)
    else:
        ids = read_cnpjs_from_txt(path)
    seen: set = set()
    unique: List[str] = []
    for c in ids:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def fetch_cnpj(cnpj: str, timeout: int = 45) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    url = BRASILAPI_URL.format(cnpj=cnpj)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body), None
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        if e.code == 404:
            return None, "nao_encontrado"
        if e.code == 429:
            return None, "rate_limit"
        return None, f"http_{e.code}: {err_body}"
    except urllib.error.URLError as e:
        return None, f"url_erro: {e.reason}"
    except json.JSONDecodeError as e:
        return None, f"json_invalido: {e}"
    except Exception as e:
        return None, str(e)


CSV_COLUMNS = [
    "cnpj",
    "erro",
    "razao_social",
    "nome_fantasia",
    "situacao_cadastral",
    "descricao_situacao_cadastral",
    "data_situacao_cadastral",
    "data_inicio_atividade",
    "telefone_1",
    "telefone_2",
    "fax",
    "email",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "municipio",
    "uf",
    "cep",
    "codigo_municipio_ibge",
    "cnae_fiscal",
    "cnae_fiscal_descricao",
    "natureza_juridica",
    "porte",
    "capital_social",
    "cnaes_secundarios_resumo",
]


def flatten_record(cnpj: str, data: Optional[Dict[str, Any]], erro: Optional[str]) -> Dict[str, Any]:
    row: Dict[str, Any] = {k: "" for k in CSV_COLUMNS}
    row["cnpj"] = cnpj
    row["erro"] = erro or ""
    if not data:
        return row
    sec = data.get("cnaes_secundarios") or []
    parts: List[str] = []
    if isinstance(sec, list):
        for item in sec[:20]:
            if isinstance(item, dict):
                c = item.get("codigo")
                d = (item.get("descricao") or "")[:60]
                parts.append(f"{c}:{d}" if d else str(c))
    row["cnpj"] = str(data.get("cnpj") or cnpj)
    row["razao_social"] = data.get("razao_social") or ""
    row["nome_fantasia"] = data.get("nome_fantasia") or ""
    row["situacao_cadastral"] = data.get("situacao_cadastral") if data.get("situacao_cadastral") is not None else ""
    row["descricao_situacao_cadastral"] = data.get("descricao_situacao_cadastral") or ""
    row["data_situacao_cadastral"] = data.get("data_situacao_cadastral") or ""
    row["data_inicio_atividade"] = data.get("data_inicio_atividade") or ""
    row["telefone_1"] = data.get("ddd_telefone_1") or ""
    row["telefone_2"] = data.get("ddd_telefone_2") or ""
    row["fax"] = data.get("ddd_fax") or ""
    row["email"] = data.get("email") or ""
    row["logradouro"] = data.get("logradouro") or ""
    row["numero"] = data.get("numero") or ""
    row["complemento"] = data.get("complemento") or ""
    row["bairro"] = data.get("bairro") or ""
    row["municipio"] = data.get("municipio") or ""
    row["uf"] = data.get("uf") or ""
    row["cep"] = data.get("cep") or ""
    row["codigo_municipio_ibge"] = data.get("codigo_municipio_ibge") if data.get("codigo_municipio_ibge") is not None else ""
    row["cnae_fiscal"] = data.get("cnae_fiscal") if data.get("cnae_fiscal") is not None else ""
    row["cnae_fiscal_descricao"] = data.get("cnae_fiscal_descricao") or ""
    row["natureza_juridica"] = data.get("natureza_juridica") or ""
    row["porte"] = data.get("porte") or ""
    cs = data.get("capital_social")
    row["capital_social"] = cs if cs is not None else ""
    row["cnaes_secundarios_resumo"] = " | ".join(parts)
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description="Enriquece CNPJs via BrasilAPI (gratuito).")
    ap.add_argument("entrada", type=Path, help="Arquivo .txt (um CNPJ por linha) ou .csv com coluna cnpj")
    ap.add_argument("-o", "--output", type=Path, required=True, help="CSV de saída")
    ap.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_S,
        help=f"Pausa entre requisições em segundos (padrão {DEFAULT_DELAY_S})",
    )
    ap.add_argument("--max-retries", type=int, default=4, help="Tentativas em caso de rate limit (429)")
    args = ap.parse_args()

    if not args.entrada.exists():
        print(f"Arquivo não encontrado: {args.entrada}", file=sys.stderr)
        return 1

    cnpjs = read_cnpjs(args.entrada)
    if not cnpjs:
        print("Nenhum CNPJ válido (14 dígitos) encontrado.", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    total = len(cnpjs)
    print(f"Consultando {total} CNPJ(s) na BrasilAPI (delay {args.delay}s)...")

    with args.output.open("w", encoding="utf-8", newline="") as fout:
        writer = csv.DictWriter(fout, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()

        for i, cnpj in enumerate(cnpjs, 1):
            erro: Optional[str] = None
            data: Optional[Dict[str, Any]] = None
            retries = 0
            while True:
                data, erro = fetch_cnpj(cnpj)
                if erro == "rate_limit" and retries < args.max_retries:
                    wait = (2**retries) * args.delay + 1.0
                    print(f"  429 rate limit — aguardando {wait:.1f}s e tentando de novo ({cnpj})...")
                    time.sleep(wait)
                    retries += 1
                    continue
                break

            row = flatten_record(cnpj, data, erro)
            writer.writerow(row)
            nome = (row.get("razao_social") or "")[:50]
            print(f"  [{i}/{total}] {cnpj} {nome} {'OK' if data else erro}")

            if i < total and args.delay > 0:
                time.sleep(args.delay)

    print(f"Salvo: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
