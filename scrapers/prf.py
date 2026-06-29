"""
Download e filtragem dos dados abertos da PRF.
Fonte: https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-da-prf

Filtra acidentes dentro do município de Passo Fundo (e cidades vizinhas da região).
"""

import logging
import zipfile
from io import BytesIO
from pathlib import Path

import gdown
import pandas as pd

logger = logging.getLogger(__name__)

# IDs dos arquivos Google Drive — "Agrupados por ocorrência"
GDRIVE_IDS = {
    2015: "1DyqR5FFcwGsamSag-fGm13feQt0Y-3Da",
    2016: "16qooQl_ySoW61CrtsBbreBVNPYlEkoYm",
    2017: "1HPLWt5f_l4RIX3tKjI4tUXyZOev52W0N",
    2018: "1cM4IgGMIiR-u4gBIH5IEe3DcvBvUzedi",
    2019: "1pN3fn2wY34GH6cY-gKfbxRJJBFE0lb_l",
    2020: "1esu6IiH5TVTxFoedv6DBGDd01Gvi8785",
    2021: "12xH8LX9aN2gObR766YN3cMcuycwyCJDz",
    2022: "1PRQjuV5gOn_nn6UNvaJyVURDIfbSAK4-",
    2023: "1-WO3SfNrwwZ5_l7fRTiwBKRw7mi1-HUq",
    2024: "14lB0vqMFkaZj8HZ44b0njYgxs9nAN8KO",
    2025: "1-G3MdmHBt6CprDwcW99xxC4BZ2DU5ryR",
}

# Municípios do território de interesse (Passo Fundo + cidades cujos BRs cruzam a região)
MUNICIPIOS_INTERESSE = {
    "PASSO FUNDO", "COXILHA", "MATO CASTELHANO", "ERNESTINA",
    "VILA MARIA", "SAO DOMINGOS DO SUL",
}

CACHE_DIR = Path(__file__).parent.parent / "data" / "prf_cache"

# Colunas relevantes (nomes variam levemente entre anos)
_COL_MAP = {
    "id":                   "id_prf",
    "data_inversa":         "data_acidente",
    "horario":              "hora_acidente",
    "uf":                   "uf",
    "br":                   "br",
    "km":                   "km",
    "municipio":            "municipio",
    "causa_acidente":       "causa_acidente",
    "tipo_acidente":        "tipo_acidente",
    "classificacao_acidente": "classificacao",
    "fase_dia":             "fase_dia",
    "uso_solo":             "uso_solo",
    "mortos":               "mortos",
    "feridos_graves":       "feridos_graves",
    "feridos_leves":        "feridos_leves",
    "veiculos":             "veiculos",
    "latitude":             "latitude",
    "longitude":            "longitude",
}


def _baixar_csv(ano: int) -> Path:
    """Baixa o CSV do ano para o cache local. Descompacta ZIP se necessário."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    csv_destino = CACHE_DIR / f"prf_{ano}.csv"

    if csv_destino.exists():
        logger.info(f"PRF {ano}: usando cache em {csv_destino}")
        return csv_destino

    file_id = GDRIVE_IDS.get(ano)
    if not file_id:
        raise ValueError(f"Sem ID Google Drive para o ano {ano}")

    url = f"https://drive.google.com/uc?id={file_id}"
    logger.info(f"PRF {ano}: baixando de Google Drive...")

    # Baixa como arquivo temporário (pode ser ZIP ou CSV)
    tmp = CACHE_DIR / f"prf_{ano}.tmp"
    gdown.download(url, str(tmp), quiet=False)

    if not tmp.exists():
        raise RuntimeError(f"Download falhou para PRF {ano}")

    # Detecta se é ZIP
    with open(tmp, "rb") as f:
        magic = f.read(4)

    if magic[:2] == b"PK":
        logger.info(f"PRF {ano}: descompactando ZIP...")
        with zipfile.ZipFile(tmp) as zf:
            nomes = zf.namelist()
            csv_nome = next((n for n in nomes if n.endswith(".csv")), nomes[0])
            with zf.open(csv_nome) as src, open(csv_destino, "wb") as dst:
                dst.write(src.read())
        tmp.unlink()
    else:
        tmp.rename(csv_destino)

    logger.info(f"PRF {ano}: salvo em {csv_destino} ({csv_destino.stat().st_size // 1024}KB)")
    return csv_destino


def _carregar_csv(path: Path, ano: int) -> pd.DataFrame:
    """Carrega o CSV da PRF com tratamento de encoding e separador."""
    # Tenta UTF-8 primeiro (anos recentes), depois latin1
    for enc in ["utf-8", "latin1", "iso-8859-1"]:
        try:
            df = pd.read_csv(path, sep=";", encoding=enc, dtype=str, low_memory=False)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"Não conseguiu ler {path}")

    # Normaliza nomes de colunas
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Renomeia colunas para o padrão interno
    rename = {k: v for k, v in _COL_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    df["ano"] = ano
    return df


def _limpar(df: pd.DataFrame) -> pd.DataFrame:
    """Converte tipos, filtra municípios, limpa coordenadas."""
    # Filtra pelo município
    if "municipio" in df.columns:
        df = df[df["municipio"].str.upper().isin(MUNICIPIOS_INTERESSE)].copy()

    if df.empty:
        return df

    # Converte tipos
    for col in ["mortos", "feridos_graves", "feridos_leves", "veiculos"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    if "km" in df.columns:
        df["km"] = pd.to_numeric(
            df["km"].astype(str).str.replace(",", "."), errors="coerce"
        )

    # Data: PRF muda de formato ao longo dos anos
    #   2016: DD/MM/YY  (2 dígitos)
    #   2015, 2017-2019: DD/MM/YYYY
    #   2020+: YYYY-MM-DD
    if "data_acidente" in df.columns:
        col = df["data_acidente"].astype(str).str.strip()
        parsed = pd.Series([pd.NaT] * len(col), index=col.index)
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"]:
            mask = parsed.isna()
            if not mask.any():
                break
            tentativa = pd.to_datetime(col[mask], format=fmt, errors="coerce")
            parsed[mask] = tentativa
        df["data_acidente"] = parsed
        # Remove datas claramente inválidas
        df = df[df["data_acidente"].dt.year.between(2000, 2030)]

    # Coordenadas: PRF usa vírgula como decimal
    for col in ["latitude", "longitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", ".").str.strip(),
                errors="coerce"
            )

    # Remove coords inválidas (0,0 ou fora do RS)
    if "latitude" in df.columns and "longitude" in df.columns:
        df = df[
            df["latitude"].between(-34, -27) &
            df["longitude"].between(-54, -49)
        ]

    # Severidade compatível com o nosso schema
    if "classificacao" in df.columns:
        df["severidade"] = df["classificacao"].map({
            "Com Mortos":             "fatal",
            "Com Vítimas Fatais":     "fatal",
            "Fatal":                  "fatal",
            "Com Feridos":            "grave",
            "Com Vítimas Feridas":    "grave",
            "Sem Vítimas":            "colisao",
            "Ignorado":               "colisao",
        }).fillna("colisao")

    return df


def carregar_anos(anos: list[int]) -> pd.DataFrame:
    """
    Baixa e processa os dados da PRF para os anos especificados.
    Retorna DataFrame filtrado para a região de Passo Fundo.
    """
    dfs = []
    for ano in sorted(anos):
        try:
            path = _baixar_csv(ano)
            df = _carregar_csv(path, ano)
            df = _limpar(df)
            logger.info(f"PRF {ano}: {len(df)} acidentes em Passo Fundo/região")
            dfs.append(df)
        except Exception as e:
            logger.error(f"PRF {ano}: falha — {e}")

    if not dfs:
        return pd.DataFrame()

    return pd.concat(dfs, ignore_index=True)
