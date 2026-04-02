#!/usr/bin/env python3
"""
Simulador simples de custo para coleta Urbanova (USD).

Premissas iniciais (pricing global observado em 31/03/2026):
  - Nearby Search Pro: $32 / 1000
  - Text Search Pro: $32 / 1000
  - Place Details Enterprise: $20 / 1000
Caps gratuitos por mes (por SKU):
  - Nearby Search Pro: 5000
  - Text Search Pro: 5000
  - Place Details Enterprise: 1000
"""

from __future__ import annotations

import argparse
import json
import math


def billable_after_cap(total: int, cap: int) -> int:
    return max(total - cap, 0)


def sku_cost(total: int, cap: int, price_per_1000: float) -> float:
    billed = billable_after_cap(total, cap)
    return (billed / 1000.0) * price_per_1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nearby", type=int, default=0, help="Quantidade de requests Nearby Search Pro")
    parser.add_argument("--text", type=int, default=0, help="Quantidade de requests Text Search Pro")
    parser.add_argument("--details", type=int, default=0, help="Quantidade de requests Place Details Enterprise")
    args = parser.parse_args()

    caps = {"nearby": 5000, "text": 5000, "details": 1000}
    prices = {"nearby": 32.0, "text": 32.0, "details": 20.0}

    cost_nearby = sku_cost(args.nearby, caps["nearby"], prices["nearby"])
    cost_text = sku_cost(args.text, caps["text"], prices["text"])
    cost_details = sku_cost(args.details, caps["details"], prices["details"])
    total = cost_nearby + cost_text + cost_details

    result = {
        "input": {"nearby": args.nearby, "text": args.text, "details": args.details},
        "billed_events": {
            "nearby": billable_after_cap(args.nearby, caps["nearby"]),
            "text": billable_after_cap(args.text, caps["text"]),
            "details": billable_after_cap(args.details, caps["details"]),
        },
        "cost_usd": {
            "nearby": round(cost_nearby, 2),
            "text": round(cost_text, 2),
            "details": round(cost_details, 2),
            "total": round(total, 2),
        },
        "round_up_month_budget_suggestion_usd": int(math.ceil(total)),
        "warning": "Estimativa simplificada. Valores e SKUs podem mudar; valide no pricing oficial.",
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

