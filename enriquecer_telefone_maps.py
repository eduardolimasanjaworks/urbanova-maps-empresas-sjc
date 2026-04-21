#!/usr/bin/env python3
"""
Para cada linha de um CSV (ex.: saída da BrasilAPI), tenta obter telefone no Google Maps
buscando o primeiro resultado e abrindo a ficha.

Não há API pública que confirme WhatsApp; geramos link wa.me a partir do número (heurística BR).

Uso:
  python3 enriquecer_telefone_maps.py -i output/cnpj_passo1_brasilapi.csv -o output/cnpj_passo2_maps.csv \\
      --lista-nomes listaatualcnpjtowhatsapp.txt
  python3 enriquecer_telefone_maps.py -i ... --only-missing
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional


def only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def wa_link_from_br_phone(raw: str) -> str:
    d = only_digits(raw)
    if not d:
        return ""
    if d.startswith("55") and len(d) >= 12:
        return f"https://wa.me/{d}"
    if len(d) in (10, 11):
        return f"https://wa.me/55{d}"
    return ""


def build_query(row: Dict[str, str], nome_lista: str) -> str:
    nome = (row.get("razao_social") or "").strip()
    if not nome:
        nome = nome_lista.strip()
    if not nome:
        nome = (row.get("nome_fantasia") or "").strip()
    mun = (row.get("municipio") or "").strip()
    uf = (row.get("uf") or "").strip()
    parts: List[str] = []
    if nome:
        parts.append(nome)
    if mun:
        parts.append(mun)
    if uf:
        parts.append(uf)
    if len(parts) < 2 and nome_lista:
        parts = [nome_lista.strip(), "Brasil"]
    return " ".join(parts)


def build_query_fallback(row: Dict[str, str], nome_lista: str) -> str:
    """Segunda tentativa: nome da lista + cidade/UF (costuma casar melhor com o Maps)."""
    nl = nome_lista.strip()
    mun = (row.get("municipio") or "").strip()
    uf = (row.get("uf") or "").strip()
    if nl and mun and uf:
        return f"{nl} {mun} {uf}"
    if nl and mun:
        return f"{nl} {mun}"
    nome = (row.get("razao_social") or row.get("nome_fantasia") or "").strip()
    if nome and mun:
        return f"{nome} {mun} {uf}".strip()
    return nl + " telefone" if nl else ""


def scrape_phone_first_result(
    query: str,
    headless: bool = True,
    timeout_ms: int = 28000,
) -> tuple[str, str]:
    from playwright.sync_api import sync_playwright

    q = urllib.parse.quote(query)
    url = f"https://www.google.com/maps/search/{q}"
    phone = ""
    final_url = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            time.sleep(2.5)
            try:
                accept = page.locator("button:has-text('Aceitar'), button:has-text('Accept')")
                if accept.count() > 0:
                    accept.first.click(timeout=3000)
                    time.sleep(1)
            except Exception:
                pass

            try:
                page.wait_for_selector("a.hfpxzc", timeout=12000)
            except Exception:
                browser.close()
                return "", ""

            link = page.locator("a.hfpxzc").first
            href = link.get_attribute("href") or ""
            final_url = href
            link.click(timeout=10000)
            time.sleep(3.2)

            try:
                phone_el = page.locator(
                    "[data-tooltip='Copiar o número de telefone'] div.fontBodyMedium, "
                    "[data-item-id^='phone'] div.fontBodyMedium"
                )
                if phone_el.count() > 0:
                    phone = phone_el.first.inner_text().strip()
            except Exception:
                pass
            if not phone:
                try:
                    tel_a = page.locator('a[href^="tel:"]').first
                    if tel_a.count() > 0:
                        href_tel = tel_a.get_attribute("href") or ""
                        phone = href_tel.replace("tel:", "").strip()
                except Exception:
                    pass
            if not phone:
                try:
                    alt = page.locator("button[data-item-id='phone'], button[data-item-id^='phone']")
                    if alt.count() > 0:
                        phone = alt.first.inner_text().strip()
                except Exception:
                    pass
            if not phone:
                try:
                    any_phone = page.locator("[data-item-id*='phone']")
                    if any_phone.count() > 0:
                        phone = any_phone.first.inner_text().strip()
                except Exception:
                    pass
        except Exception as e:
            print(f"    ⚠ Maps erro: {e}", file=sys.stderr)
        finally:
            browser.close()

    return phone, final_url


def load_nome_lista(path: Optional[Path]) -> Dict[str, str]:
    if not path or not path.exists():
        return {}
    out: Dict[str, str] = {}
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        r = csv.DictReader(f, dialect=dialect)
        if not r.fieldnames:
            return out
        low = {h.lower().strip(): h for h in r.fieldnames if h}
        k_cnpj = low.get("cnpj") or low.get("documento")
        k_nome = low.get("nome") or low.get("razao_social")
        if not k_cnpj:
            return out
        for row in r:
            raw = (row.get(k_cnpj) or "").strip()
            d = only_digits(raw)
            if len(d) != 14:
                continue
            nome = (row.get(k_nome) or "").strip() if k_nome else ""
            out[d] = nome
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Telefone via Google Maps (primeiro resultado).")
    ap.add_argument("-i", "--input", type=Path, required=True)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--lista-nomes", type=Path, default=None)
    ap.add_argument(
        "--only-missing",
        action="store_true",
        help="Só linhas sem telefone_1 na Receita",
    )
    ap.add_argument(
        "--only-still-empty",
        action="store_true",
        help="Só linhas sem telefone_1 e sem telefone_maps (reprocessar falhas)",
    )
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--no-headless", action="store_true")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"Não encontrado: {args.input}", file=sys.stderr)
        return 1

    nomes = load_nome_lista(args.lista_nomes)

    with args.input.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    extra_cols = ["telefone_maps", "maps_url", "whatsapp_maps", "query_usada"]
    base_fields = list(rows[0].keys()) if rows else []
    fieldnames = base_fields + [c for c in extra_cols if c not in base_fields]

    out_rows: List[Dict[str, Any]] = []
    n_maps = 0

    for i, row in enumerate(rows):
        cnpj = only_digits(row.get("cnpj", ""))
        nome_lista = nomes.get(cnpj, "")
        tel1 = (row.get("telefone_1") or "").strip()
        tel_maps_prev = (row.get("telefone_maps") or "").strip()

        if args.only_still_empty and (tel1 or tel_maps_prev):
            out_rows.append(dict(row))
            continue

        if args.only_missing and tel1:
            out_rows.append(dict(row))
            continue

        q = build_query(row, nome_lista)
        n_maps += 1
        print(f"  [{n_maps}] {cnpj} → {q[:72]}...")
        phone, gurl = scrape_phone_first_result(q, headless=not args.no_headless)
        q_used = q
        if not phone.strip():
            q2 = build_query_fallback(row, nome_lista)
            if q2 and q2 != q:
                print(f"       ↳ retry: {q2[:72]}...")
                time.sleep(1.0)
                phone, gurl = scrape_phone_first_result(q2, headless=not args.no_headless)
                q_used = f"{q} | ALT:{q2}"
        wa = wa_link_from_br_phone(phone)
        nr = dict(row)
        nr["telefone_maps"] = phone
        nr["maps_url"] = gurl
        nr["whatsapp_maps"] = wa
        nr["query_usada"] = q_used
        out_rows.append(nr)

        if i < len(rows) - 1 and args.delay > 0:
            time.sleep(args.delay)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in out_rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

    print(f"Salvo: {args.output.resolve()} ({len(out_rows)} linhas, {n_maps} buscas Maps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
