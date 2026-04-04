# Coleta de Empresas do Urbanova — São José dos Campos

## 🆓 Modo GRATUITO (recomendado!)

Não precisa de API key nem billing do Google. Custo: **R$ 0,00**.

### Comando único (pipeline completo):

```bash
python pipeline_gratuito.py
```

### Opções avançadas:

```bash
# Apenas OpenStreetMap (rápido, ~30s)
python pipeline_gratuito.py --skip-scraper

# Apenas Google Maps Scraping (mais dados, ~15min)
python pipeline_gratuito.py --skip-osm

# Controlar scrolls no scraper
python pipeline_gratuito.py --max-scroll 80
```

### Scripts individuais:

```bash
# Scraper Google Maps (Playwright headless)
python scraper_google_maps.py --headless

# POIs do OpenStreetMap
python extrair_pois_osm.py

# Logradouros do OpenStreetMap
python extrair_vias_urbanova.py
```

### Saídas do modo gratuito:

- `output/empresas_urbanova_FINAL.csv` — base completa unificada
- `output/empresas_urbanova_FINAL_filtrada.csv` — apenas Urbanova confirmado
- `output/empresas_unificadas.jsonl` — dados completos em JSONL
- `output/pois_osm_urbanova.csv` — POIs do OpenStreetMap
- `output/pois_osm_urbanova.geojson` — GeoJSON para visualização
- `output/resumo_pipeline_gratuito.json` — resumo da execução

### Dependências (modo gratuito):

```bash
pip install playwright beautifulsoup4 lxml
python -m playwright install chromium
```

---

## 💳 Modo PAGO (API Google - legacy)

Requer `MAPS_SERVER_API_KEY` com Places API + billing ativo.

```bash
# Simular custo
python simulador_custos_urbanova.py --nearby 3000 --text 1200 --details 2200

# Validar API key
python validar_maps_key.py --api-key SUA_KEY

# Pipeline completo pago
python pipeline_full_urbanova.py --api-key SUA_KEY --passes 3 --step 220 --radius 280
```

---

## 🌐 Terminal Web

Interface web com menu interativo (suporta modo gratuito e pago):

```bash
cd terminal-web
cp .env.example .env  # editar senha se necessário
npm install
npm start
```

---

## Fontes de dados

| Fonte | Tipo | Custo | Dados |
|---|---|---|---|
| Google Maps Scraper | Web scraping via Playwright | Grátis | Nome, endereço, telefone, horário, site, avaliação |
| OpenStreetMap/Overpass | API aberta | Grátis | Nome, endereço, telefone, site, email, horário |
| Google Places API | API oficial | ~US$10-50 | Nome, endereço, telefone, horário, site (legacy) |

