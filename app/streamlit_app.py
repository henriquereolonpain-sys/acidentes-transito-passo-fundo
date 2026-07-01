"""
Dashboard — Acidentes em Passo Fundo e região, RS
Execute com: streamlit run app/streamlit_app.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import streamlit.components.v1 as components
import folium
from folium.plugins import HeatMap, MarkerCluster
import pandas as pd
from datetime import date

from pipeline import storage

st.set_page_config(
    page_title="Acidentes — Passo Fundo",
    page_icon="🚦",
    layout="wide",
)

PASSO_FUNDO_CENTER = [-28.2576, -52.4086]

SEVERIDADE_CONFIG = {
    "fatal":   {"color": "darkred", "icon": "skull-crossbones", "label": "Fatal"},
    "grave":   {"color": "orange",  "icon": "exclamation",      "label": "Grave"},
    "colisao": {"color": "blue",    "icon": "car-crash",        "label": "Colisão"},
}

SEVERIDADE_PESO = {"fatal": 3.0, "grave": 2.0, "colisao": 1.0}

SEV_COLORS = {
    "Fatal":   "#dc2626",
    "Grave":   "#ea580c",
    "Colisão": "#3b82f6",
}

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

/* ── Tema geral ────────────────────────────────────────────────────────────── */
.stApp { background: #E9E6DF; }
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif !important; }

.block-container {
    padding-top: 2.2rem !important;
    padding-bottom: 1rem !important;
    max-width: 100% !important;
}
/* esconde o cabeçalho translúcido do Streamlit que cobre o topbar */
header[data-testid="stHeader"] { background: transparent; }

/* ── Topbar ────────────────────────────────────────────────────────────────── */
.topbar {
    height: 58px;
    background: #FBF9F4;
    border: 1px solid #E3DECF;
    border-radius: 8px;
    margin-bottom: 16px;
    display: flex;
    align-items: stretch;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.topbar-stripe {
    width: 10px;
    flex-shrink: 0;
    background: repeating-linear-gradient(-45deg, #F2C200 0 12px, #15140F 12px 24px);
}
.topbar-inner {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 22px;
}
.tb-title {
    font-family: 'Archivo', sans-serif;
    font-weight: 800;
    font-size: 17px;
    letter-spacing: -0.01em;
    color: #1A1813;
}
.tb-sub {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11.5px;
    color: #8a847a;
    margin-left: 12px;
}
.tb-src {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: #a39d92;
    letter-spacing: 0.03em;
}

/* ── Sidebar como "filter rail" ────────────────────────────────────────────── */
section[data-testid="stSidebar"] > div:first-child {
    background-color: #F5F2EA !important;
    border-right: 1px solid #E3DECF;
}
section[data-testid="stSidebar"] .block-container { padding-top: 1.2rem !important; }
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    color: #9a948a !important;
}
/* rótulo dos widgets em mono/uppercase */
section[data-testid="stSidebar"] label p {
    font-size: 13px !important;
    color: #3a352d !important;
}
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 11px !important;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #9a948a !important;
}
/* inputs creme */
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] [data-baseweb="input"],
section[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: #ffffff !important;
    border-color: #E0DACB !important;
    color: #3a352d !important;
}
/* pills do multiselect em preto/dourado */
section[data-testid="stSidebar"] [data-baseweb="tag"] {
    background: #15140F !important;
    color: #F2C200 !important;
}
section[data-testid="stSidebar"] [data-baseweb="tag"] span { color: #F2C200 !important; }
/* toggle e radio em dourado */
section[data-testid="stSidebar"] [data-testid="stCheckbox"] label,
section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: #1A1813 !important;
}
.stMetric { font-family: 'Archivo', sans-serif; }

/* ── Faixa de KPIs (acima do mapa) ─────────────────────────────────────────── */
.kpi-strip {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    margin-bottom: 14px;
}
.kpi-card {
    background: #FBF9F4;
    border: 1px solid #E3DECF;
    border-left: 3px solid #2F6FED;
    border-radius: 6px;
    padding: 10px 13px;
}
.kpi-card-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #8a847a;
}
.kpi-card-value {
    font-family: 'Archivo', sans-serif;
    font-weight: 800;
    font-size: 26px;
    color: #1A1813;
    line-height: 1.1;
    margin-top: 3px;
}

/* ── Faixa de insights (abaixo do mapa) ────────────────────────────────────── */
.ins-strip {
    display: flex;
    gap: 10px;
    margin-top: 14px;
}
.ins-card {
    flex: 1;
    background: #FBF9F4;
    border: 1px solid #E3DECF;
    border-radius: 8px;
    padding: 10px 13px;
}
.ins-main  { font-size: 12.5px; color: #3a352d; line-height: 1.35; }
.ins-main b { font-weight: 600; color: #1A1813; }
.ins-sub   { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #9a948a; margin-top: 2px; }

/* ── Moldura do mapa (iframe do folium) ────────────────────────────────────── */
[data-testid="stIFrame"] {
    border: 1px solid #E3DECF;
    border-radius: 9px;
    box-shadow: 0 18px 44px -30px rgba(0,0,0,.32);
    background: #FBF9F4;
    overflow: hidden;
}

/* ── Cards de gráficos ─────────────────────────────────────────────────────── */
.charts-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 22px;
}
.chart-card {
    border: 1px solid #E3DECF;
    border-radius: 9px;
    background: #FBF9F4;
    overflow: hidden;
    box-shadow: 0 14px 36px -30px rgba(0,0,0,.28);
}
.chart-head {
    padding: 13px 18px;
    border-bottom: 1px solid #ECE7DA;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #6f6a60;
}
.chart-body { padding: 20px 22px 18px; }
.chart-empty {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: #a39d92;
    padding: 30px 0;
    text-align: center;
}

/* ── Tabela de cruzamentos ─────────────────────────────────────────────────── */
.xtable-card {
    border: 1px solid #E3DECF;
    border-radius: 9px;
    overflow: hidden;
    background: #FBF9F4;
    box-shadow: 0 14px 36px -30px rgba(0,0,0,.28);
}
.xtable { width: 100%; border-collapse: collapse; }
.xtable thead th {
    background: #F0EBDF;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10.5px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #9a948a;
    font-weight: 500;
    padding: 11px 18px;
    text-align: right;
    border-bottom: 1px solid #E3DECF;
}
.xtable thead th.xt-loc { text-align: left; }
.xtable tbody td {
    padding: 12px 18px;
    font-size: 13px;
    text-align: right;
    border-bottom: 1px solid #EEE9DD;
    color: #3a352d;
}
.xtable tbody tr:last-child td { border-bottom: none; }
.xtable tbody tr:nth-child(even) td { background: #F8F4EB; }
.xtable td.xt-loc {
    text-align: left;
    color: #8a5a2c;
    font-weight: 500;
    font-family: 'IBM Plex Sans', sans-serif;
}
.xtable td.xt-num  { font-family: 'IBM Plex Mono', monospace; }
.xtable td.xt-zero { font-family: 'IBM Plex Mono', monospace; color: #c2bcae; }

/* ── Rodapé de fontes ──────────────────────────────────────────────────────── */
.footer {
    text-align: center;
    color: #a39d92;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    padding: 18px 0 6px;
    border-top: 1px solid #E3DECF;
    margin-top: 20px;
}
.footer b { color: #8a847a; font-weight: 500; }

/* ── Crédito do autor (amarelo queimado, esmaecido, bem pequeno) ────────────── */
.author-credit {
    text-align: center;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10.5px;
    letter-spacing: 0.03em;
    color: #a8791f;
    opacity: 0.62;
    padding: 4px 0 22px;
    line-height: 1.7;
}
.author-credit .ac-name { font-weight: 500; }
.author-credit a { color: #a8791f; text-decoration: none; }
.author-credit a:hover { text-decoration: underline; }
.author-credit .ac-sep { opacity: 0.5; margin: 0 7px; }

.stitle {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    font-weight: 500;
    color: #9a948a;
    margin: 6px 0 12px 0;
}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def carregar_dados(deduplicado: bool = True) -> pd.DataFrame:
    registros = storage.carregar_para_mapa(deduplicado=deduplicado)
    if not registros:
        return pd.DataFrame()
    df = pd.DataFrame(registros)
    df["data_publicacao"] = pd.to_datetime(df["data_publicacao"], errors="coerce")
    if "severidade" not in df.columns:
        df["severidade"] = "colisao"
    if "municipio" not in df.columns:
        df["municipio"] = "Passo Fundo"
    df["peso"] = df["severidade"].map(SEVERIDADE_PESO).fillna(1.0)
    return df


@st.cache_data(ttl=300)
def carregar_prf() -> pd.DataFrame:
    registros = storage.carregar_prf_para_mapa()
    if not registros:
        return pd.DataFrame()
    df = pd.DataFrame(registros)
    df["data_acidente"] = pd.to_datetime(df["data_acidente"], errors="coerce")
    df["peso"] = df["severidade"].map(SEVERIDADE_PESO).fillna(1.0)
    return df


def filtrar_prf(df, data_inicio, data_fim, municipios_sel=None) -> pd.DataFrame:
    if df.empty:
        return df
    mask = pd.Series([True] * len(df), index=df.index)
    if data_inicio:
        mask &= df["data_acidente"].dt.date >= data_inicio
    if data_fim:
        mask &= df["data_acidente"].dt.date <= data_fim
    if municipios_sel:
        municipios_upper = [m.upper() for m in municipios_sel]
        mask &= df["municipio"].str.upper().isin(municipios_upper)
    return df[mask]


def filtrar(df, data_inicio, data_fim, municipios, severidades) -> pd.DataFrame:
    mask = pd.Series([True] * len(df), index=df.index)
    if data_inicio:
        mask &= df["data_publicacao"].dt.date >= data_inicio
    if data_fim:
        mask &= df["data_publicacao"].dt.date <= data_fim
    if municipios:
        mask &= df["municipio"].isin(municipios)
    if severidades:
        mask &= df["severidade"].isin(severidades)
    return df[mask]


def _tooltip_html(row) -> str:
    sev = row.get("severidade", "colisao")
    cfg = SEVERIDADE_CONFIG.get(sev, {})
    cor = SEV_COLORS.get(cfg.get("label", ""), "#3b82f6")
    titulo = row["titulo"][:70] + ("..." if len(row["titulo"]) > 70 else "")
    n = int(row.get("n_artigos", 1))
    fontes = f"{n} fontes" if n > 1 else "1 fonte"
    data_str = row["data_publicacao"].strftime("%d/%m/%Y") if pd.notna(row["data_publicacao"]) else ""
    return f"""
    <div style="font-family:'Inter',sans-serif;max-width:240px;padding:2px">
      <div style="font-weight:600;font-size:12px;line-height:1.3;margin-bottom:4px">{titulo}</div>
      <div style="font-size:11px;color:{cor};font-weight:600">{cfg.get('label','')}</div>
      <div style="font-size:10px;color:#6b7280;margin-top:2px">{data_str} · {fontes}</div>
      <div style="font-size:10px;color:#9ca3af;margin-top:3px;font-style:italic">clique para ver as matérias</div>
    </div>
    """


def _popup_html(row) -> str:
    sev_label = SEVERIDADE_CONFIG.get(row.get("severidade", ""), {}).get("label", "—")
    data_str = row["data_publicacao"].strftime("%d/%m/%Y") if pd.notna(row["data_publicacao"]) else "—"

    urls = str(row.get("todas_urls", row["url"])).split("||")
    titulos = str(row.get("todos_titulos", row["titulo"])).split("||")
    pares = list(zip(urls, titulos))

    if len(pares) == 1:
        fontes_html = f'<a href="{pares[0][0]}" target="_blank" style="font-size:11px">Ver notícia</a>'
    else:
        links = "".join(
            f'<li><a href="{u}" target="_blank" style="font-size:11px">'
            f'{t[:55]}{"..." if len(t)>55 else ""}</a></li>'
            for u, t in pares
        )
        fontes_html = (
            f"<b>{len(pares)} matérias sobre este acidente:</b>"
            f"<ul style='margin:2px 0 0 12px;padding:0'>{links}</ul>"
        )

    return f"""
    <div style="min-width:240px;max-width:320px">
      <b style="font-size:13px">{row['titulo'][:80]}{'...' if len(row['titulo'])>80 else ''}</b>
      <hr style="margin:4px 0">
      <small>
        <b>Severidade:</b> {sev_label}<br>
        <b>Local:</b> {row.get('loc_endereco','—')}<br>
        <b>Município:</b> {row.get('municipio','—')}<br>
        <b>Data:</b> {data_str}<br>
      </small>
      <div style="margin-top:4px">{fontes_html}</div>
    </div>
    """


def _popup_prf(row) -> str:
    sev = row.get("severidade", "colisao")
    sev_label = SEVERIDADE_CONFIG.get(sev, {}).get("label", "—")
    hora = str(row.get("hora_acidente", ""))[:5] or "—"
    km = f"km {row['km']:.1f}" if pd.notna(row.get("km")) else "—"
    return f"""
    <div style="min-width:220px">
      <b style="font-size:12px">PRF — BR-{row.get('br','?')} ({km})</b>
      <hr style="margin:3px 0">
      <small>
        <b>Data:</b> {row['data_acidente'].strftime('%d/%m/%Y') if pd.notna(row['data_acidente']) else '—'} {hora}<br>
        <b>Severidade:</b> {sev_label}<br>
        <b>Tipo:</b> {row.get('tipo_acidente','—')}<br>
        <b>Causa:</b> {row.get('causa_acidente','—')}<br>
        <b>Mortos:</b> {int(row.get('mortos',0))} | <b>Feridos graves:</b> {int(row.get('feridos_graves',0))}<br>
        <b>Veículos:</b> {int(row.get('veiculos',0))}
      </small>
      <br><small style="color:#888">Fonte: PRF — dados abertos gov.br</small>
    </div>
    """


def gerar_insights(df: pd.DataFrame, df_prf) -> list[tuple]:
    """Retorna lista de (main_html, sub_text) com insights automáticos dos dados filtrados."""
    insights = []
    DIAS = {0: "segunda", 1: "terça", 2: "quarta", 3: "quinta",
            4: "sexta", 5: "sábado", 6: "domingo"}

    # Dia da semana com mais acidentes (notícias)
    if not df.empty:
        datas_validas = df["data_publicacao"].dropna()
        if not datas_validas.empty:
            dia = datas_validas.dt.dayofweek.value_counts().idxmax()
            n_dia = datas_validas.dt.dayofweek.value_counts().iloc[0]
            insights.append((f"<b>{DIAS[dia].capitalize()}</b> é o dia com mais registros",
                             f"{n_dia} acidentes"))

    # Hora de pico (PRF)
    if df_prf is not None and not df_prf.empty and "hora_acidente" in df_prf.columns:
        horas = pd.to_numeric(df_prf["hora_acidente"].astype(str).str[:2], errors="coerce").dropna()
        if not horas.empty:
            h = int(horas.value_counts().idxmax())
            insights.append((f"Pico nas federais <b>{h:02d}h–{h+1:02d}h</b>", "por horário"))

    # Taxa de fatalidade
    if len(df) > 0:
        n_fatal = len(df[df["severidade"] == "fatal"])
        taxa = n_fatal / len(df) * 100
        insights.append((f'<b style="color:#C0392B">{taxa:.0f}%</b> resultaram em morte',
                         "dos registrados"))

    # BR mais perigosa
    if df_prf is not None and not df_prf.empty and "br" in df_prf.columns:
        br_mais = str(df_prf["br"].value_counts().idxmax())
        n_br = df_prf["br"].value_counts().iloc[0]
        fatais_br = len(df_prf[(df_prf["br"].astype(str) == br_mais) & (df_prf["severidade"] == "fatal")])
        insights.append((f"<b>BR-{br_mais}</b> · mais acidentes",
                         f"{n_br} reg · {fatais_br} fatais"))

    # Cruzamento mais perigoso
    if "loc_tipo" in df.columns:
        df_c = df[df["loc_tipo"] == "cruzamento"]
        if not df_c.empty:
            top = df_c["loc_endereco"].value_counts()
            nome = top.index[0]
            nome_curto = nome[:32] + "…" if len(nome) > 32 else nome
            insights.append((f"Cruzamento crítico: <b>{nome_curto}</b>",
                             f"{top.iloc[0]} acidentes"))

    return insights


FONT_IMPORT = (
    "<style>@import url('https://fonts.googleapis.com/css2?"
    "family=Archivo:wght@700;800&family=IBM+Plex+Mono:wght@400;500&"
    "family=IBM+Plex+Sans:wght@400;500;600&display=swap');"
    # desce os controles do topo para não ficarem sob a barra de título do card
    ".leaflet-top{top:54px;}"
    ".leaflet-top.leaflet-left{left:0;right:auto;}"
    ".leaflet-control-zoom{border:1px solid #D9D3C5 !important;border-radius:6px !important;"
    "overflow:hidden;box-shadow:0 4px 12px -6px rgba(0,0,0,.25) !important;}"
    ".leaflet-control-zoom a{color:#3a352d !important;background:#fff !important;}"
    # cantos arredondados no próprio container do mapa (moldura do card)
    ".leaflet-container{border-radius:9px;}"
    "</style>"
)


def _map_header_html(n_registros: int) -> str:
    """Barra de título do card do mapa (faixa + rótulo + contador)."""
    return (
        '<div style="position:absolute;top:0;left:0;right:0;height:46px;z-index:1200;'
        'display:flex;align-items:stretch;background:#FBF9F4;border-bottom:1px solid #ECE7DA;'
        "font-family:'IBM Plex Sans',sans-serif;overflow:hidden;border-radius:9px 9px 0 0\">"
        '<div style="width:8px;flex-shrink:0;background:repeating-linear-gradient('
        '-45deg,#F2C200 0 11px,#15140F 11px 22px)"></div>'
        '<div style="flex:1;display:flex;align-items:center;justify-content:space-between;padding:0 18px">'
        "<span style=\"font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.14em;"
        'text-transform:uppercase;color:#6f6a60">Mapa de calor · densidade de acidentes</span>'
        "<span style=\"font-family:'IBM Plex Mono',monospace;font-size:11px;color:#a39d92\">"
        f'{n_registros:,} registros no filtro</span>'
        '</div></div>'
    )


def _map_legend_html() -> str:
    """Legenda de densidade (gradiente) no canto inferior-esquerdo do mapa."""
    return (
        '<div style="position:absolute;bottom:14px;left:14px;z-index:1200;'
        'background:rgba(251,249,244,.94);border:1px solid #E3DECF;border-radius:7px;'
        'padding:10px 12px;-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px)">'
        "<div style=\"font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.1em;"
        'text-transform:uppercase;color:#8a847a;margin-bottom:7px">Densidade ponderada</div>'
        '<div style="width:120px;height:9px;border-radius:5px;'
        'background:linear-gradient(90deg,#5b6cd0,#F2C200,#E5484D)"></div>'
        "<div style=\"display:flex;justify-content:space-between;font-size:10px;color:#9a948a;"
        "margin-top:4px;font-family:'IBM Plex Mono',monospace\">"
        '<span>baixa</span><span>alta</span></div></div>'
    )


def render_mapa(df: pd.DataFrame, modo: str, df_prf: pd.DataFrame = None,
                n_registros: int = 0) -> folium.Map:
    center = [df["latitude"].mean(), df["longitude"].mean()] if not df.empty else PASSO_FUNDO_CENTER
    m = folium.Map(location=center, zoom_start=12, tiles=None, zoom_control=True)
    # tiles CARTO Voyager — tom quente, combina com a paleta creme do dashboard
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
        attr='&copy; OpenStreetMap &copy; CARTO',
        name="Voyager", control=False,
    ).add_to(m)

    if df.empty:
        return m

    if modo == "Heatmap (ponderado por gravidade)":
        heat_data = [[r["latitude"], r["longitude"], r["peso"]] for _, r in df.iterrows()]
        # inclui PRF no mesmo heatmap
        if df_prf is not None and not df_prf.empty:
            heat_data += [
                [r["latitude"], r["longitude"], r["peso"]]
                for _, r in df_prf.iterrows()
            ]
        HeatMap(heat_data, radius=20, blur=15, min_opacity=0.4,
                gradient={"0.2": "blue", "0.5": "orange", "1.0": "red"}).add_to(m)

    elif modo == "Marcadores por severidade":
        clusters = {
            sev: MarkerCluster(name=cfg["label"],
                               options={"showCoverageOnHover": False, "spiderfyOnMaxZoom": True}).add_to(m)
            for sev, cfg in SEVERIDADE_CONFIG.items()
        }
        for _, row in df.iterrows():
            sev = row.get("severidade", "colisao")
            cfg = SEVERIDADE_CONFIG.get(sev, SEVERIDADE_CONFIG["colisao"])
            folium.Marker(
                location=[row["latitude"], row["longitude"]],
                popup=folium.Popup(_popup_html(row), max_width=300),
                tooltip=_tooltip_html(row),
                icon=folium.Icon(color=cfg["color"], icon="circle", prefix="fa"),
            ).add_to(clusters[sev])

        # no modo marcadores, PRF aparece como círculos sobrepostos
        if df_prf is not None and not df_prf.empty:
            prf_group = folium.FeatureGroup(name="PRF — Rodovias Federais", show=True)
            for _, row in df_prf.iterrows():
                sev = row.get("severidade", "colisao")
                cor = {"fatal": "black", "grave": "darkred", "colisao": "cadetblue"}.get(sev, "cadetblue")
                folium.CircleMarker(
                    location=[row["latitude"], row["longitude"]],
                    radius=6 if sev == "fatal" else 4,
                    color=cor, fill=True, fill_opacity=0.8,
                    popup=folium.Popup(_popup_prf(row), max_width=280),
                    tooltip=f"PRF BR-{row.get('br','?')} | {sev}",
                ).add_to(prf_group)
            prf_group.add_to(m)

    # ── Chrome do card: fontes/estilo + barra de título + legenda ──────────────
    m.get_root().header.add_child(folium.Element(FONT_IMPORT))
    m.get_root().html.add_child(folium.Element(_map_header_html(n_registros)))
    m.get_root().html.add_child(folium.Element(_map_legend_html()))

    return m


# ── Gráficos (cards HTML no estilo do design) ─────────────────────────────────
MONO = "font-family:'IBM Plex Mono',monospace"


def _chart_card(title: str, body: str) -> str:
    return (f'<div class="chart-card"><div class="chart-head">{title}</div>'
            f'<div class="chart-body">{body}</div></div>')


def _lerp_color(t: float, c0, c1) -> str:
    r = round(c0[0] + (c1[0] - c0[0]) * t)
    g = round(c0[1] + (c1[1] - c0[1]) * t)
    b = round(c0[2] + (c1[2] - c0[2]) * t)
    return f"rgb({r},{g},{b})"


def _chart_severidade(df: pd.DataFrame) -> str:
    itens = [("Fatal", "fatal", "#D93A3F"), ("Grave", "grave", "#E08A00"),
             ("Colisão", "colisao", "#8C877C")]
    counts = {sev: int((df["severidade"] == sev).sum()) for _, sev, _ in itens}
    mx = max(counts.values()) or 1
    barras = ""
    for nome, sev, cor in itens:
        c = counts[sev]
        h = c / mx * 100
        barras += (
            '<div style="flex:1;display:flex;flex-direction:column;align-items:center;'
            'justify-content:flex-end;height:100%">'
            f'<div style="{MONO};font-size:12px;color:#3a352d;margin-bottom:6px">{c}</div>'
            f'<div style="width:100%;max-width:70px;height:{h:.0f}%;background:{cor};'
            'border-radius:4px 4px 0 0;min-height:3px"></div></div>'
        )
    rotulos = "".join(
        f'<div style="flex:1;text-align:center;{MONO};font-size:11px;color:#6b665c">{nome}</div>'
        for nome, _, _ in itens
    )
    return (
        f'<div style="height:200px;display:flex;align-items:flex-end;gap:26px">{barras}</div>'
        f'<div style="display:flex;gap:26px;margin-top:8px">{rotulos}</div>'
    )


def _chart_meses(df: pd.DataFrame) -> str:
    s = df[df["data_publicacao"].notna()].copy()
    if s.empty:
        return '<div class="chart-empty">Sem dados no período</div>'
    s["mes"] = s["data_publicacao"].dt.to_period("M")
    cont = s.groupby("mes").size().sort_index()
    vals = list(cont.values)
    anos = [p.year for p in cont.index]
    mx = max(vals) or 1
    n = len(vals)
    barras = ""
    for i, v in enumerate(vals):
        cor = "#C0392B" if i >= n - 12 else "#B79B6E"
        barras += (f'<div style="flex:1;height:{v / mx * 100:.1f}%;background:{cor};'
                   'border-radius:2px 2px 0 0;min-width:2px;min-height:2px"></div>')
    # eixo x: primeiro, ~1/3, ~2/3 e último ano
    marcas = sorted({anos[0], anos[n // 3], anos[2 * n // 3], anos[-1]})
    eixo = "".join(f"<span>{a}</span>" for a in marcas)
    return (
        '<div style="height:200px;display:flex;align-items:flex-end;gap:2px;'
        f'padding-bottom:22px;border-bottom:1px solid #E6E1D4">{barras}</div>'
        f'<div style="display:flex;justify-content:space-between;{MONO};'
        f'font-size:9.5px;color:#b3ada1;margin-top:8px">{eixo}</div>'
    )


def _chart_heat_diahora(df_prf) -> str:
    if df_prf is None or df_prf.empty:
        return '<div class="chart-empty">Sem dados PRF no período</div>'
    h = df_prf.copy()
    h["hora"] = pd.to_numeric(h["hora_acidente"].astype(str).str[:2], errors="coerce")
    h["dia"] = h["data_acidente"].dt.dayofweek
    grid = h.dropna(subset=["hora", "dia"]).groupby(["dia", "hora"]).size()
    if grid.empty:
        return '<div class="chart-empty">Sem dados PRF no período</div>'
    mx = int(grid.max()) or 1
    c0, c1 = (247, 233, 220), (176, 35, 30)
    dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    linhas = ""
    for di, dl in enumerate(dias):
        celulas = ""
        for hr in range(24):
            c = int(grid.get((di, hr), 0))
            cor = _lerp_color(c / mx, c0, c1)
            celulas += (f'<div style="flex:1;aspect-ratio:1;border-radius:2px;'
                        f'background:{cor}"></div>')
        linhas += (
            '<div style="display:flex;align-items:center;gap:5px">'
            f'<span style="width:24px;{MONO};font-size:9.5px;color:#9a948a;flex-shrink:0">{dl}</span>'
            f'<div style="flex:1;display:flex;gap:3px">{celulas}</div></div>'
        )
    horas = "".join(
        f'<span style="flex:1;text-align:center">{h if h % 3 == 0 else ""}</span>'
        for h in range(24)
    )
    eixo = (
        '<div style="display:flex;align-items:center;gap:5px;margin-top:2px">'
        '<span style="width:24px;flex-shrink:0"></span>'
        f'<div style="flex:1;display:flex;gap:3px;{MONO};font-size:8px;color:#b3ada1">{horas}</div></div>'
    )
    legenda = (
        f'<div style="display:flex;align-items:center;gap:8px;margin-top:14px;{MONO};'
        'font-size:10px;color:#8a847a"><span>1</span>'
        '<div style="width:90px;height:8px;border-radius:4px;'
        'background:linear-gradient(90deg,#F7E9DC,#E08A00,#B0231E)"></div>'
        f'<span>{mx} acidentes</span></div>'
    )
    return (f'<div style="display:flex;flex-direction:column;gap:3px">{linhas}{eixo}</div>'
            f'{legenda}')


def _tabela_cruzamentos(cruzamentos: pd.DataFrame) -> str:
    """Tabela de cruzamentos no estilo do design (card creme, local em marrom)."""
    linhas = ""
    for local, row in cruzamentos.iterrows():
        nome = str(local).split(",")[0].strip()  # só o par de vias
        def _cel(v):
            v = int(v)
            cls = "xt-zero" if v == 0 else "xt-num"
            return f'<td class="{cls}">{v}</td>'
        linhas += (
            f'<tr><td class="xt-loc">{nome}</td>'
            f'{_cel(row["Total"])}{_cel(row["Fatais"])}{_cel(row["Graves"])}</tr>'
        )
    return (
        '<div class="xtable-card"><table class="xtable">'
        '<thead><tr><th class="xt-loc">Local</th>'
        '<th>Total</th><th>Fatais</th><th>Graves</th></tr></thead>'
        f'<tbody>{linhas}</tbody></table></div>'
    )


def _chart_causas(df_prf) -> str:
    if df_prf is None or df_prf.empty or "causa_acidente" not in df_prf.columns:
        return '<div class="chart-empty">Sem dados PRF no período</div>'
    top = df_prf["causa_acidente"].value_counts().head(6)
    if top.empty:
        return '<div class="chart-empty">Sem dados PRF no período</div>'
    mx = int(top.iloc[0]) or 1
    cores = ["#B0231E", "#D14C1F", "#E08A00", "#E08A00", "#C79400", "#C79400"]
    linhas = ""
    for i, (causa, val) in enumerate(top.items()):
        nome = str(causa)
        nome = nome[:26] + "…" if len(nome) > 26 else nome
        pct = int(val) / mx * 100
        cor = cores[i] if i < len(cores) else "#C79400"
        linhas += (
            '<div style="display:flex;align-items:center;gap:12px">'
            f'<span style="width:150px;flex-shrink:0;font-size:12px;color:#3a352d;'
            f'text-align:right">{nome}</span>'
            '<div style="flex:1;height:16px;background:#F0EBDF;border-radius:3px;overflow:hidden">'
            f'<div style="width:{pct:.0f}%;height:100%;background:{cor}"></div></div>'
            f'<span style="width:28px;{MONO};font-size:11px;color:#3a352d">{int(val)}</span></div>'
        )
    return f'<div style="display:flex;flex-direction:column;gap:12px">{linhas}</div>'


# ── Topbar ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="topbar">
  <div class="topbar-stripe"></div>
  <div class="topbar-inner">
    <div>
      <span class="tb-title">Mapa de Acidentes</span>
      <span class="tb-sub">Passo Fundo e região, RS</span>
    </div>
    <div class="tb-src">rdplanalto.com · PRF (dados abertos)</div>
  </div>
</div>
""", unsafe_allow_html=True)

deduplicado = st.sidebar.toggle(
    "Deduplicar acidentes", value=True,
    help="Mostra 1 ponto por acidente real (remove cobertura múltipla do mesmo acidente)"
)

df_completo = carregar_dados(deduplicado=deduplicado)

if df_completo.empty:
    st.warning("Nenhum dado com coordenada. Execute `python run_pipeline.py` primeiro.")
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filtros")

    data_min = df_completo["data_publicacao"].min()
    data_max = df_completo["data_publicacao"].max()

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        data_inicio = st.date_input(
            "De", value=data_min.date() if pd.notna(data_min) else date(2020, 1, 1),
            format="DD/MM/YYYY",
        )
    with col_d2:
        data_fim = st.date_input(
            "Até", value=data_max.date() if pd.notna(data_max) else date.today(),
            format="DD/MM/YYYY",
        )

    municipios_disp = sorted(df_completo["municipio"].dropna().unique().tolist())
    municipios_sel = st.multiselect(
        "Município",
        options=municipios_disp,
        default=["Passo Fundo"] if "Passo Fundo" in municipios_disp else municipios_disp,
    )

    st.markdown("**Severidade**")
    severidades_sel = []
    for sev, cfg in SEVERIDADE_CONFIG.items():
        if st.checkbox(cfg["label"], value=True, key=f"sev_{sev}"):
            severidades_sel.append(sev)

    modo_mapa = st.radio(
        "Visualização",
        ["Heatmap (ponderado por gravidade)", "Marcadores por severidade"],
        index=0,
    )

    mostrar_prf = st.toggle(
        "Acidentes em rodovias", value=True,
        help="Acidentes em rodovias federais — dados oficiais PRF 2015-2024"
    )

    st.divider()
    stats = storage.estatisticas()
    prf_stats = storage.estatisticas_prf()
    st.metric("Artigos coletados", stats["total"])
    st.metric("Com coordenada", stats["com_coordenada"])
    if prf_stats["total"] > 0:
        st.metric("PRF (BR federais)", prf_stats["total"],
                  help=f"{prf_stats['ano_min']}–{prf_stats['ano_max']} | {prf_stats['fatais']} fatais")

# ── Filtragem ─────────────────────────────────────────────────────────────────
df = filtrar(df_completo, data_inicio, data_fim, municipios_sel, severidades_sel)

df_prf_filtrado = None
if mostrar_prf:
    df_prf_completo = carregar_prf()
    df_prf_filtrado = filtrar_prf(df_prf_completo, data_inicio, data_fim, municipios_sel)

# ── KPIs e insights ──────────────────────────────────────────────────────────
label_count   = "Acidentes únicos" if deduplicado else "Artigos no período"
n_prf         = len(df_prf_filtrado) if df_prf_filtrado is not None else 0
n_fatais      = len(df[df["severidade"] == "fatal"])
n_graves      = len(df[df["severidade"] == "grave"])
n_cruzamentos = (
    df[df["loc_tipo"] == "cruzamento"]["loc_endereco"].nunique()
    if "loc_tipo" in df.columns else 0
)

# faixa de KPIs (cards com borda esquerda colorida) acima do mapa
kpi_cards = [
    (label_count,      len(df),        "#2F6FED"),
    ("Fatais",         n_fatais,       "#E5484D"),
    ("Graves",         n_graves,       "#E08A00"),
    ("Cruzamentos",    n_cruzamentos,  "#1F8A5B"),
    ("PRF — federais", n_prf,          "#7A4FD0"),
]
kpi_html = '<div class="kpi-strip">'
for lbl, val, cor in kpi_cards:
    kpi_html += (
        f'<div class="kpi-card" style="border-left-color:{cor}">'
        f'<div class="kpi-card-label">{lbl}</div>'
        f'<div class="kpi-card-value">{val:,}</div></div>'
    )
kpi_html += "</div>"
st.markdown(kpi_html, unsafe_allow_html=True)

# ── Mapa (card emoldurado) ───────────────────────────────────────────────────
if df.empty and (df_prf_filtrado is None or df_prf_filtrado.empty):
    st.info("Nenhum dado para os filtros selecionados.")
else:
    mapa = render_mapa(df, modo_mapa, df_prf=df_prf_filtrado, n_registros=len(df))
    # render próprio (get_root) preserva o chrome injetado; folium_static o descartaria
    components.html(mapa.get_root().render(), height=520)

# ── Insights automáticos ─────────────────────────────────────────────────────
insights = gerar_insights(df, df_prf_filtrado)
if insights:
    ins_html = '<div class="ins-strip">'
    for main, sub in insights:
        ins_html += (
            f'<div class="ins-card"><div class="ins-main">{main}</div>'
            f'<div class="ins-sub">{sub}</div></div>'
        )
    ins_html += "</div>"
    st.markdown(ins_html, unsafe_allow_html=True)

st.markdown("---")

# ── Ranking de cruzamentos ────────────────────────────────────────────────────
st.markdown('<p class="stitle">Cruzamentos com mais acidentes</p>', unsafe_allow_html=True)
try:
    df_cruz = df[df["loc_tipo"] == "cruzamento"].copy()
    if not df_cruz.empty:
        cruz_total = df_cruz.groupby("loc_endereco").size().rename("Total")
        cruz_fatal = df_cruz[df_cruz["severidade"] == "fatal"].groupby("loc_endereco").size().rename("Fatais")
        cruz_grave = df_cruz[df_cruz["severidade"] == "grave"].groupby("loc_endereco").size().rename("Graves")
        cruzamentos = pd.concat([cruz_total, cruz_fatal, cruz_grave], axis=1).fillna(0).astype(int)
        cruzamentos = cruzamentos.sort_values(["Fatais", "Total"], ascending=False).head(12)
        cruzamentos.index.name = "Local"
        st.markdown(_tabela_cruzamentos(cruzamentos), unsafe_allow_html=True)
    else:
        st.info("Nenhum cruzamento com coordenada nos filtros atuais.")
except Exception as e:
    st.error(f"Erro no ranking: {e}")

st.markdown("---")

# ── Gráficos (cards no estilo do design) ──────────────────────────────────────
try:
    cards = [
        _chart_card("Por severidade", _chart_severidade(df)),
        _chart_card("Por mês", _chart_meses(df)),
    ]
    if df_prf_filtrado is not None and not df_prf_filtrado.empty:
        cards.append(_chart_card("Quando acontecem · PRF (dia × hora)",
                                 _chart_heat_diahora(df_prf_filtrado)))
        cards.append(_chart_card("Principais causas · PRF",
                                 _chart_causas(df_prf_filtrado)))
    st.markdown(f'<div class="charts-grid">{"".join(cards)}</div>',
                unsafe_allow_html=True)
except Exception as e:
    st.error(f"Erro nos gráficos: {e}")

# ── Tabela completa ───────────────────────────────────────────────────────────
try:
    with st.expander(f"Ver todos os acidentes ({len(df)}) — com links para as fontes"):
        colunas_exibir = ["titulo", "severidade", "municipio", "data_publicacao",
                          "loc_tipo", "loc_endereco", "n_artigos", "todas_urls"]
        colunas_exibir = [c for c in colunas_exibir if c in df.columns]
        df_exibir = df[colunas_exibir].copy()
        if "n_artigos" in df_exibir.columns:
            df_exibir["n_artigos"] = df_exibir["n_artigos"].astype(int)
        st.dataframe(df_exibir, use_container_width=True, hide_index=True)
        st.caption("Coluna 'todas_urls': URLs separadas por || quando há múltiplas matérias sobre o mesmo acidente.")
except Exception as e:
    st.error(f"Erro na tabela: {e}")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="footer">
  Dados: <b>rdplanalto.com</b> · <b>GZH</b> · <b>Uirapuru</b> · <b>PRF / dados abertos gov.br</b>
  &nbsp;|&nbsp; Geocodificação: Nominatim (OpenStreetMap) &nbsp;|&nbsp; Projeto_08
</div>
<div class="author-credit">
  <span class="ac-name">Henrique Pain</span>
  <span class="ac-sep">·</span>
  <a href="https://henriquereolonpain-sys.github.io/#home" target="_blank">portfólio</a>
  <span class="ac-sep">·</span>
  <a href="https://linkedin.com/in/henrique-pain" target="_blank">linkedin.com/in/henrique-pain</a>
  <span class="ac-sep">·</span>
  54 9 8129-3329
</div>
""", unsafe_allow_html=True)
