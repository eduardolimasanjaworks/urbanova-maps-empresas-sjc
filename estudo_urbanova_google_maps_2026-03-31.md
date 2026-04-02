# Estudo atualizado: captura de empresas do Urbanova via Google (31/03/2026)

## Escopo e resposta direta

Você quer capturar o **máximo possível** de empresas do Urbanova (SJC/SP), com dados ricos (nome, endereço, horário, telefone, website, descrição etc.).

Conclusão prática:

- A melhor arquitetura é usar **Places API (New)** em 3 etapas: `searchNearby` + `searchText` + `Place Details`.
- **Google Business Profile API** (antigo "Google Meu Negócio" API) **não** é a API correta para varrer todo o bairro; ela é para contas/perfis próprios ou autorizados.
- Dá para fazer **PoC pequena** só com franquia grátis por SKU, mas para cobertura alta + enriquecimento amplo o normal é ter custo pago.

---

## 1) Delimitação geográfica operacional do Urbanova

Observação: bairro não tem um "polígono oficial único" público no Google Maps Platform para cobrança/consulta. Na prática, você precisa de um perímetro operacional.

### 1.1 Começa aqui / termina aqui (envelope operacional recomendado)

- **Começa (leste, entrada principal aproximada):** região da Avenida Shishima Hifumi, próximo a `-23.1955314, -45.9325347`.
- **Termina (oeste, região do Parque Ribeirão Vermelho):** aproximadamente `-23.1992281, -45.9641029`.

Envelope inicial para varredura (ajustável por validação):

- **Latitude:** `-23.212` até `-23.188`
- **Longitude:** `-45.965` até `-45.930`

### 1.2 Ruas/pontos de contorno e referência (>=10)

Referências relevantes para malha de busca, QA e auditoria:

1. Avenida Shishima Hifumi (eixo principal): `-23.1993711, -45.9360518`
2. Avenida Ironman Victor Garrido: `-23.2012727, -45.9463171`
3. Avenida Papa João Paulo II: `-23.2029124, -45.9509053`
4. Avenida Antônio Widmer: `-23.2027916, -45.9561257`
5. Avenida Possidônio José de Freitas: `-23.1960037, -45.9401674`
6. Avenida Lineu de Moura (acesso/conexão): `-23.1937421, -45.9213587`
7. Rua Armando de Souza Guedes (referência de borda leste): `-23.1874008, -45.9333393`
8. Parque Ribeirão Vermelho: `-23.1965335, -45.9585128`
9. UNIVAP Urbanova: `-23.2077365, -45.9487973`
10. Urbanova I (centro nominal): `-23.1963979, -45.9355225`
11. Urbanova II (centro nominal): `-23.2024587, -45.9432628`
12. Urbanova III (centro nominal): `-23.2001331, -45.9490986`
13. Urbanova IV (centro nominal): `-23.2033247, -45.9497703`
14. Urbanova V (centro nominal): `-23.2039215, -45.9558321`
15. Urbanova VI (centro nominal): `-23.1997580, -45.9537916`
16. Urbanova VII (centro nominal): `-23.2006582, -45.9608925`

---

## 2) APIs/Endpoints mais adequados (Google, estado atual)

## 2.1 APIs recomendadas

### Descoberta por área (principal)

- `POST https://places.googleapis.com/v1/places:searchNearby`
- Uso: varrer células geográficas do bairro.

### Descoberta textual (complementar)

- `POST https://places.googleapis.com/v1/places:searchText`
- Uso: capturar faltantes que o ranking/local index não trouxe no nearby.

### Enriquecimento por estabelecimento

- `GET https://places.googleapis.com/v1/places/{PLACE_ID}`
- Uso: trazer campos de contato/horário/detalhes para cada `place.id`.

## 2.2 Campos (FieldMask) por etapa

### Etapa A: descoberta (baixo custo relativo)

Use somente o necessário para deduplicar e localizar:

- `places.id`
- `places.displayName`
- `places.formattedAddress`
- `places.location`
- `places.primaryType`
- `places.types`
- `places.googleMapsUri` (opcional)

### Etapa B: enriquecimento (selectivo)

Para cada `place.id` consolidado, pedir:

- `id`
- `displayName`
- `formattedAddress`
- `location`
- `internationalPhoneNumber`
- `nationalPhoneNumber`
- `regularOpeningHours`
- `websiteUri`
- `businessStatus`
- `googleMapsUri`
- `primaryType`
- `types`
- `editorialSummary` (se necessário)

---

## 3) Quais dados você consegue e quais não

## 3.1 Consegue (oficialmente na Places API, conforme SKU)

- Nome
- Endereço
- Latitude/longitude
- Telefone (nacional/internacional)
- Horário de funcionamento
- Site
- Categoria/tipos
- Status de operação
- Rating e contagem de avaliações
- Reviews e summaries (em SKUs mais altos)

## 3.2 Limitações importantes

- **Email:** não é campo padrão dedicado da Places API.
- **WhatsApp:** não há campo oficial específico; pode surgir indiretamente via `websiteUri`, descrição, review ou texto público.
- **100% de todas as empresas:** nenhum provedor garante totalidade absoluta. Meta realista: **cobertura máxima auditável**, com múltiplas passadas.

## 3.3 Sobre Google Meu Negócio / Business Profile API

- Serve para gerenciar perfis de empresas próprias/autorizadas.
- Não é o endpoint ideal para "descobrir todas as empresas do bairro".

---

## 4) Estratégia de coleta para máxima cobertura

## 4.1 Malha geográfica (grid)

- Cobrir o envelope com círculos de raio **250m a 350m**.
- Para Urbanova, uma malha inicial de **~40 a 70 células** costuma ser um bom ponto de partida.
- Em cada célula:
  - `searchNearby` com `rankPreference=DISTANCE` e `maxResultCount=20`.
  - Rodadas por grupos de tipos (`includedTypes`) para reduzir viés de popularidade.

## 4.2 Rodadas por tipo (exemplo de grupos)

- Alimentação: `restaurant`, `cafe`, `bakery`
- Saúde: `hospital`, `dentist`, `pharmacy`, `doctor`
- Serviços: `beauty_salon`, `lawyer`, `accounting`, `real_estate_agency`
- Educação: `school`, `university`, `training_center`
- Comércio geral: `store`, `supermarket`, `convenience_store`
- Automotivo: `car_repair`, `gas_station`

## 4.3 Complemento com `searchText`

Executar consultas locais para capturar faltantes:

- "empresas urbanova são josé dos campos"
- "clínica urbanova são josé dos campos"
- "advocacia urbanova são josé dos campos"
- "contabilidade urbanova são josé dos campos"
- "academia urbanova são josé dos campos"

## 4.4 Deduplicação e consolidação

- Chave primária: `place.id`
- Chaves secundárias de reconciliação: `displayName + formattedAddress + location` (quando houver divergências).
- Salvar linhagem de origem:
  - endpoint (`nearby`/`text`)
  - célula geográfica
  - timestamp da coleta

---

## 5) Custos: estudo atualizado (31/03/2026)

Base: tabela oficial global do Google Maps Platform (USD por 1000 eventos), com cap de uso grátis por SKU.

SKUs mais relevantes:

- Places API Nearby Search Pro: **US$ 32.00 / 1000**
- Places API Text Search Pro: **US$ 32.00 / 1000**
- Places API Place Details Pro: **US$ 17.00 / 1000**
- Places API Place Details Enterprise: **US$ 20.00 / 1000**
- Places API Place Details Enterprise + Atmosphere: **US$ 25.00 / 1000**

Free caps observados na tabela:

- Nearby Search Pro: cap mensal gratuito de **5,000**
- Text Search Pro: cap mensal gratuito de **5,000**
- Place Details Enterprise: cap mensal gratuito de **1,000**
- Place Details Pro: cap mensal gratuito de **5,000**

## 5.1 Simulação rápida de cenários

### Cenário A (PoC econômica)

- 300 requests de discovery (nearby/text combinados)
- 600 details enterprise
- Tendência: **fica no gratuito** (dependendo do restante da conta/billing account no mês)

### Cenário B (médio, cobertura forte)

- 2,500 discovery
- 2,500 details enterprise
- Extrapola details enterprise acima do cap de 1,000:
  - parte paga aproximada: 1,500 * (US$ 20/1000) = **US$ 30**
  - discovery possivelmente ainda dentro do cap (dependendo split nearby/text e uso agregado da conta)

### Cenário C (exaustivo com revarredura)

- 8,000 discovery
- 6,000 details enterprise
- Exemplo aproximado (sem descontos de volume adicionais):
  - Nearby/Text acima do cap em ~3,000 eventos totais pagos se concentrados em um SKU: ~`3 * 32 = US$ 96`
  - Details Enterprise acima do cap em ~5,000: ~`5 * 20 = US$ 100`
  - Total aproximado: **US$ 196** (ordem de grandeza, depende da distribuição exata por SKU)

Resumo sobre "dá para usar só créditos grátis?":

- **Sim, para PoC e primeira fotografia.**
- **Não é seguro assumir grátis para cobertura quase total + enriquecimento completo.**

---

## 6) Conformidade, qualidade e operação

## 6.1 Conformidade

- Revisar e cumprir políticas de uso/armazenamento/atribuição da Google Maps Platform.
- Não assumir direito irrestrito de redistribuição de dados.

## 6.2 Controle técnico

- Quotas por método e rate limiting por minuto.
- Retry com backoff exponencial e jitter.
- Observabilidade:
  - taxa de erro por endpoint
  - latência
  - consumo por SKU

## 6.3 KPIs de cobertura

- `% registros com telefone`
- `% registros com horário`
- `% registros com website`
- `% com lat/lon`
- taxa de deduplicação
- ganho marginal por rodada adicional (novos registros / requests)

---

## 7) Arquitetura recomendada (resumo final)

1. Definir envelope + grid do Urbanova.
2. Executar `searchNearby` por célula/tipo (varredura principal).
3. Executar `searchText` com termos locais (complemento).
4. Deduplicar por `place.id`.
5. Enriquecer com `Place Details` em FieldMask seletiva.
6. Rodar QA de cobertura e custo.
7. Repetir só onde houver ganho marginal.

---

## 8) Fontes pesquisadas (internet, atualizadas)

- Google Places API Nearby Search (New)  
  <https://developers.google.com/maps/documentation/places/web-service/nearby-search>
- Google Places API Place Details (New)  
  <https://developers.google.com/maps/documentation/places/web-service/place-details>
- Place Data Fields (New)  
  <https://developers.google.com/maps/documentation/places/web-service/data-fields>
- Places Usage and Billing  
  <https://developers.google.com/maps/documentation/places/web-service/usage-and-billing>
- Google Maps Platform Pricing (Places)  
  <https://developers.google.com/maps/billing-and-pricing/pricing#places-pricing>
- Google Business Profile overview  
  <https://developers.google.com/my-business/content/overview>
- Referências geográficas complementares (Nominatim/OSM)  
  <https://nominatim.openstreetmap.org/>

