"""
Calcula um nível de confiança por acidente, agregando os artigos pelo acidente_id.

Pontuação:
  +2  confirmado por 2+ fontes distintas
  +1  tem localização geocodificada (coordenada)
  +1  tem data de publicação
  +1  internamente consistente (severidade bate com mortos/feridos)
  -2  fontes divergem no número de mortos
  -1  classificado como fatal mas sem nenhuma evidência de morte no texto

Buckets:
  >= 3  -> "alta"
  1-2   -> "media"
  <= 0  -> "baixa"
"""
import logging

import duckdb
from pipeline.storage import DB_PATH

logger = logging.getLogger(__name__)


def _garantir_colunas(con):
    for col, tipo in [("nivel_confianca", "TEXT"), ("score_confianca", "INTEGER")]:
        try:
            con.execute(f"ALTER TABLE acidentes ADD COLUMN {col} {tipo}")
        except Exception:
            pass


def calcular() -> dict:
    con = duckdb.connect(str(DB_PATH))
    _garantir_colunas(con)

    # Agrega por acidente_id: fontes, mortos divergentes, etc.
    grupos = con.execute("""
        SELECT
            acidente_id,
            COUNT(DISTINCT fonte) as n_fontes,
            COUNT(*) as n_artigos,
            MAX(CASE WHEN latitude IS NOT NULL THEN 1 ELSE 0 END) as tem_coord,
            MAX(CASE WHEN data_publicacao IS NOT NULL THEN 1 ELSE 0 END) as tem_data,
            COUNT(DISTINCT n_mortos) FILTER (WHERE n_mortos IS NOT NULL) as variacoes_mortos,
            MAX(n_mortos) as max_mortos,
            MAX(n_feridos) as max_feridos,
            -- severidade canônica do grupo (mais grave)
            MIN(CASE severidade WHEN 'fatal' THEN 1 WHEN 'grave' THEN 2
                                WHEN 'colisao' THEN 3 ELSE 4 END) as sev_rank
        FROM acidentes
        WHERE acidente_id IS NOT NULL
        GROUP BY acidente_id
    """).fetchall()

    cols = ["acidente_id", "n_fontes", "n_artigos", "tem_coord", "tem_data",
            "variacoes_mortos", "max_mortos", "max_feridos", "sev_rank"]

    buckets = {"alta": 0, "media": 0, "baixa": 0}
    updates = []

    for row in grupos:
        g = dict(zip(cols, row))
        score = 0

        # +2 multi-fonte
        if g["n_fontes"] >= 2:
            score += 2

        # +1 coordenada, +1 data
        if g["tem_coord"]:
            score += 1
        if g["tem_data"]:
            score += 1

        # consistência: severidade fatal deve ter morto; grave deve ter ferido
        sev_rank = g["sev_rank"]  # 1=fatal 2=grave 3=colisao
        max_mortos = g["max_mortos"] or 0
        max_feridos = g["max_feridos"] or 0

        if sev_rank == 1:  # fatal
            if max_mortos > 0:
                score += 1            # consistente
            elif max_feridos == 0 and max_mortos == 0:
                score -= 1            # fatal sem evidência de morte
        elif sev_rank == 2:  # grave
            if max_feridos > 0 or max_mortos > 0:
                score += 1

        # -2 divergência de mortos entre fontes
        if g["variacoes_mortos"] and g["variacoes_mortos"] > 1:
            score -= 2

        # bucket
        if score >= 3:
            nivel = "alta"
        elif score >= 1:
            nivel = "media"
        else:
            nivel = "baixa"
        buckets[nivel] += 1

        updates.append((nivel, score, g["acidente_id"]))

    con.executemany(
        "UPDATE acidentes SET nivel_confianca = ?, score_confianca = ? WHERE acidente_id = ?",
        updates,
    )
    con.close()

    logger.info(f"Confiança calculada para {len(grupos)} acidentes")
    logger.info(f"  Alta: {buckets['alta']} | Média: {buckets['media']} | Baixa: {buckets['baixa']}")
    return buckets


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    calcular()
