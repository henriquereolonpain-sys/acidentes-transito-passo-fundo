#  Mapa de Acidentes — Passo Fundo, RS

Dashboard interativo que mapeia acidentes de trânsito em **Passo Fundo e região (RS)**, agregando notícias de múltiplos veículos locais e dados oficiais da Polícia Rodoviária Federal. O objetivo é transformar matérias dispersas em um panorama navegável: onde, quando e com que gravidade os acidentes acontecem.

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
| [Rádio Tapejara](https://www.radiotapejara.com.br/noticias/assunto/17/acidente) | Notícias (scraping) | Tapejara e microrregião | — |
| [PRF — Dados Abertos](https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos) | Oficial (CSV) | rodovias federais, 2015–2024 | 1.150 |

Cada acidente preserva os **links das matérias originais** — a fonte é sempre rastreável.

## Por que não usamos dados oficiais do município

Em agosto/2026, por meio da Vereadora Marina Bernardes, foi protocolado o
**Pedido de Informação nº 52/2026** solicitando à Prefeitura de Passo Fundo
data, horário, local, classificação, veículos envolvidos e número de feridos
dos acidentes de trânsito do município.

A resposta — [**Ofício nº 199/2026-GAB**](docs/oficio-199-2026-pedido-52.pdf),
assinada pelo prefeito Pedro Almeida em 19/08/2026 — confirma a lacuna que
motiva este projeto:

- O **Boletim de Ocorrências digital** da Secretaria de Segurança Pública e
  Transportes ainda está em implementação; hoje só existe o boletim físico,
  preenchido em papel pelos Agentes de Trânsito, e por isso **não é possível
  extrair os dados solicitados**.
- Os Agentes de Trânsito municipais só registram acidentes **sem vítima**
  (dano material). Acidentes com ferido ou óbito na área urbana são
  atribuição da **Brigada Militar**, não da Prefeitura.

Ou seja: não existe hoje, em nenhum órgão público, uma base estruturada e
consultável de acidentes de trânsito em Passo Fundo — daí a necessidade de
reconstruir esse panorama a partir de notícias e da base federal da PRF.

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

Os passos 1–6 rodam sozinhos todos os dias (tarefa agendada, ver [`TRANSICAO.md`](TRANSICAO.md) para configurar em uma nova máquina).

## Qualidade de dados — auditoria manual

A extração automática de localização funciona bem, mas tem um limite conhecido: quando a matéria descreve um **cruzamento** ("na Rua X, esquina com a Rua Y"), a extração às vezes captura só a primeira rua e o ponto cai em qualquer lugar dela, em vez de na esquina exata. Para esses casos, existe uma etapa de revisão humana:

```bash
python runs/corrigir.py
```

O script identifica os acidentes plotados como "rua" cujo texto sugere um cruzamento e mostra um caso por vez — o trecho da matéria com a menção destacada, o ponto atual no mapa e a notícia original — para você confirmar ou corrigir a coordenada. Cada caso revisado é marcado (`corrigido_manual`) e não volta a aparecer nem é sobrescrito pelo pipeline automático.

> Automação leva a maior parte dos dados a um bom nível de precisão; os casos que mudam uma decisão real de política pública (ex.: onde priorizar um semáforo) passam por essa checagem manual antes de virar destaque.

## Stack

- **Coleta:** `requests` + `BeautifulSoup`
- **Dados:** `DuckDB` (banco analítico embutido) + `pandas`
- **Geocodificação:** `geopy` (Nominatim) + Overpass API
- **App:** `Streamlit` + `folium`
- **Testes:** `pytest`

## App online

Versão pública (sempre no ar): **https://acidentes-transito-pf.streamlit.app/**

## Rodando localmente

O repositório já inclui o banco de dados (`data/acidentes.duckdb`), então o app
roda direto após clonar — não é preciso coletar nada para visualizar.

```bash
git clone git@github.com:henriquereolonpain-sys/acidentes-transito-passo-fundo.git
cd acidentes-transito-passo-fundo
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

O app abre em `http://localhost:8501`.

### Reconstruir os dados do zero (opcional)

```bash
python runs/run_pipeline.py    # scraping + geocoding + dedup + confiança
python runs/run_prf.py         # baixa e integra os dados da PRF (via gdown)
python runs/run_diario.py      # atualização incremental (só o que é novo)
```

## Estrutura

```
scrapers/        coletores por fonte (rdplanalto, uirapuru, gzh, prf)
pipeline/        extração, geocoding, storage, dedup, enriquecimento, confiança
app/             dashboard Streamlit
tests/           testes das funções de extração e classificação
runs/            scripts de orquestração (run_*.py, corrigir.py)
checks/          scripts avulsos de inspeção/debug (check_*.py, não versionados)
```

## Testes

```bash
python -m pytest tests/ -v
```

Cobrem as partes mais frágeis — extração de localização, classificação de severidade e parsing de vítimas/hora/km em português (incluindo números por extenso).

## Roadmap

- [ ] Pedido de informação à Brigada Militar (dados de acidentes com vítima/óbito na área urbana — ver [nota acima](#por-que-não-usamos-dados-oficiais-do-município))
- [ ] Integrar base de acidentes urbanos da Secretaria de Segurança de Passo Fundo, quando o Boletim de Ocorrências digital estiver disponível
- [ ] Melhorar o casamento de acidentes entre fontes diferentes
- [x] Atualização automática diária

## Licença

Projeto de portfólio / uso educacional. As notícias e dados pertencem às respectivas fontes, sempre creditadas com link para o original.
