# 🚦 Mapa de Acidentes — Passo Fundo, RS

Dashboard interativo que mapeia acidentes de trânsito em **Passo Fundo e região (RS)**, agregando notícias de múltiplos veículos locais e dados oficiais da Polícia Rodoviária Federal. O objetivo é transformar matérias dispersas em um panorama navegável — onde, quando e com que gravidade os acidentes acontecem.

> Dados de **2014 a 2026** · **7.300+** matérias de 3 fontes · **1.150** registros oficiais da PRF · geocodificação automática · validação cruzada entre fontes.

---

## Por que existe

Acidentes de trânsito são noticiados todos os dias pela imprensa local, mas a informação fica presa em matérias soltas — impossível enxergar padrões. Este projeto coleta essas notícias, extrai *onde* e *quando* cada acidente aconteceu, cruza com a base oficial da PRF e plota tudo num mapa. O resultado responde perguntas que nenhuma matéria individual responde:

- Quais cruzamentos concentram mais acidentes?
- Os fatais estão nas rodovias ou nas vias urbanas?
- A gravidade muda por horário / período do dia?

## Fontes de dados

| Fonte | Tipo | Cobertura | Volume |
|---|---|---|---|
| [RD Planalto](https://rdplanalto.com) | Notícias (scraping) | 2014–2026, todas as vias | 3.580 |
| [Rádio Uirapuru](https://rduirapuru.com.br) | Notícias (scraping) | região do Planalto | 2.961 |
| [GZH Passo Fundo](https://gauchazh.clicrbs.com.br/passo-fundo/) | Notícias (scraping) | 2023–2026 | 831 |
| [PRF — Dados Abertos](https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos) | Oficial (CSV) | rodovias federais, 2015–2024 | 1.150 |

Cada acidente preserva os **links das matérias originais** — a fonte é sempre rastreável.

## Como funciona

```
┌─────────────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────────┐
│  Scrapers   │──▶│  Extração    │──▶│ Geocodificação │──▶│   DuckDB     │
│ (3 sites)   │   │ local/data   │   │ Nominatim/OSM  │   │              │
└─────────────┘   └──────────────┘   └───────────────┘   └──────┬───────┘
┌─────────────┐                                                  │
│ PRF (CSV)   │──────────────────────────────────────────────────┤
└─────────────┘                                                  ▼
                  ┌──────────────┐   ┌───────────────┐   ┌──────────────┐
                  │ Enriquecimento│  │  Deduplicação │   │  Streamlit   │
                  │ hora/km/vítima│─▶│ + Confiança    │──▶│  (mapa)      │
                  └──────────────┘   └───────────────┘   └──────────────┘
```

1. **Scraping** — coleta título, data e URL das páginas de categoria de cada site
2. **Extração** — deriva localização (cruzamento, rodovia, avenida, bairro) e município do slug da URL
3. **Geocodificação** — converte endereços em coordenadas via Nominatim (OSM); cruzamentos via Overpass
4. **Enriquecimento** — abre as matérias de acidentes graves/fatais para extrair hora, km, vítimas e veículos do corpo
5. **Deduplicação** — agrupa matérias do mesmo acidente (inclusive entre fontes) por local + data
6. **Confiança** — atribui nível (alta/média/baixa) por concordância entre fontes e consistência interna
7. **Visualização** — mapa de calor + marcadores por severidade no Streamlit

## Stack

- **Coleta:** `requests` + `BeautifulSoup`
- **Dados:** `DuckDB` (banco analítico embutido) + `pandas`
- **Geocodificação:** `geopy` (Nominatim) + Overpass API
- **App:** `Streamlit` + `folium`
- **Testes:** `pytest`

## Rodando localmente

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Coletar e processar os dados
python run_pipeline.py        # scraping + geocoding + dedup + confiança
python run_prf.py             # baixa e integra os dados da PRF

# 3. Subir o dashboard
streamlit run app/streamlit_app.py
```

O app abre em `http://localhost:8501`.

## Estrutura

```
scrapers/        coletores por fonte (rdplanalto, uirapuru, gzh, prf)
pipeline/        extração, geocoding, storage, dedup, enriquecimento, confiança
app/             dashboard Streamlit
tests/           testes das funções de extração e classificação
run_*.py         scripts de orquestração
```

## Testes

```bash
python -m pytest tests/ -v
```

Cobrem as partes mais frágeis — extração de localização, classificação de severidade e parsing de vítimas/hora/km em português (incluindo números por extenso).

## Roadmap

- [ ] Integrar base de acidentes urbanos da Secretaria de Segurança de Passo Fundo
- [ ] Aplicar o km extraído na geocodificação de rodovias (ponto exato vs. centro da via)
- [ ] Melhorar o casamento de acidentes entre fontes diferentes
- [ ] Atualização automática diária

## Licença

Projeto de portfólio / uso educacional. As notícias e dados pertencem às respectivas fontes, sempre creditadas com link para o original.
