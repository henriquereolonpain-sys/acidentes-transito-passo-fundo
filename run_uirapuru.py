"""
Coleta notícias da Rádio Uirapuru e insere no banco.
Salva incrementalmente após cada categoria para não perder dados em caso de queda.
Execute com: python run_uirapuru.py
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)

import duckdb
from scrapers.uirapuru import CATEGORIAS, _scrape_categoria
from pipeline import storage
from pipeline.extrator import extrair_localizacao, extrair_municipio

storage.inicializar()

# URLs já no banco para não re-baixar
con = duckdb.connect("data/acidentes.duckdb")
urls_existentes = set(r[0] for r in con.execute("SELECT url FROM acidentes WHERE fonte='uirapuru'").fetchall())
con.close()
print(f"URLs Uirapuru ja no banco: {len(urls_existentes)}")

total_inserido = 0
urls_globais = set(urls_existentes)

for categoria, base_url in CATEGORIAS.items():
    print(f"\n=== Processando: {categoria} ===")

    noticias = _scrape_categoria(categoria, base_url, max_paginas=300, urls_existentes=urls_globais)
    print(f"Coletadas na categoria '{categoria}': {len(noticias)}")

    if not noticias:
        continue

    # Converte e insere imediatamente — não perde em caso de queda posterior
    registros = []
    for n in noticias:
        municipio = extrair_municipio(n.titulo, n.slug)
        loc = extrair_localizacao(n.slug, municipio)
        r = {
            "titulo": n.titulo, "url": n.url, "slug": n.slug,
            "data_publicacao": n.data_publicacao, "fonte": "uirapuru",
            "categoria": n.categoria, "severidade": n.severidade,
            "municipio": municipio,
        }
        if loc:
            r.update({"loc_tipo": loc.get("tipo"), "loc_endereco": loc.get("endereco"),
                      "loc_rua1": loc.get("rua1"), "loc_rua2": loc.get("rua2")})
        registros.append(r)

    inseridos = storage.inserir_noticias(registros)
    total_inserido += inseridos
    print(f"Salvos no banco: {inseridos} (total acumulado: {total_inserido})")

    # Atualiza urls_globais para evitar duplicatas entre categorias
    for n in noticias:
        urls_globais.add(n.url)

print(f"\n=== CONCLUIDO: {total_inserido} novos registros inseridos ===")
