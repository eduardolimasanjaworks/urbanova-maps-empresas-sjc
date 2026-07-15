#!/usr/bin/env python3
"""Enriquece telefones de registros já descobertos sem refazer buscas."""

import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper_google_maps import Business, export_csv, generate_place_id


def load_csv(path: Path) -> list[Business]:
    if not path.exists():
        return []
    rows = []
    fields = set(Business.__dataclass_fields__.keys())
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            data = {k: row.get(k, "") for k in fields}
            for k in ("latitude", "longitude"):
                try:
                    data[k] = float(data[k] or 0)
                except ValueError:
                    data[k] = 0.0
            rows.append(Business(**data))
    return rows


def enrich_phones(businesses: list[Business], limit: int = 0) -> list[Business]:
    from playwright.sync_api import sync_playwright

    targets = [b for b in businesses if not b.telefone and b.google_maps_url]
    if limit > 0:
        targets = targets[:limit]

    print(f"Enriquecendo {len(targets)} registros sem telefone...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=20)
        page = browser.new_page(
            viewport={"width": 1280, "height": 900},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
        )
        for i, biz in enumerate(targets, 1):
            try:
                if i % 10 == 0 or i == 1:
                    print(f"  {i}/{len(targets)}")
                page.goto(biz.google_maps_url, wait_until="domcontentloaded", timeout=25000)
                time.sleep(1.5)
                phone_el = page.locator(
                    "[data-tooltip='Copiar o número de telefone'] div.fontBodyMedium, "
                    "[data-item-id^='phone'] div.fontBodyMedium"
                )
                if phone_el.count() > 0:
                    biz.telefone = phone_el.first.inner_text().strip()
                addr_btn = page.locator(
                    "[data-item-id='address'] div.fontBodyMedium, button[data-item-id='address'] div.fontBodyMedium"
                )
                if addr_btn.count() > 0:
                    biz.endereco = addr_btn.first.inner_text().strip()
                web_el = page.locator(
                    "[data-tooltip='Abrir o site'] div.fontBodyMedium, [data-item-id='authority'] div.fontBodyMedium"
                )
                if web_el.count() > 0:
                    biz.website = web_el.first.inner_text().strip()
                biz.place_id = generate_place_id(biz.nome, biz.endereco or biz.google_maps_url)
            except Exception as e:
                print(f"  erro {biz.nome[:40]}: {e}")
        browser.close()
    return businesses


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    inp = Path(args.input)
    out = Path(args.output)
    rows = load_csv(inp)
    rows = enrich_phones(rows, limit=args.limit)
    export_csv(out, rows)
    phones = sum(1 for b in rows if b.telefone)
    print(f"Salvo {out}: {len(rows)} registros, {phones} com telefone")


if __name__ == "__main__":
    main()
