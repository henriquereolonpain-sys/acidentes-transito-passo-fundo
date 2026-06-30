"""
Re-geocodifica acidentes em rodovias federais (BR) que têm km extraído,
usando a referência km->coordenada da PRF. Move o ponto do centro da via
para a posição exata do km. Pure local lookup — sem rede.
"""
import logging
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

import duckdb
from pipeline.km_ref import construir_referencia, buscar_coord
from pipeline.geocoder import _RE_BR, _parse_km
from pipeline.storage import DB_PATH

# Garante que a referência existe
con = duckdb.connect(str(DB_PATH))
existe = con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name='prf_km_ref'").fetchone()[0]
con.close()
if not existe:
    logger.info("Construindo referência km...")
    construir_referencia()

con = duckdb.connect(str(DB_PATH))
rows = con.execute("""
    SELECT id, loc_endereco, km_rodovia, latitude, longitude
    FROM acidentes
    WHERE loc_tipo = 'rodovia'
      AND km_rodovia IS NOT NULL
      AND loc_endereco LIKE '%BR-%'
""").fetchall()

logger.info(f"Acidentes BR com km para reposicionar: {len(rows)}")

movidos = 0
for id, endereco, km_rodovia, lat_old, lon_old in rows:
    m_br = _RE_BR.search(endereco or "")
    km = _parse_km(km_rodovia)
    if not m_br or km is None:
        continue
    coords = buscar_coord(m_br.group(1), km)
    if coords:
        con.execute("UPDATE acidentes SET latitude = ?, longitude = ? WHERE id = ?",
                    [coords[0], coords[1], id])
        movidos += 1

con.close()
logger.info(f"Reposicionados com km exato: {movidos}/{len(rows)}")
