"""
Referência km → coordenada para rodovias federais, construída a partir dos
CSVs completos da PRF (todo o RS). Permite geocodificar "BR-285 km 220" no
ponto exato em vez do centro da rodovia.

Uso:
    construir_referencia()        # uma vez, monta a tabela prf_km_ref
    buscar_coord("285", 220.0)    # retorna (lat, lon) ou None
"""
import logging
import re
from pathlib import Path

import duckdb
import pandas as pd

from pipeline.storage import DB_PATH

logger = logging.getLogger(__name__)

CACHE = Path(__file__).parent.parent / "data" / "prf_cache"
TOLERANCIA_KM = 3.0  # distância máxima em km para considerar um ponto de referência


def _normalizar_br(valor) -> str | None:
    """'BR-285' / '285' / '0285' / '285.0' -> '285'."""
    if valor is None:
        return None
    m = re.search(r"(\d+)", str(valor))
    if not m:
        return None
    return str(int(m.group(1)))


def construir_referencia() -> int:
    """Lê os CSVs da PRF, extrai pontos do RS com br+km+coord e grava prf_km_ref."""
    frames = []
    for csv in sorted(CACHE.glob("prf_*.csv")):
        for enc in ["latin1", "utf-8"]:
            try:
                df = pd.read_csv(csv, sep=";", encoding=enc, dtype=str, low_memory=False)
                break
            except Exception:
                continue
        df.columns = [c.strip().lower() for c in df.columns]
        if not {"uf", "br", "km", "latitude", "longitude"}.issubset(df.columns):
            continue
        rs = df[df["uf"].str.upper() == "RS"][["br", "km", "latitude", "longitude"]].copy()
        frames.append(rs)

    if not frames:
        logger.warning("Nenhum CSV da PRF com colunas de coordenada — referência não criada")
        return 0

    ref = pd.concat(frames, ignore_index=True)
    ref["br"] = ref["br"].map(_normalizar_br)
    ref["km"] = pd.to_numeric(ref["km"].astype(str).str.replace(",", "."), errors="coerce")
    ref["latitude"] = pd.to_numeric(ref["latitude"].astype(str).str.replace(",", "."), errors="coerce")
    ref["longitude"] = pd.to_numeric(ref["longitude"].astype(str).str.replace(",", "."), errors="coerce")

    ref = ref.dropna(subset=["br", "km", "latitude", "longitude"])
    ref = ref[ref["latitude"].between(-34, -27) & ref["longitude"].between(-58, -49)]

    # Agrega por (br, km) inteiro: média das coordenadas — reduz ruído e tamanho
    ref["km_int"] = ref["km"].round().astype(int)
    agg = (
        ref.groupby(["br", "km_int"])
        .agg(latitude=("latitude", "mean"), longitude=("longitude", "mean"))
        .reset_index()
        .rename(columns={"km_int": "km"})
    )

    con = duckdb.connect(str(DB_PATH))
    con.execute("DROP TABLE IF EXISTS prf_km_ref")
    con.execute("""
        CREATE TABLE prf_km_ref (
            br TEXT, km INTEGER, latitude DOUBLE, longitude DOUBLE
        )
    """)
    con.execute("INSERT INTO prf_km_ref SELECT br, km, latitude, longitude FROM agg")
    con.execute("CREATE INDEX idx_km_ref ON prf_km_ref(br, km)")
    n = con.execute("SELECT COUNT(*) FROM prf_km_ref").fetchone()[0]
    con.close()

    logger.info(f"Referência km construída: {n} pontos (br, km únicos)")
    return n


def buscar_coord(br: str, km: float, tolerancia: float = TOLERANCIA_KM) -> tuple[float, float] | None:
    """Retorna a coordenada do ponto de referência mais próximo do km na BR, ou None."""
    br_norm = _normalizar_br(br)
    if br_norm is None or km is None:
        return None

    con = duckdb.connect(str(DB_PATH))
    try:
        row = con.execute("""
            SELECT latitude, longitude, ABS(km - ?) as dist
            FROM prf_km_ref
            WHERE br = ?
            ORDER BY dist
            LIMIT 1
        """, [float(km), br_norm]).fetchone()
    except duckdb.CatalogException:
        # tabela ainda não existe
        con.close()
        return None
    con.close()

    if row and row[2] <= tolerancia:
        return (row[0], row[1])
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    construir_referencia()
