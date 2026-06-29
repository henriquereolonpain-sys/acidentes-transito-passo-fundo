"""
Coleta ou retoma o scraping do GZH Passo Fundo.
Execute com: python run_gzh.py [pagina_inicio]
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)

import duckdb
from scrapers.gzh import scrape
from pipeline import storage
from pipeline.extrator import extrair_localizacao, extrair_municipio

start_page = int(sys.argv[1]) if len(sys.argv) > 1 else 1

# URLs GZH já no banco — são puladas sem causar stop por "loop"
con = duckdb.connect("data/acidentes.duckdb")
urls_existentes = set(r[0] for r in con.execute("SELECT url FROM acidentes WHERE fonte='gzh'").fetchall())
con.close()
print(f"URLs GZH ja no banco: {len(urls_existentes)} | Iniciando da pagina {start_page}")

noticias = scrape(max_paginas=200, start_page=start_page, urls_existentes=urls_existentes)
print(f"Novas coletadas: {len(noticias)}")

registros = []
for n in noticias:
    municipio = extrair_municipio(n.titulo, n.slug)
    loc = extrair_localizacao(n.slug, municipio)
    r = {
        "titulo": n.titulo, "url": n.url, "slug": n.slug,
        "data_publicacao": n.data_publicacao, "fonte": "gzh",
        "categoria": "transito", "severidade": n.severidade,
        "municipio": municipio,
        "hora_acidente": n.hora_acidente, "km_rodovia": n.km_rodovia, "teaser": n.teaser,
    }
    if loc:
        r.update({"loc_tipo": loc.get("tipo"), "loc_endereco": loc.get("endereco"),
                  "loc_rua1": loc.get("rua1"), "loc_rua2": loc.get("rua2")})
    registros.append(r)

inseridos = storage.inserir_noticias(registros)
print(f"Inseridos no banco: {inseridos}")
