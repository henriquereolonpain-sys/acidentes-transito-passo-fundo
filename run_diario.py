"""
Rotina diária: coleta apenas notícias novas, geocodifica, enriquece os
graves/fatais novos, deduplica e recalcula a confiança.

Tudo incremental — o scraper para ao bater em território já coletado e
o geocoder/enriquecimento só processam o que ainda não foi processado.

Execute manualmente:  python run_diario.py
Ou agende (ver agendar_diario.ps1).
"""
import logging
import sys
from datetime import datetime

LOG_PATH = "data/diario.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("diario")


def main():
    inicio = datetime.now()
    logger.info("=" * 60)
    logger.info(f"ROTINA DIARIA — {inicio:%Y-%m-%d %H:%M}")
    logger.info("=" * 60)

    from pipeline import storage
    storage.inicializar()

    # 1. Coleta incremental das 3 fontes de notícias
    novos_total = 0
    novos_total += _coletar_rdplanalto()
    novos_total += _coletar_uirapuru()
    novos_total += _coletar_gzh()
    logger.info(f"Total de notícias novas: {novos_total}")

    if novos_total == 0:
        logger.info("Nenhuma notícia nova — encerrando sem processar.")
        return

    # 2. Geocodifica os novos (com km exato para rodovias)
    _geocodificar()

    # 3. Enriquece graves/fatais novos
    _enriquecer()

    # 4. Deduplicação + confiança
    from pipeline.deduplicar import deduplicar
    from pipeline.confianca import calcular
    deduplicar()
    calcular()

    stats = storage.estatisticas()
    dur = (datetime.now() - inicio).total_seconds()
    logger.info(f"FIM em {dur:.0f}s — {stats['total']} artigos, {stats['com_coordenada']} com coordenada")


def _coletar_rdplanalto() -> int:
    from scrapers.rdplanalto import scrape
    from pipeline import storage
    from pipeline.extrator import extrair_localizacao, extrair_municipio
    urls = storage.buscar_urls_existentes()
    noticias = scrape(urls_existentes=urls)
    return _salvar(noticias, "rdplanalto")


def _coletar_uirapuru() -> int:
    from scrapers.uirapuru import scrape
    from pipeline import storage
    urls = {u for u in storage.buscar_urls_existentes()}
    noticias = scrape(max_paginas=30, urls_existentes=urls)  # só páginas iniciais no diário
    return _salvar(noticias, "uirapuru")


def _coletar_gzh() -> int:
    from scrapers.gzh import scrape
    from pipeline import storage
    urls = storage.buscar_urls_existentes()
    noticias = scrape(max_paginas=15, urls_existentes=urls)  # só páginas iniciais
    return _salvar(noticias, "gzh")


def _salvar(noticias, fonte: str) -> int:
    from pipeline import storage
    from pipeline.extrator import extrair_localizacao, extrair_municipio
    if not noticias:
        return 0
    registros = []
    for n in noticias:
        municipio = extrair_municipio(n.titulo, n.slug)
        loc = extrair_localizacao(n.slug, municipio)
        r = {
            "titulo": n.titulo, "url": n.url, "slug": n.slug,
            "data_publicacao": n.data_publicacao, "fonte": fonte,
            "categoria": getattr(n, "categoria", "transito"),
            "severidade": n.severidade, "municipio": municipio,
            "hora_acidente": getattr(n, "hora_acidente", None),
            "km_rodovia": getattr(n, "km_rodovia", None),
            "teaser": getattr(n, "teaser", None),
        }
        if loc:
            r.update({"loc_tipo": loc.get("tipo"), "loc_endereco": loc.get("endereco"),
                      "loc_rua1": loc.get("rua1"), "loc_rua2": loc.get("rua2")})
        registros.append(r)
    n_ins = storage.inserir_noticias(registros)
    logger.info(f"  {fonte}: {n_ins} novos")
    return n_ins


def _geocodificar():
    from pipeline.geocoder import geocodificar
    from pipeline import storage
    pendentes = storage.buscar_sem_geocodificar()
    logger.info(f"Geocodificando {len(pendentes)} novos...")
    for reg in pendentes:
        coords = geocodificar(
            endereco=reg["loc_endereco"], loc_tipo=reg["loc_tipo"],
            rua1=reg.get("loc_rua1"), rua2=reg.get("loc_rua2"),
            municipio=reg.get("municipio", "Passo Fundo"),
            km_rodovia=reg.get("km_rodovia"),
        )
        if coords:
            storage.atualizar_coordenadas(reg["id"], coords[0], coords[1])
        else:
            storage.marcar_sem_coordenada(reg["id"])


def _enriquecer():
    from pipeline.body_scraper import enriquecer
    stats = enriquecer(limite=100, severidades=["fatal", "grave"])
    logger.info(f"Enriquecidos: hora={stats['com_hora']} km={stats['com_km']}")


if __name__ == "__main__":
    main()
