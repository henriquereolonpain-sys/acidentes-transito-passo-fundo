"""
Reclassifica a severidade de TODOS os artigos (sem baixar nada):
1. Re-aplica o classificador por palavra-chave no título (fonte primária)
2. Re-extrai n_mortos/n_feridos de título + teaser
3. Sobe a severidade quando os números confirmam (mortos>0 -> fatal, feridos>0 -> grave)
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

import duckdb
from scrapers.rdplanalto import classificar_severidade
from pipeline.body_scraper import (
    _extrair_contagem, _RE_MORTOS, _RE_MORTE_SINGULAR, _RE_FERIDOS, _RE_FERIDO_SINGULAR
)
from pipeline.storage import DB_PATH

con = duckdb.connect(str(DB_PATH))
rows = con.execute("SELECT id, titulo, teaser, severidade, categoria FROM acidentes").fetchall()
logger.info(f"Reprocessando {len(rows)} artigos...")

atualizados = 0
mudou_sev = 0

for id, titulo, teaser, sev_atual, categoria in rows:
    texto = (titulo or "") + ". " + (teaser or "")

    # 1. Classificação base por palavra-chave do título
    nova_sev = classificar_severidade(titulo or "")
    # preserva fiscalizacao já marcada se o título for ambíguo
    if sev_atual == "fiscalizacao" and nova_sev == "colisao":
        nova_sev = "fiscalizacao"

    # 2. Extrai contagens
    n_mortos = _extrair_contagem(_RE_MORTOS, _RE_MORTE_SINGULAR, texto)
    n_feridos = _extrair_contagem(_RE_FERIDOS, _RE_FERIDO_SINGULAR, texto)

    # 3. Sobe pelos números reais
    if n_mortos and n_mortos > 0:
        nova_sev = "fatal"
    elif n_feridos and n_feridos > 0 and nova_sev not in ("fatal",):
        nova_sev = "grave"

    campos = []
    vals = []
    if n_mortos is not None:
        campos.append("n_mortos = ?"); vals.append(n_mortos)
    if n_feridos is not None:
        campos.append("n_feridos = ?"); vals.append(n_feridos)
    if nova_sev != sev_atual:
        campos.append("severidade = ?"); vals.append(nova_sev)
        mudou_sev += 1

    if campos:
        vals.append(id)
        con.execute(f"UPDATE acidentes SET {', '.join(campos)} WHERE id = ?", vals)
        atualizados += 1

con.close()
logger.info(f"Atualizados: {atualizados} | Severidade mudou: {mudou_sev}")

con = duckdb.connect(str(DB_PATH))
print("\n=== Severidade após reclassificação ===")
for sev, n in con.execute("SELECT severidade, COUNT(*) FROM acidentes GROUP BY severidade ORDER BY 2 DESC").fetchall():
    print(f"  {sev}: {n}")
con.close()
