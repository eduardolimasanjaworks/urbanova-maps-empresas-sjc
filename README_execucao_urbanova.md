# Execucao pratica - Urbanova (Google Places API New)

## Arquivos entregues

- `estudo_urbanova_google_maps_2026-03-31.md`
- `urbanova_referencias_geograficas.json`
- `coletar_empresas_urbanova.py`
- `simulador_custos_urbanova.py`

## 1) Simular custo antes de rodar

Exemplo:

```bash
python simulador_custos_urbanova.py --nearby 3000 --text 1200 --details 2200
```

## 2) Rodar coleta

```bash
python coletar_empresas_urbanova.py --api-key SUA_CHAVE_AQUI
```

Ou via `.env`:

```env
MAPS_SERVER_API_KEY=SUA_CHAVE_AQUI
```

Parametros uteis:

- `--radius 300` (raio por celula)
- `--step 300` (distancia entre celulas da grade)
- `--road-radius 200` (raio para varredura de cada via de referencia)
- `--road-threshold-m 180` (distancia maxima para considerar via coberta)
- `--sleep-ms 120` (pausa entre requests para reduzir risco de rate limit)
- `--skip-road-scan` (desliga busca por rua/avenida)
- `--skip-text-scan` (desliga busca textual por segmento)

## 3) Saidas geradas

Em `output/`:

- `places_descoberta.jsonl` (linhagem da descoberta)
- `places_detalhes.jsonl` (payload de detalhes por place_id)
- `empresas_urbanova.csv` (base consolidada)
- `cobertura_por_via.json` (vias cobertas vs lacunas)
- `resumo_execucao.json` (KPIs de cobertura)

## 4) QA minimo recomendado

Conferir no `resumo_execucao.json`:

- `with_phone_pct`
- `with_hours_pct`
- `with_website_pct`
- `with_location_pct`

Critério prático inicial:

- >= 70% com telefone
- >= 70% com horário
- >= 60% com website

Se os indicadores ficarem baixos:

1. Reduzir `--step` para aumentar densidade da malha.
2. Rodar nova rodada com mais consultas de `searchText`.
3. Expandir grupos de `includedTypes` por segmento faltante.

## 5) Conformidade e termos

- Use os dados conforme os termos da Google Maps Platform.
- Revise regras de armazenamento/retencao/exibicao e atribuicao.
- Nao tratar esta coleta como garantia de 100% de estabelecimentos.

