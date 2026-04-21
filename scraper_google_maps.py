#!/usr/bin/env python3
"""
Scraper gratuito de Google Maps via Playwright (headless browser).
Substitui a Google Places API paga.

Extrai: nome, endereço, telefone, horário, website, avaliação,
        quantidade de reviews, categoria, coordenadas, Google Maps URL.

Uso:
  python scraper_google_maps.py
  python scraper_google_maps.py --headless --max-scroll 80
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def buscas_config_default_path() -> Path:
    return Path(__file__).resolve().parent / "config" / "buscas_urbanova.json"


def _as_str_list(value: Any, *, allow_empty: bool = False) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            s_raw = "" if item is None else str(item)
            s = s_raw.strip()
            if s:
                out.append(s)
            elif allow_empty:
                # "" pode ser significativo (ex.: bairros=[""] => busca na cidade toda)
                out.append("")
        return out
    s = str(value).strip()
    return [s] if s else []


def load_buscas_arquivo(path: Path) -> Tuple[List[str], List[str], bool, List[str]]:
    """Lê JSON de buscas: bairros, cidades, flag amplas, segmentos.

    Compatível com o formato antigo:
      - "bairro": "Urbanova"
      - "cidade": "São José dos Campos"

    E com o formato novo (lista):
      - "bairros": ["Urbanova", "Jardim Aquarius"]
      - "cidades": ["São José dos Campos", "Taubaté"]
    """
    if not path.exists():
        raise SystemExit(
            f"Arquivo de buscas não encontrado: {path}\n"
            "Crie com: python3 gerenciar_buscas.py init\n"
            "Ou edite o JSON manualmente (chave \"segmentos\": lista de termos)."
        )
    data: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))

    bairros = _as_str_list(data.get("bairros"), allow_empty=True)
    if not bairros:
        bairros = _as_str_list(data.get("bairro", "Urbanova"), allow_empty=True)

    cidades = _as_str_list(data.get("cidades"))
    if not cidades:
        cidades = _as_str_list(data.get("cidade", "São José dos Campos"))

    amplas = bool(data.get("incluir_buscas_amplas", True))
    raw = data.get("segmentos", [])
    if not isinstance(raw, list):
        raise SystemExit(f'"{path}" inválido: "segmentos" deve ser uma lista.')
    segmentos: List[str] = []
    for item in raw:
        s = str(item).strip()
        if s:
            segmentos.append(s)
    return bairros, cidades, amplas, segmentos


@dataclass
class Business:
    place_id: str = ""
    nome: str = ""
    endereco: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    telefone: str = ""
    horario: str = ""
    website: str = ""
    avaliacao: str = ""
    total_reviews: str = ""
    categoria: str = ""
    status_negocio: str = ""
    google_maps_url: str = ""
    fonte: str = ""


def generate_place_id(name: str, address: str) -> str:
    raw = f"{name.strip().lower()}|{address.strip().lower()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def extract_coords_from_url(url: str) -> Tuple[float, float]:
    """Extract lat/lon from Google Maps URL patterns."""
    # Pattern: @-23.1234,-45.5678,17z or !3d-23.1234!4d-45.5678
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", url)
    if m:
        return float(m.group(1)), float(m.group(2))
    return 0.0, 0.0


def scrape_google_maps(
    queries: List[str],
    headless: bool = True,
    max_scroll: int = 60,
    slow_mo: int = 50,
    scroll_pause_ms: int = 1500,
    details_limit: Optional[int] = None,
) -> List[Business]:
    """
    Scrape Google Maps search results using Playwright.
    Returns list of Business objects.
    """
    from playwright.sync_api import sync_playwright

    all_businesses: Dict[str, Business] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
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

        for query_idx, query in enumerate(queries):
            print(f"\n[{query_idx+1}/{len(queries)}] Buscando: {query}")
            search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"

            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)

                # Accept cookies if prompted
                try:
                    accept_btn = page.locator("button:has-text('Aceitar'), button:has-text('Accept')")
                    if accept_btn.count() > 0:
                        accept_btn.first.click()
                        time.sleep(1)
                except Exception:
                    pass

                # Wait for results panel
                try:
                    page.wait_for_selector("[role='feed'], div.m6QErb", timeout=10000)
                except Exception:
                    print(f"  ⚠ Nenhum feed de resultados encontrado para: {query}")
                    continue

                # Scroll to load all results
                feed = page.locator("[role='feed']").first
                if not feed.count():
                    feed = page.locator("div.m6QErb").first

                prev_count = 0
                stale_rounds = 0
                for scroll_i in range(max_scroll):
                    try:
                        feed.evaluate("el => el.scrollTop = el.scrollHeight")
                    except Exception:
                        break
                    time.sleep(scroll_pause_ms / 1000.0)

                    # Check if we hit "end of results"
                    end_text = page.locator("span.HlvSq, p.fontBodyMedium:has-text('final')")
                    if end_text.count() > 0:
                        break

                    items = page.locator("[role='feed'] > div > div > a, div.m6QErb > div > div > a")
                    current_count = items.count()
                    if current_count == prev_count:
                        stale_rounds += 1
                        if stale_rounds >= 4:
                            break
                    else:
                        stale_rounds = 0
                    prev_count = current_count

                # Collect all result links
                result_links = page.locator(
                    "[role='feed'] a.hfpxzc, div.m6QErb a.hfpxzc"
                )
                link_count = result_links.count()
                print(f"  → {link_count} resultados encontrados")

                # Extract data from each result
                for i in range(link_count):
                    try:
                        link = result_links.nth(i)
                        aria_label = link.get_attribute("aria-label") or ""
                        href = link.get_attribute("href") or ""

                        if not aria_label:
                            continue

                        biz = Business(
                            nome=aria_label.strip(),
                            google_maps_url=href,
                            fonte=f"scraper_gmaps|{query}",
                        )

                        # Extract coords from URL
                        lat, lon = extract_coords_from_url(href)
                        biz.latitude = lat
                        biz.longitude = lon

                        # Try to get more info from the card
                        parent = link.locator("..").first
                        try:
                            # Rating
                            rating_el = parent.locator("span.MW4etd")
                            if rating_el.count() > 0:
                                biz.avaliacao = rating_el.first.inner_text().strip()
                            # Review count
                            reviews_el = parent.locator("span.UY7F9")
                            if reviews_el.count() > 0:
                                txt = reviews_el.first.inner_text().strip()
                                biz.total_reviews = re.sub(r"[^\d]", "", txt)
                            # Category / type
                            cat_els = parent.locator("div.W4Efsd > div.W4Efsd > span")
                            texts = []
                            for ci in range(min(cat_els.count(), 5)):
                                t = cat_els.nth(ci).inner_text().strip()
                                if t and t != "·":
                                    texts.append(t)
                            if texts:
                                biz.categoria = texts[0] if texts else ""
                                # Address is usually in the text parts
                                for t in texts[1:]:
                                    if any(kw in t.lower() for kw in ["urbanova", "são josé", "sao jose", "sjc", "rua", "av", "avenida"]):
                                        biz.endereco = t
                                        break
                        except Exception:
                            pass

                        # Generate unique ID
                        biz.place_id = generate_place_id(biz.nome, biz.endereco or href)

                        if biz.place_id not in all_businesses:
                            all_businesses[biz.place_id] = biz
                        else:
                            # Merge sources
                            existing = all_businesses[biz.place_id]
                            if query not in existing.fonte:
                                existing.fonte += f"|{query}"

                    except Exception as e:
                        print(f"  ⚠ Erro ao extrair resultado {i}: {e}")
                        continue

            except Exception as e:
                print(f"  ❌ Erro na busca '{query}': {e}")
                continue

        # Phase 2: Get details for each business by visiting their page
        businesses_list = list(all_businesses.values())
        print(f"\n📋 Total único após descoberta: {len(businesses_list)}")
        print("🔍 Extraindo detalhes de cada empresa...")

        if details_limit is not None and details_limit > 0:
            businesses_for_details = businesses_list[:details_limit]
        else:
            businesses_for_details = businesses_list

        if details_limit is not None and details_limit > 0 and details_limit < len(businesses_list):
            print(f"  ℹ Limitando detalhes para {details_limit}/{len(businesses_list)} empresas (para acelerar).")

        for idx, biz in enumerate(businesses_for_details):
            if not biz.google_maps_url:
                continue
            try:
                if (idx + 1) % 10 == 0 or idx == 0:
                    print(f"  Detalhes: {idx+1}/{len(businesses_for_details)}")

                page.goto(biz.google_maps_url, wait_until="domcontentloaded", timeout=20000)
                time.sleep(2)

                # Name (more accurate)
                try:
                    name_el = page.locator("h1.DUwDvf")
                    if name_el.count() > 0:
                        biz.nome = name_el.first.inner_text().strip()
                except Exception:
                    pass

                # Address
                try:
                    addr_btn = page.locator("[data-item-id='address'] div.fontBodyMedium, button[data-item-id='address'] div.fontBodyMedium")
                    if addr_btn.count() > 0:
                        biz.endereco = addr_btn.first.inner_text().strip()
                except Exception:
                    pass

                # Phone
                try:
                    phone_el = page.locator("[data-tooltip='Copiar o número de telefone'] div.fontBodyMedium, [data-item-id^='phone'] div.fontBodyMedium")
                    if phone_el.count() > 0:
                        biz.telefone = phone_el.first.inner_text().strip()
                except Exception:
                    pass

                # Website
                try:
                    web_el = page.locator("[data-tooltip='Abrir o site'] div.fontBodyMedium, [data-item-id='authority'] div.fontBodyMedium")
                    if web_el.count() > 0:
                        biz.website = web_el.first.inner_text().strip()
                except Exception:
                    pass

                # Hours
                try:
                    hours_el = page.locator("[aria-label*='horário'], [data-item-id='oh'] .fontBodyMedium")
                    if hours_el.count() > 0:
                        biz.horario = hours_el.first.get_attribute("aria-label") or hours_el.first.inner_text().strip()
                except Exception:
                    pass

                # Category
                try:
                    cat_el = page.locator("button.DkEaL")
                    if cat_el.count() > 0:
                        biz.categoria = cat_el.first.inner_text().strip()
                except Exception:
                    pass

                # Rating
                try:
                    rating_el = page.locator("div.F7nice span[aria-hidden='true']")
                    if rating_el.count() > 0:
                        biz.avaliacao = rating_el.first.inner_text().strip()
                    reviews_el = page.locator("div.F7nice span span")
                    if reviews_el.count() > 0:
                        txt = reviews_el.first.inner_text().strip()
                        biz.total_reviews = re.sub(r"[^\d]", "", txt)
                except Exception:
                    pass

                # Status
                try:
                    status_el = page.locator("span.ZDu9vd span")
                    if status_el.count() > 0:
                        biz.status_negocio = status_el.first.inner_text().strip()
                except Exception:
                    pass

                # Coordinates from URL
                current_url = page.url
                lat, lon = extract_coords_from_url(current_url)
                if lat != 0.0:
                    biz.latitude = lat
                    biz.longitude = lon

                # Update place_id with better info
                biz.place_id = generate_place_id(biz.nome, biz.endereco or biz.google_maps_url)

            except Exception as e:
                print(f"  ⚠ Erro detalhes '{biz.nome}': {e}")
                continue

        browser.close()

    return list(all_businesses.values())


def build_search_queries(config_path: Optional[Path] = None) -> List[str]:
    """Monta buscas a partir de config/buscas_urbanova.json (segmentos + opcional amplas)."""
    path = config_path or buscas_config_default_path()
    bairros, cidades, amplas, segmentos = load_buscas_arquivo(path)

    queries: List[str] = []
    seen: set[str] = set()
    for cidade in cidades:
        for bairro in (bairros or [""]):
            for seg in segmentos:
                parts = [seg, bairro, cidade]
                q = " ".join(p.strip() for p in parts if p and p.strip())
                if q not in seen:
                    seen.add(q)
                    queries.append(q)

    if amplas:
        for cidade in cidades:
            for bairro in (bairros or [""]):
                for broad_prefix in ("empresas", "comércio", "serviços", "lojas"):
                    parts = [broad_prefix, bairro, cidade]
                    broad = " ".join(p.strip() for p in parts if p and p.strip())
                    if broad not in seen:
                        seen.add(broad)
                        queries.append(broad)

    return queries


def export_csv(path: Path, businesses: List[Business]) -> None:
    cols = [
        "place_id", "nome", "endereco", "latitude", "longitude",
        "telefone", "horario", "website", "avaliacao", "total_reviews",
        "categoria", "status_negocio", "google_maps_url", "fonte",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for biz in businesses:
            writer.writerow(asdict(biz))


def export_jsonl(path: Path, businesses: List[Business]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for biz in businesses:
            f.write(json.dumps(asdict(biz), ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scraper gratuito de Google Maps")
    parser.add_argument("--headless", action="store_true", default=True, help="Rodar sem interface gráfica")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Rodar com interface gráfica")
    parser.add_argument("--max-scroll", type=int, default=60, help="Max scrolls por busca")
    parser.add_argument("--scroll-pause-ms", type=int, default=1500, help="Pausa entre scrolls (ms)")
    parser.add_argument("--slow-mo", type=int, default=50, help="Slow motion do browser (ms)")
    parser.add_argument("--output-dir", default="output", help="Diretório de saída")
    parser.add_argument("--skip-details", action="store_true", help="Pular coleta de detalhes individuais")
    parser.add_argument(
        "--details-limit",
        type=int,
        default=0,
        help="Limita quantas empresas terão a fase de detalhes (0 = sem limite; ignora se --skip-details).",
    )
    parser.add_argument(
        "--buscas-config",
        type=Path,
        default=None,
        help="JSON com segmentos (default: config/buscas_urbanova.json)",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    queries = build_search_queries(config_path=args.buscas_config)
    print(f"🚀 Iniciando scraper Google Maps ({len(queries)} buscas)")
    print(f"   Modo: {'headless' if args.headless else 'com interface'}")

    details_limit: Optional[int] = None
    if not args.skip_details and args.details_limit and args.details_limit > 0:
        details_limit = int(args.details_limit)

    businesses = scrape_google_maps(
        queries=queries,
        headless=args.headless,
        max_scroll=args.max_scroll,
        slow_mo=args.slow_mo,
        scroll_pause_ms=args.scroll_pause_ms,
        details_limit=details_limit,
    )

    # Filter for Urbanova area
    urbanova_businesses = []
    other_businesses = []
    for biz in businesses:
        text = f"{biz.endereco} {biz.nome} {biz.fonte}".lower()
        if "urbanova" in text:
            urbanova_businesses.append(biz)
        else:
            other_businesses.append(biz)

    # Export all (broad)
    export_csv(out_dir / "empresas_urbanova_scraper.csv", businesses)
    export_jsonl(out_dir / "empresas_scraper_descoberta.jsonl", businesses)

    # Export filtered
    export_csv(out_dir / "empresas_urbanova_scraper_filtrada.csv", urbanova_businesses)

    # Summary
    with_phone = sum(1 for b in businesses if b.telefone)
    with_hours = sum(1 for b in businesses if b.horario)
    with_site = sum(1 for b in businesses if b.website)
    total = len(businesses) or 1

    summary = {
        "timestamp_unix": int(time.time()),
        "metodo": "scraper_google_maps_gratuito",
        "custo": "R$ 0,00",
        "total_empresas_descobertas": len(businesses),
        "empresas_urbanova_confirmadas": len(urbanova_businesses),
        "empresas_arredores": len(other_businesses),
        "cobertura": {
            "com_telefone_pct": round(100.0 * with_phone / total, 2),
            "com_horario_pct": round(100.0 * with_hours / total, 2),
            "com_website_pct": round(100.0 * with_site / total, 2),
        },
        "queries_executadas": len(queries),
        "arquivos": [
            "output/empresas_urbanova_scraper.csv",
            "output/empresas_urbanova_scraper_filtrada.csv",
            "output/empresas_scraper_descoberta.jsonl",
        ],
    }
    (out_dir / "resumo_scraper.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✅ Scraping concluído!")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
