"""
Agrupa artigos que cobrem o mesmo acidente real.

Lógica:
  - Artigos com mesmo loc_endereco no mesmo dia → mesmo acidente (tipo: 'inicial')
  - Artigos com mesmo loc_endereco em +1 a +14 dias → acompanhamento do mesmo acidente
  - Artigos sem loc_endereco → acidente_id próprio baseado na URL (não agrupa)

Resultado: colunas acidente_id e tipo_cobertura preenchidas em todos os registros.
"""

import hashlib
import logging
from datetime import timedelta

import duckdb

from pipeline.storage import _conexao

logger = logging.getLogger(__name__)

JANELA_MESMO_DIA = 0       # dias de tolerância para "mesmo acidente"
JANELA_ACOMPANHAMENTO = 14  # dias máximos para artigo ser acompanhamento


def _hash(texto: str) -> str:
    return hashlib.sha1(texto.encode()).hexdigest()[:12]


def deduplicar() -> dict:
    """
    Atribui acidente_id e tipo_cobertura a todos os registros.
    Retorna estatísticas do processo.
    """
    with _conexao() as con:
        # Busca todos os registros ordenados por data e local
        rows = con.execute("""
            SELECT id, data_publicacao, loc_endereco, url
            FROM acidentes
            ORDER BY loc_endereco NULLS LAST, data_publicacao NULLS LAST, id
        """).fetchall()

    # Mapeia id → (acidente_id, tipo_cobertura)
    resultado: dict[int, tuple[str, str]] = {}

    # Agrupa por loc_endereco
    grupos: dict[str, list] = {}
    sem_local: list = []

    for row_id, data_pub, loc_end, url in rows:
        if not loc_end or not data_pub:
            sem_local.append((row_id, url))
            continue
        grupos.setdefault(loc_end, []).append((row_id, data_pub, url))

    # Para cada local, ordena por data e agrupa acidentes
    for loc_end, artigos in grupos.items():
        artigos_sorted = sorted(artigos, key=lambda x: x[1])

        clusters: list[list] = []  # lista de [(id, data, url)]

        for row_id, data_pub, url in artigos_sorted:
            colocado = False
            for cluster in clusters:
                data_ref = cluster[0][1]  # data do primeiro artigo do cluster
                delta = (data_pub - data_ref).days
                if 0 <= delta <= JANELA_ACOMPANHAMENTO:
                    cluster.append((row_id, data_pub, url))
                    colocado = True
                    break
            if not colocado:
                clusters.append([(row_id, data_pub, url)])

        # Atribui acidente_id e tipo_cobertura
        for cluster in clusters:
            data_ref, url_ref = cluster[0][1], cluster[0][2]
            acid_id = _hash(f"{loc_end}|{data_ref}")

            for i, (row_id, data_pub, url) in enumerate(cluster):
                delta = (data_pub - data_ref).days
                tipo = "inicial" if delta <= JANELA_MESMO_DIA else "acompanhamento"
                # Se há múltiplos artigos no mesmo dia, todos são 'inicial'
                resultado[row_id] = (acid_id, tipo)

    # Artigos sem local: acidente_id único por URL
    for row_id, url in sem_local:
        resultado[row_id] = (_hash(url), "inicial")

    # Persiste no banco em lotes
    updates = [(acid_id, tipo, row_id) for row_id, (acid_id, tipo) in resultado.items()]

    with _conexao() as con:
        # Adiciona colunas se não existirem (idempotente)
        try:
            con.execute("ALTER TABLE acidentes ADD COLUMN acidente_id TEXT")
        except Exception:
            pass
        try:
            con.execute("ALTER TABLE acidentes ADD COLUMN tipo_cobertura TEXT")
        except Exception:
            pass

        con.executemany(
            "UPDATE acidentes SET acidente_id = ?, tipo_cobertura = ? WHERE id = ?",
            updates,
        )

    # Estatísticas
    with _conexao() as con:
        total_artigos = con.execute("SELECT COUNT(*) FROM acidentes").fetchone()[0]
        acidentes_unicos = con.execute(
            "SELECT COUNT(DISTINCT acidente_id) FROM acidentes"
        ).fetchone()[0]
        acompanhamentos = con.execute(
            "SELECT COUNT(*) FROM acidentes WHERE tipo_cobertura = 'acompanhamento'"
        ).fetchone()[0]
        multi = con.execute(
            """SELECT COUNT(*) FROM (
               SELECT acidente_id FROM acidentes
               GROUP BY acidente_id HAVING COUNT(*) > 1
            )"""
        ).fetchone()[0]

    stats = {
        "total_artigos": total_artigos,
        "acidentes_unicos": acidentes_unicos,
        "acompanhamentos": acompanhamentos,
        "acidentes_com_multiplos_artigos": multi,
    }
    logger.info(f"Deduplicacao: {total_artigos} artigos -> {acidentes_unicos} acidentes unicos")
    logger.info(f"  Acompanhamentos: {acompanhamentos} | Com múltiplos artigos: {multi}")
    return stats
