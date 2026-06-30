"""
Camada de persistência usando DuckDB.
Schema único: tabela 'acidentes' com todos os campos relevantes.
"""

import logging
from datetime import datetime
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "acidentes.duckdb"

_DDL_PRF = """
CREATE TABLE IF NOT EXISTS prf_acidentes (
    id_prf           TEXT,
    ano              INTEGER,
    ano_completo     BOOLEAN DEFAULT TRUE,  -- FALSE para o ano em curso (dados parciais)
    data_acidente    DATE,
    hora_acidente    TEXT,
    br               TEXT,
    km               DOUBLE,
    municipio        TEXT,
    uf               TEXT,
    causa_acidente   TEXT,
    tipo_acidente    TEXT,
    classificacao    TEXT,
    fase_dia         TEXT,
    uso_solo         TEXT,
    mortos           INTEGER,
    feridos_graves   INTEGER,
    feridos_leves    INTEGER,
    veiculos         INTEGER,
    latitude         DOUBLE,
    longitude        DOUBLE,
    severidade       TEXT,
    PRIMARY KEY (id_prf, ano)
);
"""

_DDL = """
CREATE SEQUENCE IF NOT EXISTS acidentes_id_seq;
CREATE TABLE IF NOT EXISTS acidentes (
    id               INTEGER DEFAULT nextval('acidentes_id_seq') PRIMARY KEY,
    titulo           TEXT    NOT NULL,
    url              TEXT    UNIQUE NOT NULL,
    slug             TEXT    NOT NULL,
    data_publicacao  DATE,
    fonte            TEXT    NOT NULL,
    categoria        TEXT,       -- 'transito', 'policia', etc
    severidade       TEXT,       -- 'fatal', 'grave', 'colisao', 'fiscalizacao'
    municipio        TEXT,       -- 'Passo Fundo', 'Carazinho', etc
    acidente_id      TEXT,       -- hash do acidente real (deduplicacao entre fontes)
    tipo_cobertura   TEXT,       -- 'inicial' | 'acompanhamento'
    hora_acidente    TEXT,       -- ex: '14h30' (extraído do teaser quando disponível)
    km_rodovia       TEXT,       -- ex: '220' (km na rodovia, quando disponível)
    teaser           TEXT,       -- primeiro parágrafo da matéria
    -- localização extraída do slug
    loc_tipo         TEXT,       -- 'cruzamento', 'rodovia', 'logradouro', 'bairro'
    loc_endereco     TEXT,       -- endereço montado para geocodificação
    loc_rua1         TEXT,
    loc_rua2         TEXT,
    -- resultado da geocodificação
    latitude         DOUBLE,
    longitude        DOUBLE,
    geocodificado    BOOLEAN DEFAULT FALSE,
    -- metadados
    coletado_em      TIMESTAMP DEFAULT current_timestamp
);
"""


def _conexao() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))


def inicializar():
    with _conexao() as con:
        con.execute(_DDL)
        con.execute(_DDL_PRF)
    logger.info(f"Banco inicializado em {DB_PATH}")


def inserir_noticias(noticias: list[dict]) -> int:
    """
    Insere notícias ignorando duplicatas (por URL).
    Retorna o número de registros novos inseridos.
    """
    if not noticias:
        return 0

    with _conexao() as con:
        antes = con.execute("SELECT COUNT(*) FROM acidentes").fetchone()[0]
        con.executemany(
            """
            INSERT OR IGNORE INTO acidentes
                (titulo, url, slug, data_publicacao, fonte, categoria, severidade, municipio,
                 loc_tipo, loc_endereco, loc_rua1, loc_rua2,
                 hora_acidente, km_rodovia, teaser)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    n["titulo"],
                    n["url"],
                    n["slug"],
                    n.get("data_publicacao"),
                    n["fonte"],
                    n.get("categoria"),
                    n.get("severidade"),
                    n.get("municipio"),
                    n.get("loc_tipo"),
                    n.get("loc_endereco"),
                    n.get("loc_rua1"),
                    n.get("loc_rua2"),
                    n.get("hora_acidente"),
                    n.get("km_rodovia"),
                    n.get("teaser"),
                )
                for n in noticias
            ],
        )
        depois = con.execute("SELECT COUNT(*) FROM acidentes").fetchone()[0]

    inseridos = depois - antes
    logger.info(f"Inseridos {inseridos} novos registros (total: {depois})")
    return inseridos


def buscar_urls_existentes() -> set[str]:
    """Retorna todas as URLs já coletadas no banco."""
    with _conexao() as con:
        rows = con.execute("SELECT url FROM acidentes").fetchall()
    return {r[0] for r in rows}


def buscar_sem_geocodificar() -> list[dict]:
    """Retorna registros que têm endereço mas ainda não foram geocodificados."""
    with _conexao() as con:
        rows = con.execute(
            """
            SELECT id, loc_endereco, loc_tipo, loc_rua1, loc_rua2, municipio, km_rodovia
            FROM acidentes
            WHERE loc_endereco IS NOT NULL
              AND geocodificado = FALSE
            ORDER BY id
            """
        ).fetchall()
    return [
        {
            "id": r[0],
            "loc_endereco": r[1],
            "loc_tipo": r[2],
            "loc_rua1": r[3],
            "loc_rua2": r[4],
            "municipio": r[5] or "Passo Fundo",
            "km_rodovia": r[6],
        }
        for r in rows
    ]


def atualizar_coordenadas(id: int, lat: float, lon: float):
    with _conexao() as con:
        con.execute(
            """
            UPDATE acidentes
            SET latitude = ?, longitude = ?, geocodificado = TRUE
            WHERE id = ?
            """,
            [lat, lon, id],
        )


def marcar_sem_coordenada(id: int):
    """Marca como geocodificado=TRUE mesmo sem coordenada (endereço não encontrado)."""
    with _conexao() as con:
        con.execute(
            "UPDATE acidentes SET geocodificado = TRUE WHERE id = ?",
            [id],
        )


def carregar_para_mapa(deduplicado: bool = True) -> list[dict]:
    """
    Retorna acidentes com coordenadas para o mapa.
    deduplicado=True (padrão): um registro por acidente real (mais severo/recente).
    deduplicado=False: todos os artigos.
    """
    sev_order = "CASE severidade WHEN 'fatal' THEN 1 WHEN 'grave' THEN 2 WHEN 'colisao' THEN 3 ELSE 4 END"

    if deduplicado:
        # Seleciona o artigo mais severo por acidente_id e agrega todas as URLs/fontes
        query = f"""
            SELECT
                canonical.titulo,
                canonical.url,
                canonical.fonte,
                canonical.categoria,
                canonical.severidade,
                canonical.municipio,
                canonical.data_publicacao,
                canonical.loc_tipo,
                canonical.loc_endereco,
                canonical.loc_rua1,
                canonical.loc_rua2,
                canonical.latitude,
                canonical.longitude,
                canonical.acidente_id,
                grupo.n_artigos,
                grupo.todas_urls,
                grupo.todos_titulos,
                canonical.nivel_confianca,
                grupo.max_mortos,
                grupo.max_feridos
            FROM (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY acidente_id
                        ORDER BY {sev_order}, data_publicacao DESC
                    ) as rn
                FROM acidentes
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                  AND acidente_id IS NOT NULL
            ) canonical
            JOIN (
                SELECT
                    acidente_id,
                    COUNT(*) as n_artigos,
                    STRING_AGG(url, '||' ORDER BY data_publicacao) as todas_urls,
                    STRING_AGG(titulo, '||' ORDER BY data_publicacao) as todos_titulos,
                    MAX(n_mortos) as max_mortos,
                    MAX(n_feridos) as max_feridos
                FROM acidentes
                WHERE acidente_id IS NOT NULL
                GROUP BY acidente_id
            ) grupo ON canonical.acidente_id = grupo.acidente_id
            WHERE canonical.rn = 1
            UNION ALL
            SELECT titulo, url, fonte, categoria, severidade, municipio,
                   data_publicacao, loc_tipo, loc_endereco, loc_rua1, loc_rua2,
                   latitude, longitude, url as acidente_id,
                   1 as n_artigos, url as todas_urls, titulo as todos_titulos,
                   nivel_confianca, n_mortos as max_mortos, n_feridos as max_feridos
            FROM acidentes
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
              AND acidente_id IS NULL
            ORDER BY data_publicacao DESC NULLS LAST
        """
    else:
        query = """
            SELECT titulo, url, fonte, categoria, severidade, municipio,
                   data_publicacao, loc_tipo, loc_endereco, loc_rua1, loc_rua2,
                   latitude, longitude,
                   COALESCE(acidente_id, url) as acidente_id,
                   1 as n_artigos, url as todas_urls, titulo as todos_titulos,
                   nivel_confianca, n_mortos as max_mortos, n_feridos as max_feridos
            FROM acidentes
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY data_publicacao DESC NULLS LAST
        """

    with _conexao() as con:
        rows = con.execute(query).fetchall()

    colunas = ["titulo", "url", "fonte", "categoria", "severidade", "municipio",
               "data_publicacao", "loc_tipo", "loc_endereco", "loc_rua1", "loc_rua2",
               "latitude", "longitude", "acidente_id", "n_artigos",
               "todas_urls", "todos_titulos",
               "nivel_confianca", "n_mortos", "n_feridos"]
    return [dict(zip(colunas, r)) for r in rows]


def estatisticas() -> dict:
    with _conexao() as con:
        total = con.execute("SELECT COUNT(*) FROM acidentes").fetchone()[0]
        com_coord = con.execute(
            "SELECT COUNT(*) FROM acidentes WHERE latitude IS NOT NULL"
        ).fetchone()[0]
        sem_loc = con.execute(
            "SELECT COUNT(*) FROM acidentes WHERE loc_endereco IS NULL"
        ).fetchone()[0]
    return {"total": total, "com_coordenada": com_coord, "sem_localizacao": sem_loc}


def inserir_prf(df) -> int:
    """Insere dados da PRF. Ignora duplicatas por (id_prf, ano)."""
    import pandas as pd

    if df.empty:
        return 0

    colunas = [
        "id_prf", "ano", "data_acidente", "hora_acidente", "br", "km",
        "municipio", "uf", "causa_acidente", "tipo_acidente", "classificacao",
        "fase_dia", "uso_solo", "mortos", "feridos_graves", "feridos_leves",
        "veiculos", "latitude", "longitude", "severidade",
    ]
    # Garante que só colunas existentes sejam usadas
    colunas_presentes = [c for c in colunas if c in df.columns]
    df_insert = df[colunas_presentes].copy()

    # Preenche colunas ausentes com None
    for c in colunas:
        if c not in df_insert.columns:
            df_insert[c] = None

    with _conexao() as con:
        antes = con.execute("SELECT COUNT(*) FROM prf_acidentes").fetchone()[0]
        con.execute("INSERT OR IGNORE INTO prf_acidentes SELECT * FROM df_insert")
        depois = con.execute("SELECT COUNT(*) FROM prf_acidentes").fetchone()[0]

    inseridos = depois - antes
    logger.info(f"PRF: {inseridos} novos registros (total: {depois})")
    return inseridos


def carregar_prf_para_mapa() -> list[dict]:
    """Retorna acidentes PRF com coordenadas para o mapa."""
    with _conexao() as con:
        rows = con.execute("""
            SELECT
                id_prf, ano, data_acidente, hora_acidente, br, km,
                municipio, causa_acidente, tipo_acidente,
                mortos, feridos_graves, feridos_leves, veiculos,
                latitude, longitude, severidade, uso_solo
            FROM prf_acidentes
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY data_acidente DESC
        """).fetchall()

    colunas = [
        "id_prf", "ano", "data_acidente", "hora_acidente", "br", "km",
        "municipio", "causa_acidente", "tipo_acidente",
        "mortos", "feridos_graves", "feridos_leves", "veiculos",
        "latitude", "longitude", "severidade", "uso_solo",
    ]
    return [dict(zip(colunas, r)) for r in rows]


def estatisticas_prf() -> dict:
    with _conexao() as con:
        try:
            total = con.execute("SELECT COUNT(*) FROM prf_acidentes").fetchone()[0]
            anos = con.execute(
                "SELECT MIN(ano), MAX(ano) FROM prf_acidentes"
            ).fetchone()
            fatais = con.execute(
                "SELECT COUNT(*) FROM prf_acidentes WHERE mortos > 0"
            ).fetchone()[0]
        except Exception:
            return {"total": 0, "ano_min": None, "ano_max": None, "fatais": 0}
    return {"total": total, "ano_min": anos[0], "ano_max": anos[1], "fatais": fatais}
