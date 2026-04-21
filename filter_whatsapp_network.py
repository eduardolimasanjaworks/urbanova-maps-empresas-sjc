#!/usr/bin/env python3
"""Filtra lista de convites priorizando networking de e-commerce (B2B / vendedores)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from whatsapp_finder.network_filter import filter_crawl_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("output/whatsapp_groups_manual/groups_br_crawl_new.json"),
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("output/whatsapp_groups_manual/groups_br_network_ecommerce_filtered.json"),
    )
    parser.add_argument(
        "--out-txt",
        type=Path,
        default=Path("output/whatsapp_groups_manual/groups_br_network_ecommerce_filtered.txt"),
    )
    parser.add_argument("--min-score", type=float, default=0.5)
    parser.add_argument("--top", type=int, default=300)
    args = parser.parse_args()

    summary = filter_crawl_json(
        input_path=args.input,
        output_json=args.out_json,
        output_txt=args.out_txt,
        min_score=args.min_score,
        top_n=args.top,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
