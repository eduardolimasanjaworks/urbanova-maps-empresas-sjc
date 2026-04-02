# Execucao full Urbanova (sem PoC)

## O que ja ficou pronto

- Extracao de logradouros via Overpass:
  - `extrair_vias_urbanova.py`
- Coletor integrado com vias reais:
  - `coletar_empresas_urbanova.py` (usa `--roads-file output/vias_urbanova.csv`)
- Pipeline full com rodadas e saturacao:
  - `pipeline_full_urbanova.py`
- Teste real de API key:
  - `validar_maps_key.py`

## Artefatos ja gerados localmente

- `output/vias_urbanova.csv`
- `output/vias_urbanova_auditoria.csv`
- `output/vias_urbanova.geojson`

## Unico requisito faltante para captura total de empresas

- Definir `MAPS_SERVER_API_KEY` (Places API New + billing ativo).

## Comandos de producao

1) Validar a API key:

```bash
python validar_maps_key.py --api-key SUA_KEY
```

2) Rodar pipeline full:

```bash
python pipeline_full_urbanova.py --api-key SUA_KEY --passes 3 --step 220 --radius 280
```

## Saidas finais esperadas

- `output/empresas_urbanova.csv` (base ampla)
- `output/empresas_urbanova_filtrada.csv` (endereco contendo Urbanova)
- `output/resumo_execucao.json`
- `output/cobertura_por_via.json`
- `output/evidencias_pipeline_full.json`

