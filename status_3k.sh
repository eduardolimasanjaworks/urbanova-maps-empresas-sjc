#!/usr/bin/env bash
# Mostra o progresso da coleta a qualquer momento.
cd "/root/gerador de lead - revista urbanova" || exit 1

echo "=== PROCESSOS ATIVOS ==="
pgrep -af "rodar_crawler_vale_paralelo|scraper_google_maps|consolidar_leads_paralelo" 2>/dev/null \
  | grep -v "grep" | wc -l | xargs echo "processos:"

echo ""
echo "=== LEADS FINAIS ==="
.venv/bin/python - <<'PY'
import csv
from pathlib import Path
p = Path("output_leads_enxutos/leads_enxutos.csv")
if p.exists():
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    tel = sum(1 for r in rows if (r.get("telefone") or "").strip())
    cats = {}
    for r in rows:
        c = r.get("categoria_alvo", "?")
        cats[c] = cats.get(c, 0) + 1
    print(f"TOTAL LEADS: {len(rows)} | com telefone: {tel}")
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {c}: {n}")
else:
    print("ainda sem CSV final")
PY

echo ""
echo "=== BRUTO POR CIDADE (top 15) ==="
for d in output_leads_enxutos/*/; do
  f="${d}empresas_urbanova_scraper.csv"
  [ -f "$f" ] && echo "$(( $(wc -l < "$f") - 1 )) $(basename "$d")"
done 2>/dev/null | sort -rn | head -15
