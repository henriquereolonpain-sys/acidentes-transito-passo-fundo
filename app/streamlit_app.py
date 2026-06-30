"""
Dashboard — Acidentes em Passo Fundo e região, RS
Execute com: streamlit run app/streamlit_app.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import altair as alt
import folium
from folium.plugins import HeatMap, MarkerCluster
from streamlit_folium import folium_static
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
    "fatal":        {"color": "darkred",  "icon": "skull-crossbones", "label": "Fatal"},
    "grave":        {"color": "orange",   "icon": "exclamation",      "label": "Grave"},
    "colisao":      {"color": "blue",     "icon": "car-crash",        "label": "Colisão"},
    "fiscalizacao": {"color": "gray",     "icon": "shield-alt",       "label": "Fiscalização"},
}

SEVERIDADE_PESO = {"fatal": 3.0, "grave": 2.0, "colisao": 1.0, "fiscalizacao": 0.3}

SEV_COLORS = {
    "Fatal":        "#dc2626",
    "Grave":        "#ea580c",
    "Colisão":      "#3b82f6",
    "Fiscalização": "#6b7280",
}

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }

.hero {
    background: linear-gradient(135deg, #1a2e4a 0%, #2c4a6e 100%);
    border-radius: 12px;
    padding: 22px 28px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 16px;
}
.hero-icon { font-size: 36px; line-height: 1; }
.hero-title {
    font-size: 22px;
    font-weight: 700;
    color: #ffffff !important;
    margin: 0 0 5px 0;
    line-height: 1.2;
}
.hero-sub {
    font-size: 12px;
    color: rgba(255,255,255,0.65);
    margin: 0;
}
.hero-sub code {
    background: rgba(255,255,255,0.15);
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 11px;
}

.kpi {
    background: #ffffff;
    border-radius: 10px;
    padding: 14px 16px;
    border-left: 4px solid #3b82f6;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07), 0 0 0 1px rgba(0,0,0,0.04);
}
.kpi.total { border-left-color: #1d4ed8; }
.kpi.fatal { border-left-color: #dc2626; }
.kpi.grave { border-left-color: #ea580c; }
.kpi.cross { border-left-color: #047857; }
.kpi.prf   { border-left-color: #7c3aed; }
.kpi-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #6b7280;
    margin-bottom: 5px;
}
.kpi-value {
    font-size: 28px;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.1;
}

.stitle {
    font-size: 15px;
    font-weight: 600;
    color: #1e293b;
    padding-bottom: 8px;
    border-bottom: 2px solid #e2e8f0;
    margin: 4px 0 14px 0;
}

section[data-testid="stSidebar"] > div:first-child {
    background-color: #f8fafc !important;
}
section[data-testid="stSidebar"] h2 {
    font-size: 13px !important;
    font-weight: 700 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #475569 !important;
}

.footer {
    text-align: center;
    color: #94a3b8;
    font-size: 11.5px;
    padding: 16px 0 8px;
    border-top: 1px solid #e2e8f0;
    margin-top: 20px;
}

/* Insight cards */
.ic {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 12px 14px;
    height: 100%;
}
.ic-emoji { font-size: 20px; margin-bottom: 5px; }
.ic-text  { font-size: 12px; color: #374151; line-height: 1.5; }
.ic-text b { color: #0f172a; }
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
    """Retorna lista de (emoji, html) com insights automáticos dos dados filtrados."""
    insights = []
    DIAS = {0: "segunda", 1: "terça", 2: "quarta", 3: "quinta",
            4: "sexta", 5: "sábado", 6: "domingo"}

    # Dia da semana com mais acidentes (notícias)
    if not df.empty:
        datas_validas = df["data_publicacao"].dropna()
        if not datas_validas.empty:
            dia = datas_validas.dt.dayofweek.value_counts().idxmax()
            n_dia = datas_validas.dt.dayofweek.value_counts().iloc[0]
            insights.append(("📅", f"<b>{DIAS[dia].capitalize()}</b> é o dia com mais registros de acidentes ({n_dia})"))

    # Hora de pico (PRF)
    if df_prf is not None and not df_prf.empty and "hora_acidente" in df_prf.columns:
        horas = pd.to_numeric(df_prf["hora_acidente"].astype(str).str[:2], errors="coerce").dropna()
        if not horas.empty:
            h = int(horas.value_counts().idxmax())
            insights.append(("🕐", f"Pico nas rodovias federais: <b>{h:02d}h–{h+1:02d}h</b>"))

    # Taxa de fatalidade
    if len(df) > 0:
        n_fatal = len(df[df["severidade"] == "fatal"])
        taxa = n_fatal / len(df) * 100
        insights.append(("⚠️", f"<b>{taxa:.0f}%</b> dos acidentes registrados resultaram em morte"))

    # BR mais perigosa
    if df_prf is not None and not df_prf.empty and "br" in df_prf.columns:
        br_mais = str(df_prf["br"].value_counts().idxmax())
        n_br = df_prf["br"].value_counts().iloc[0]
        fatais_br = len(df_prf[(df_prf["br"].astype(str) == br_mais) & (df_prf["severidade"] == "fatal")])
        insights.append(("🛣️", f"<b>BR-{br_mais}</b>: rodovia com mais acidentes ({n_br} registros, {fatais_br} fatais)"))

    # Cruzamento mais perigoso
    if "loc_tipo" in df.columns:
        df_c = df[df["loc_tipo"] == "cruzamento"]
        if not df_c.empty:
            top = df_c["loc_endereco"].value_counts()
            nome = top.index[0]
            nome_curto = nome[:45] + "…" if len(nome) > 45 else nome
            insights.append(("📍", f"Cruzamento crítico: <b>{nome_curto}</b> ({top.iloc[0]} acidentes)"))

    return insights


def render_mapa(df: pd.DataFrame, modo: str, df_prf: pd.DataFrame = None) -> folium.Map:
    center = [df["latitude"].mean(), df["longitude"].mean()] if not df.empty else PASSO_FUNDO_CENTER
    m = folium.Map(location=center, zoom_start=12, tiles="CartoDB positron")

    if df.empty:
        return m

    if modo == "Heatmap (ponderado por gravidade)":
        heat_data = [[r["latitude"], r["longitude"], r["peso"]] for _, r in df.iterrows()]
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
        folium.LayerControl().add_to(m)

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
        folium.LayerControl(collapsed=False).add_to(m)

    return m


# ── Hero header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <span class="hero-icon">🚦</span>
  <div>
    <p class="hero-title">Mapa de Acidentes — Passo Fundo e região, RS</p>
    <p class="hero-sub">
      Henrique Pain &nbsp;|&nbsp; rdplanalto.com · GZH · Uirapuru · PRF (dados abertos)
      &nbsp;|&nbsp; Atualizar: <code>python run_pipeline.py</code>
    </p>
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
            "De", value=data_min.date() if pd.notna(data_min) else date(2020, 1, 1)
        )
    with col_d2:
        data_fim = st.date_input(
            "Até", value=data_max.date() if pd.notna(data_max) else date.today()
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
        if st.checkbox(cfg["label"], value=(sev != "fiscalizacao"), key=f"sev_{sev}"):
            severidades_sel.append(sev)

    modo_mapa = st.radio(
        "Visualização",
        ["Heatmap (ponderado por gravidade)", "Marcadores por severidade"],
        index=0,
    )

    mostrar_prf = st.toggle(
        "Camada PRF (BR federais)", value=True,
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
    if st.button("Limpar cache"):
        st.cache_data.clear()
        st.rerun()

# ── Filtragem ─────────────────────────────────────────────────────────────────
df = filtrar(df_completo, data_inicio, data_fim, municipios_sel, severidades_sel)

df_prf_filtrado = None
if mostrar_prf:
    df_prf_completo = carregar_prf()
    df_prf_filtrado = filtrar_prf(df_prf_completo, data_inicio, data_fim, municipios_sel)

# ── KPIs ──────────────────────────────────────────────────────────────────────
label_count   = "Acidentes únicos" if deduplicado else "Artigos no período"
n_prf         = len(df_prf_filtrado) if df_prf_filtrado is not None else 0
n_fatais      = len(df[df["severidade"] == "fatal"])
n_graves      = len(df[df["severidade"] == "grave"])
n_cruzamentos = (
    df[df["loc_tipo"] == "cruzamento"]["loc_endereco"].nunique()
    if "loc_tipo" in df.columns else 0
)

c1, c2, c3, c4, c5 = st.columns(5)
for col, cls, lbl, val in [
    (c1, "total", label_count,          len(df)),
    (c2, "fatal", "Fatais (notícias)",  n_fatais),
    (c3, "grave", "Graves (notícias)",  n_graves),
    (c4, "cross", "Cruzamentos mapeados", n_cruzamentos),
    (c5, "prf",   "PRF — BR federais",  n_prf),
]:
    col.markdown(
        f'<div class="kpi {cls}"><div class="kpi-label">{lbl}</div>'
        f'<div class="kpi-value">{val}</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── Insights automáticos ──────────────────────────────────────────────────────
insights = gerar_insights(df, df_prf_filtrado)
if insights:
    cols_i = st.columns(len(insights))
    for col, (emoji, texto) in zip(cols_i, insights):
        col.markdown(
            f'<div class="ic"><div class="ic-emoji">{emoji}</div>'
            f'<div class="ic-text">{texto}</div></div>',
            unsafe_allow_html=True,
        )
    st.markdown("<br>", unsafe_allow_html=True)

# ── Mapa ──────────────────────────────────────────────────────────────────────
st.markdown('<p class="stitle">Mapa</p>', unsafe_allow_html=True)

if df.empty and (df_prf_filtrado is None or df_prf_filtrado.empty):
    st.info("Nenhum dado para os filtros selecionados.")
else:
    mapa = render_mapa(df, modo_mapa, df_prf=df_prf_filtrado)
    folium_static(mapa, width=1100, height=520)

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
        cruzamentos = cruzamentos.sort_values(["Fatais", "Total"], ascending=False).head(15)
        cruzamentos.index.name = "Local"
        st.dataframe(cruzamentos.reset_index(), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum cruzamento com coordenada nos filtros atuais.")
except Exception as e:
    st.error(f"Erro no ranking: {e}")

st.markdown("---")

# ── Gráficos ──────────────────────────────────────────────────────────────────
col_sev, col_mes = st.columns(2)

with col_sev:
    st.markdown('<p class="stitle">Por severidade</p>', unsafe_allow_html=True)
    try:
        label_map = {k: v["label"] for k, v in SEVERIDADE_CONFIG.items()}
        contagem = df["severidade"].value_counts().rename(index=label_map).reset_index()
        contagem.columns = ["Severidade", "Acidentes"]
        if not contagem.empty:
            chart_sev = (
                alt.Chart(contagem)
                .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                .encode(
                    x=alt.X("Severidade:N", sort="-y", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("Acidentes:Q", title=""),
                    color=alt.Color("Severidade:N",
                        scale=alt.Scale(domain=list(SEV_COLORS.keys()),
                                        range=list(SEV_COLORS.values())),
                        legend=None),
                    tooltip=["Severidade:N", "Acidentes:Q"],
                ).properties(height=260)
            )
            st.altair_chart(chart_sev, use_container_width=True)
    except Exception as e:
        st.error(f"Erro: {e}")

with col_mes:
    st.markdown('<p class="stitle">Por mês</p>', unsafe_allow_html=True)
    try:
        df_tempo = df[df["data_publicacao"].notna()].copy()
        df_tempo["mes"] = df_tempo["data_publicacao"].dt.to_period("M").astype(str)
        por_mes = df_tempo.groupby("mes").size().reset_index()
        por_mes.columns = ["Mês", "Acidentes"]
        if not por_mes.empty:
            chart_mes = (
                alt.Chart(por_mes)
                .mark_bar(color="#2563eb", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                .encode(
                    x=alt.X("Mês:O", axis=alt.Axis(labelAngle=-45, labelLimit=60)),
                    y=alt.Y("Acidentes:Q", title=""),
                    tooltip=["Mês:N", "Acidentes:Q"],
                ).properties(height=260)
            )
            st.altair_chart(chart_mes, use_container_width=True)
    except Exception as e:
        st.error(f"Erro: {e}")

# ── PRF: heatmap dia × hora  +  top causas ───────────────────────────────────
if df_prf_filtrado is not None and not df_prf_filtrado.empty:
    st.markdown("---")
    col_heat, col_causa = st.columns([6, 4])

    with col_heat:
        st.markdown('<p class="stitle">Quando acontecem — PRF (dia × hora)</p>', unsafe_allow_html=True)
        try:
            DIAS_LABEL = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}
            df_h = df_prf_filtrado.copy()
            df_h["hora"] = pd.to_numeric(df_h["hora_acidente"].astype(str).str[:2], errors="coerce")
            df_h["dia"]  = df_h["data_acidente"].dt.dayofweek.map(DIAS_LABEL)
            heat = (df_h.dropna(subset=["hora", "dia"])
                       .groupby(["dia", "hora"]).size().reset_index(name="Acidentes"))
            if not heat.empty:
                chart_heat = (
                    alt.Chart(heat)
                    .mark_rect(cornerRadius=2)
                    .encode(
                        x=alt.X("hora:O", title="Hora", axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("dia:O",
                                sort=["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"],
                                title=""),
                        color=alt.Color("Acidentes:Q",
                                        scale=alt.Scale(scheme="orangered"),
                                        legend=alt.Legend(title="Acidentes")),
                        tooltip=["dia:N", "hora:O", "Acidentes:Q"],
                    ).properties(height=200)
                )
                st.altair_chart(chart_heat, use_container_width=True)
        except Exception as e:
            st.error(f"Erro heatmap: {e}")

    with col_causa:
        st.markdown('<p class="stitle">Principais causas — PRF</p>', unsafe_allow_html=True)
        try:
            causas = (df_prf_filtrado["causa_acidente"]
                      .value_counts().head(8).reset_index())
            causas.columns = ["Causa", "Acidentes"]
            if not causas.empty:
                chart_causa = (
                    alt.Chart(causas)
                    .mark_bar(color="#7c3aed",
                              cornerRadiusTopRight=4,
                              cornerRadiusBottomRight=4)
                    .encode(
                        x=alt.X("Acidentes:Q", title=""),
                        y=alt.Y("Causa:N", sort="-x", title=""),
                        tooltip=["Causa:N", "Acidentes:Q"],
                    ).properties(height=240)
                )
                st.altair_chart(chart_causa, use_container_width=True)
        except Exception as e:
            st.error(f"Erro causas: {e}")

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
""", unsafe_allow_html=True)
