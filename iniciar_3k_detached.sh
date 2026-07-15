#!/usr/bin/env bash
# Lança a coleta enxuta (3k leads) totalmente desacoplada do SSH.
# Sobrevive a desconexões porque cada processo roda em sua própria sessão (setsid).

set -u
cd "/root/gerador de lead - revista urbanova" || exit 1

VENV=".venv/bin/python"
CONFIG="config/buscas_leads_enxutos_sp.json"
OUT="output_leads_enxutos"
LOGDIR="$OUT/_logs"
mkdir -p "$LOGDIR"

STAMP="$(date +%Y%m%d_%H%M%S)"

# Workers dimensionados para o servidor (8 CPU / 15GB). Ajustável via 1o argumento.
WORKERS="${1:-5}"

# 1) Crawler principal: N cidades em paralelo, detalhes completos.
setsid nohup "$VENV" -u rodar_crawler_vale_paralelo.py \
  --config "$CONFIG" \
  --output-root "$OUT" \
  --workers "$WORKERS" \
  --max-scroll 15 \
  --details-limit 0 \
  --final-output "$OUT/leads_enxutos.csv" \
  --final-limit 12000 \
  > "$LOGDIR/crawler_$STAMP.log" 2>&1 < /dev/null &
echo "crawler_pid=$! workers=$WORKERS"

# 2) Consolidador contínuo: atualiza o CSV final a cada 45s.
setsid nohup bash -c '
  cd "/root/gerador de lead - revista urbanova" || exit 1
  while true; do
    .venv/bin/python consolidar_leads_paralelo.py \
      --output-root output_leads_enxutos \
      --final-output output_leads_enxutos/leads_enxutos.csv \
      --limit 12000 >> output_leads_enxutos/_logs/consolidador.log 2>&1
    sleep 45
  done
' > "$LOGDIR/consolidador_boot_$STAMP.log" 2>&1 < /dev/null &
echo "consolidador_pid=$!"

echo "OK: coleta rodando desacoplada. Logs em $LOGDIR"
