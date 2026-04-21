#!/usr/bin/env python3
"""
Enriquece telefone quando o primeiro resultado do Maps falhou: abre até N resultados
da busca, compara o título (h1) com razão social / nome fantasia / nome da lista e
escolhe o telefone do melhor match.

Uso:
  python3 enriquecer_maps_varios_resultados.py -i output/cnpj_FINAL_whatsapp.csv \\
      -o output/cnpj_FINAL_whatsapp_v2.csv --lista-nomes listaatualcnpjtowhatsapp.txt --max 8
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import urllib.parse
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from enriquecer_telefone_maps import load_nome_lista, only_digits, wa_link_from_br_phone


def _tokens(s: str) -> set:
    s = re.sub(r"[^a-z0-9\s]", " ", (s or "").lower())
    return {w for w in s.split() if len(w) > 2}


def score_title(h1: str, names: List[str]) -> float:
    h1 = (h1 or "").strip()
    if not h1:
        return 0.0
    best = 0.0
    t1 = _tokens(h1)
    for n in names:
        if not (n or "").strip():
            continue
        n = n.strip()
        r = SequenceMatcher(None, h1.lower(), n.lower()).ratio()
        t2 = _tokens(n)
        jacc = len(t1 & t2) / max(len(t1 | t2), 1) if (t1 or t2) else 0.0
        best = max(best, 0.55 * r + 0.45 * jacc)
    return best


def extract_phone_and_title(page) -> Tuple[str, str]:
    phone = ""
    title = ""
    try:
        h = page.locator("h1.DUwDvf")
        if h.count() > 0:
            title = h.first.inner_text().strip()
    except Exception:
        pass
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
                phone = (tel_a.get_attribute("href") or "").replace("tel:", "").strip()
        except Exception:
            pass
    if not phone:
        try:
            alt = page.locator("button[data-item-id='phone'], button[data-item-id^='phone']")
            if alt.count() > 0:
                phone = alt.first.inner_text().strip()
        except Exception:
            pass
    return phone, title


def build_queries(row: Dict[str, str], nome_lista: str) -> List[str]:
    mun = (row.get("municipio") or "").strip()
    uf = (row.get("uf") or "").strip()
    suf = " ".join(x for x in (mun, uf) if x).strip()

    def q(*parts: str) -> str:
        base = " ".join(p for p in parts if p).strip()
        if suf and base and suf not in base:
            return f"{base} {suf}".strip()
        return base or suf

    out: List[str] = []
    seen: set = set()

    def add(a: str) -> None:
        a = a.strip()
        if len(a) < 4:
            return
        if a not in seen:
            seen.add(a)
            out.append(a)

    rz = (row.get("razao_social") or "").strip()
    nf = (row.get("nome_fantasia") or "").strip()
    nl = (nome_lista or "").strip()

    add(q(rz))
    add(q(nf))
    add(q(nl))
    if mun:
        add(q(nf, mun))
        add(q(nl, mun))
    if not rz and not nf:
        add(q(nl, "Brasil"))
    return out[:6]


def scrape_best_phone(
    queries: List[str],
    names_for_match: List[str],
    max_results: int = 8,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> Tuple[str, str, str, float]:
    """
    Retorna (telefone, maps_url, query_usada, score).
    """
    from playwright.sync_api import sync_playwright

    best_phone = ""
    best_url = ""
    best_q = ""
    best_sc = 0.0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        for query in queries:
            if best_phone and best_sc >= 0.42:
                break
            q = urllib.parse.quote(query)
            url = f"https://www.google.com/maps/search/{q}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                time.sleep(2.8)
                try:
                    accept = page.locator("button:has-text('Aceitar'), button:has-text('Accept')")
                    if accept.count() > 0:
                        accept.first.click(timeout=3000)
                        time.sleep(1)
                except Exception:
                    pass

                try:
                    page.wait_for_selector("a.hfpxzc", timeout=14000)
                except Exception:
                    continue

                feed = page.locator("[role='feed']").first
                if feed.count():
                    for _ in range(6):
                        try:
                            feed.evaluate("el => el.scrollTop = el.scrollHeight")
                        except Exception:
                            break
                        time.sleep(0.45)

                links = page.locator("a.hfpxzc")
                n = min(links.count(), max_results)
                hrefs: List[str] = []
                for i in range(n):
                    try:
                        h = links.nth(i).get_attribute("href") or ""
                        if h:
                            hrefs.append(h)
                    except Exception:
                        continue

                for href in hrefs:
                    try:
                        page.goto(href, wait_until="domcontentloaded", timeout=timeout_ms)
                        time.sleep(2.2)
                        phone, title = extract_phone_and_title(page)
                        sc = score_title(title, names_for_match)
                        if phone:
                            if sc > best_sc or (not best_phone and phone):
                                best_sc = sc
                                best_phone = phone
                                best_url = page.url
                                best_q = query
                            if sc >= 0.5 and phone:
                                browser.close()
                                return best_phone, best_url, best_q, best_sc
                    except Exception as e:
                        print(f"    aviso lugar: {e}", file=sys.stderr)
                        continue
            except Exception as e:
                print(f"  ⚠ query '{query[:50]}...': {e}", file=sys.stderr)
                continue

        browser.close()

    return best_phone, best_url, best_q, best_sc


def main() -> int:
    ap = argparse.ArgumentParser(description="Maps: vários resultados + melhor match de nome.")
    ap.add_argument("-i", "--input", type=Path, required=True)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--lista-nomes", type=Path, default=None)
    ap.add_argument("--max", type=int, default=8, help="Máx. resultados por busca")
    ap.add_argument("--delay", type=float, default=1.0, help="Pausa entre empresas (s)")
    ap.add_argument("--no-headless", action="store_true")
    args = ap.parse_args()

    nomes = load_nome_lista(args.lista_nomes)

    with args.input.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    base_fields = list(rows[0].keys()) if rows else []
    extra = ["telefone_maps_v2", "maps_url_v2", "whatsapp_maps_v2", "query_maps_v2", "score_match_maps"]
    fieldnames = base_fields + [c for c in extra if c not in base_fields]

    out: List[Dict[str, str]] = []
    n_run = 0

    for row in rows:
        tf = (row.get("telefone_final") or "").strip()
        t1 = (row.get("telefone_1") or "").strip()
        tm = (row.get("telefone_maps") or "").strip()

        cnpj = only_digits(row.get("cnpj", ""))
        nome_lista = nomes.get(cnpj, "")

        if tf or t1 or tm:
            nr = dict(row)
            for c in extra:
                nr[c] = ""
            out.append(nr)
            continue

        n_run += 1
        names = [
            row.get("razao_social") or "",
            row.get("nome_fantasia") or "",
            nome_lista,
        ]
        names = [x.strip() for x in names if x.strip()]
        queries = build_queries(row, nome_lista)
        if not queries:
            queries = [nome_lista + " Brasil"] if nome_lista else []

        print(f"  [{n_run}] {cnpj} queries: {queries[:2]}...")

        phone, gurl, used_q, sc = scrape_best_phone(
            queries,
            names,
            max_results=args.max,
            headless=not args.no_headless,
        )

        nr = dict(row)
        nr["telefone_maps_v2"] = phone
        nr["maps_url_v2"] = gurl
        nr["whatsapp_maps_v2"] = wa_link_from_br_phone(phone) if phone else ""
        nr["query_maps_v2"] = used_q
        nr["score_match_maps"] = f"{sc:.3f}"
        for c in extra:
            if c not in nr:
                nr[c] = ""
        out.append(nr)

        if args.delay > 0:
            time.sleep(args.delay)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, "") for k in fieldnames})

    print(f"Processadas {n_run} linha(s) sem telefone. Salvo: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
