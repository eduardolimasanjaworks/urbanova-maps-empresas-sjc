# WhatsApp Group Finder (OSINT)

Ferramenta para descobrir links públicos `chat.whatsapp.com` em páginas indexadas por buscadores.

## Objetivo

- Coletar links de convite públicos com foco em nichos (ex.: e-commerce/networking).
- Salvar incrementalmente para não perder progresso.
- Gerar JSON/CSV com links únicos e metadados da origem.

## Instalação

```bash
pip install -r requirements.txt
```

## Uso rápido

```bash
python whatsapp_group_finder.py \
  --keywords-file config/keywords_ecommerce.txt \
  --engines bing,duckduckgo,brave \
  --target 15000 \
  --max-dorks 350 \
  --depth 2 \
  --per-query 30 \
  --delay-min 1.2 \
  --delay-max 3.2 \
  --lang pt,en,es \
  --concurrency 12 \
  --out output/whatsapp_groups
```

## Saídas

- `output/whatsapp_groups/groups_raw.jsonl`
- `output/whatsapp_groups/groups_unique.csv`
- `output/whatsapp_groups/groups_unique.json`
- `output/whatsapp_groups/checkpoint.json`
- `output/whatsapp_groups/run_summary.json`

## Observações

- A coleta usa apenas páginas públicas e indexadas.
- Alguns links podem estar expirados, cheios ou revogados.
- Ajuste `--delay-*` e `--concurrency` para reduzir risco de bloqueio.
- Use `--max-dorks` para controlar duração da execução e custo computacional.
- Se você tiver SearXNG self-hosted, pode usar `--engines searxng --searx-url http://localhost:8080`.

