#!/usr/bin/env python3
"""Gera CSV final enxuto: apenas clubes, escolinhas, escolas, condomínios, SESI/SESC, ADC."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# Termos de busca (scraper)
SEGMENTOS_BUSCA = [
    "clube de campo",
    "escolinha de futebol",
    "escola de futebol",
    "escolinha de natação",
    "escola de natação",
    "grêmio recreativo",
    "associação desportiva classista",
    "adc",
    "sesi",
    "sesc",
    "escola municipal",
    "emef",
    "emei",
    "escola particular",
    "colégio particular",
    "creche particular",
    "condomínio residencial",
    "condomínio",
    "administradora de condomínios",
    "síndico profissional",
    "associação de moradores",
]

# Categoria final exibida no CSV (lista enxuta do usuário)
CATEGORIA_ALVO_RULES: List[Tuple[str, List[str]]] = [
    ("Clube de campo", ["clube de campo", "country club"]),
    ("Escolinha de futebol", ["escolinha de futebol", "escola de futebol", "futebol infantil", "futebol society", "escolinha futebol"]),
    ("Escolinha de natação", ["escolinha de natação", "escola de natação", "natação infantil", "academia de natação", "clube de natação", "natação"]),
    ("Grêmio recreativo", ["grêmio recreativo", "gremio recreativo", "clube recreativo", "associação recreativa"]),
    ("ADC", ["associação desportiva classista", " adc ", "adc"]),
    ("SESI", ["sesi"]),
    ("SESC", ["sesc"]),
    ("Escola municipal", ["escola municipal", "emef", "emei", "escola pública", "escola publica"]),
    ("Escola particular", ["escola particular", "colégio particular", "colegio particular", "creche particular", "escola infantil particular", "colégio", "colegio", "escola privada"]),
    ("Condomínio", ["condomínio", "condominio", "administradora de condomínios", "síndico", "sindico", "associação de moradores", "portaria condomínio"]),
]

CIDADES = [
    "São José dos Campos", "Jacareí", "Caçapava", "Taubaté", "Pindamonhangaba",
    "Tremembé", "Campos do Jordão", "Guaratinguetá", "Aparecida", "Lorena",
    "Cruzeiro", "Cachoeira Paulista", "Caraguatatuba", "Ubatuba", "São Sebastião",
    "Ilhabela", "Santos", "Guarujá", "Praia Grande", "Cubatão", "Bertioga",
    "Peruíbe", "Mongaguá", "Itanhaém", "São Vicente", "Campinas", "Jundiaí",
    "Sorocaba", "Mogi das Cruzes", "Atibaia", "Bragança Paulista", "Piracicaba",
    "Limeira", "Americana", "Indaiatuba", "Valinhos", "Vinhedo", "Ribeirão Preto",
    "São Carlos", "Araraquara", "Bauru", "Botucatu", "Itu", "Salto", "Tatuí",
    "Araçoiaba da Serra", "Osasco", "Barueri", "Cotia", "São Bernardo do Campo",
    "Santo André", "São Caetano do Sul", "Diadema", "Mauá", "Suzano",
    "Itaquaquecetuba", "Ferraz de Vasconcelos", "Guarulhos", "Arujá", "Poá",
]


def only_digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_text(value: str) -> str:
    return compact(value).lower()


def first_matching(text: str, options: Iterable[str]) -> str:
    text_norm = normalize_text(text)
    for option in options:
        if normalize_text(option) in text_norm:
            return option
    return ""


def extract_query(fonte: str) -> str:
    if not fonte:
        return ""
    parts = [p for p in fonte.split("|") if p and p != "scraper_gmaps"]
    return parts[0] if parts else fonte


def classify_lead(query: str, nome: str, categoria: str, endereco: str) -> str:
    blob = normalize_text(" ".join([query, nome, categoria, endereco]))
    for label, keywords in CATEGORIA_ALVO_RULES:
        for kw in keywords:
            if normalize_text(kw) in blob:
                return label
    return ""


def is_target_lead(query: str, nome: str, categoria: str, endereco: str) -> bool:
    if first_matching(query, SEGMENTOS_BUSCA):
        return True
    return bool(classify_lead(query, nome, categoria, endereco))


def dedupe_key(row: Dict[str, str]) -> str:
    phone = only_digits(row.get("telefone", ""))
    if phone:
        return f"phone:{phone}"
    raw = f"{normalize_text(row.get('nome', ''))}|{normalize_text(row.get('endereco', ''))}"
    return "name:" + hashlib.md5(raw.encode("utf-8")).hexdigest()


def is_possible_whatsapp(phone: str) -> str:
    digits = only_digits(phone)
    if digits.startswith("55"):
        local = digits[2:]
    else:
        local = digits
    return "sim" if len(local) in {10, 11} else ""


def lead_score(row: Dict[str, str]) -> tuple:
    has_phone = 1 if row.get("telefone") else 0
    has_site = 1 if row.get("website") else 0
    reviews_digits = only_digits(row.get("total_reviews", ""))
    reviews = int(reviews_digits) if reviews_digits else 0
    return (has_phone, has_site, reviews, row.get("nome", ""))


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera CSV enxuto de leads públicos")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=12000)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Arquivo de entrada não encontrado: {input_path}")

    with input_path.open("r", encoding="utf-8", newline="") as f:
        raw_rows = list(csv.DictReader(f))

    deduped: Dict[str, Dict[str, str]] = {}
    skipped = 0
    for raw in raw_rows:
        query = extract_query(raw.get("fonte", ""))
        nome = compact(raw.get("nome", ""))
        categoria_google = compact(raw.get("categoria", ""))
        endereco = compact(raw.get("endereco", ""))

        if not is_target_lead(query, nome, categoria_google, endereco):
            skipped += 1
            continue

        phone = compact(raw.get("telefone", ""))
        website = compact(raw.get("website", ""))
        if not phone and not website:
            continue

        categoria_alvo = classify_lead(query, nome, categoria_google, endereco)
        if not categoria_alvo:
            categoria_alvo = first_matching(query, SEGMENTOS_BUSCA) or "Outros (segmento alvo)"

        lead = {
            "nome": nome,
            "telefone": phone,
            "telefone_limpo": only_digits(phone),
            "possivel_whatsapp": is_possible_whatsapp(phone),
            "website": website,
            "categoria_alvo": categoria_alvo,
            "categoria_google": categoria_google,
            "cidade": first_matching(" ".join([endereco, query]), CIDADES),
            "endereco": endereco,
            "avaliacao": compact(raw.get("avaliacao", "")),
            "total_reviews": compact(raw.get("total_reviews", "")),
            "status_negocio": compact(raw.get("status_negocio", "")),
            "google_maps_url": compact(raw.get("google_maps_url", "")),
            "fonte": "Google Maps público",
            "consulta_origem": query,
        }
        key = dedupe_key(lead)
        existing = deduped.get(key)
        if existing is None or lead_score(lead) > lead_score(existing):
            deduped[key] = lead

    leads: List[Dict[str, str]] = sorted(deduped.values(), key=lead_score, reverse=True)
    leads = leads[: args.limit]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "nome", "telefone", "telefone_limpo", "possivel_whatsapp", "website",
        "categoria_alvo", "categoria_google", "cidade", "endereco",
        "avaliacao", "total_reviews", "status_negocio", "google_maps_url",
        "fonte", "consulta_origem",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(leads)

    with_phone = sum(1 for row in leads if row["telefone"])
    print(f"CSV final: {output_path}")
    print(f"Leads exportados: {len(leads)} (filtrados enxutos)")
    print(f"Com telefone: {with_phone}")
    print(f"Ignorados fora do segmento: {skipped}")


if __name__ == "__main__":
    main()
