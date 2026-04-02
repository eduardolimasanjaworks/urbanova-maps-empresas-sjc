# Plano detalhado para obter TODAS as empresas do Urbanova (ou mais, nunca menos)

Data de referencia: 31/03/2026  
Objetivo: maximizar cobertura de empresas no Urbanova (Sao Jose dos Campos/SP), aceitando excesso controlado para evitar perda.

---

## 1) Definicao de sucesso (criterio de prova)

Vamos considerar que o plano funcionou quando:

- Gerar `empresas_urbanova.csv` com cobertura ampla.
- Existir evidencias de varredura por:
  - grade geoespacial,
  - ruas/avenidas,
  - busca textual por segmentos.
- Exibir indicadores de cobertura (telefone, horario, website, vias sem cobertura).
- Rodadas adicionais renderem ganho marginal baixo (sinal de saturacao).

**Regra sua (prioritaria):** se houver erro de precisao, preferir trazer "a mais" (falso positivo) do que "a menos" (falso negativo).

---

## 2) Arquitetura de captura (estrategia anti-perda)

## 2.1 Camada A: inventario viario completo

Google Places nao e ideal para descobrir todas as ruas.  
Entao a descoberta de vias deve vir de fonte cartografica (OSM/Overpass + validacao municipal quando possivel).

Entrega dessa camada:

- lista completa de vias do Urbanova (ruas/avenidas/alamedas)
- pontos de referencia por via (lat/lon)

## 2.2 Camada B: descoberta de empresas por area

Executar Places API com:

- `searchNearby` em grade densa (step e raio ajustados para cobertura)
- multipla repeticao por grupos de tipos (saude, alimentacao, servicos, etc.)

Objetivo: capturar empresas que aparecem por proximidade.

## 2.3 Camada C: descoberta por via

Para cada via inventariada:

- `searchNearby` no entorno da via
- `searchText` por segmento + nome da via

Objetivo: reduzir buracos locais.

## 2.4 Camada D: descoberta textual geral

`searchText` por termos setoriais no Urbanova para capturar negocios nao ranqueados no nearby.

## 2.5 Camada E: enriquecimento

Para cada `place_id` unico:

- `placeDetails` para telefone, horario, website, endereco e outros campos.

---

## 3) Politica de "nunca menos"

Para cumprir sua regra:

- usar parametros mais inclusivos na coleta inicial;
- permitir excedente geografico controlado no entorno do Urbanova;
- deduplicar por `place_id`;
- classificar "fora do alvo" em coluna de auditoria (em vez de excluir cedo demais);
- gerar versao "ampla" e versao "filtrada", mantendo rastreabilidade.

Resultado:

- base ampla (maxima captura)
- base final operacional (com filtros explicitos)

---

## 4) Fallbacks quando falhar

Mensagens curtas para o usuario (sem JSON bruto):

- "Nao funcionou: API key ausente/invalida."
- "Falhou: billing do Google Cloud parece inativo."
- "Falhou: permissao negada na Places API."
- "Falhou: limite de quota estourado."
- "Falhou: erro tecnico temporario."

Fallback tecnico automatico:

- retry com backoff;
- revarredura em areas/lacunas;
- reducao de taxa quando houver rate limit;
- nova rodada por vias sem cobertura.

---

## 5) Prova de cobertura (o que vamos te mostrar)

A cada execucao:

- total de empresas unicas encontradas;
- % com telefone;
- % com horario;
- % com website;
- vias sem cobertura;
- comparativo entre rodada atual e anterior (novas empresas adicionadas).

Quando o crescimento ficar baixo em rodadas sucessivas, marcamos "saturacao pratica".

---

## 6) Entregaveis finais

1. `empresas_urbanova.csv` (lista final)
2. `resumo_execucao.json` (indicadores)
3. `cobertura_por_via.json` (lacunas e auditoria)
4. `vias_urbanova.csv` (inventario de vias, quando ativarmos essa camada)
5. relatorio curto em linguagem leiga: "o que foi feito, o que pode faltar, proximo passo"

---

## 7) Sequencia de execucao recomendada

1. Validar API key e billing.
2. Rodar captura ampla (modo maximo).
3. Ver status e baixar CSV.
4. Rodar segunda passada em lacunas (vias sem cobertura).
5. Repetir ate ganho marginal baixo.
6. Entregar base final + base ampla de auditoria.

---

## 8) Compromisso com seu objetivo

Este plano foi montado para garantir:

- foco total em cobertura maxima;
- interface simples e guiada;
- mensagens claras;
- preferencia por excesso controlado (nunca menos).

Se houver conflito entre "precisao perfeita" e "nao perder empresa", o sistema prioriza **nao perder**.

