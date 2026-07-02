"""
Pipeline principal: coleta -> extração de local + município -> geocodificação -> storage.
Execute com:  python run_pipeline.py
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

from scrapers.rdplanalto import scrape as scrape_rdplanalto
from scrapers.gzh import scrape as scrape_gzh
from scrapers.uirapuru import scrape as scrape_uirapuru
from scrapers.tapejara import scrape as scrape_tapejara
from pipeline.extrator import extrair_localizacao, extrair_municipio
from pipeline.geocoder import geocodificar
from pipeline import storage
from pipeline.deduplicar import deduplicar


def coletar_e_salvar():
    logger.info("=== ETAPA 1: Scraping rdplanalto.com ===")

    # Carrega URLs já no banco para o scraper poder parar em território conhecido
    urls_existentes = storage.buscar_urls_existentes()
    logger.info(f"URLs ja no banco: {len(urls_existentes)}")

    noticias_rdp = scrape_rdplanalto(urls_existentes=urls_existentes)
    logger.info(f"rdplanalto: {len(noticias_rdp)} noticias")

    logger.info("Scraping GZH Passo Fundo...")
    noticias_gzh_raw = scrape_gzh()
    logger.info(f"gzh: {len(noticias_gzh_raw)} noticias")

    # Converte GZH para o formato comum e filtra URLs já no banco
    noticias_gzh = []
    for n in noticias_gzh_raw:
        if n.url not in urls_existentes:
            noticias_gzh.append(n)

    logger.info("Scraping Uirapuru...")
    noticias_uira = [n for n in scrape_uirapuru(urls_existentes=urls_existentes)
                     if n.url not in urls_existentes]
    logger.info(f"uirapuru: {len(noticias_uira)} noticias")

    logger.info("Scraping Radio Tapejara...")
    noticias_tap = [n for n in scrape_tapejara(urls_existentes=urls_existentes)
                    if n.url not in urls_existentes]
    logger.info(f"tapejara: {len(noticias_tap)} noticias")

    noticias_raw = list(noticias_rdp) + noticias_gzh + noticias_uira + noticias_tap
    logger.info(f"Total coletado: {len(noticias_raw)} noticias")

    registros = []
    for n in noticias_raw:
        municipio = extrair_municipio(n.titulo, n.slug)
        loc = extrair_localizacao(n.slug, municipio)

        # Campos base comuns a todas as fontes
        registro = {
            "titulo": n.titulo,
            "url": n.url,
            "slug": n.slug,
            "data_publicacao": n.data_publicacao,
            "fonte": getattr(n, "fonte", None) or ("gzh" if hasattr(n, "teaser") else "rdplanalto"),
            "categoria": getattr(n, "categoria", "transito"),
            "severidade": n.severidade,
            "municipio": municipio,
            # Campos extras do GZH (None para rdplanalto)
            "hora_acidente": getattr(n, "hora_acidente", None),
            "km_rodovia": getattr(n, "km_rodovia", None),
            "teaser": getattr(n, "teaser", None),
        }
        if loc:
            registro.update({
                "loc_tipo": loc.get("tipo"),
                "loc_endereco": loc.get("endereco"),
                "loc_rua1": loc.get("rua1"),
                "loc_rua2": loc.get("rua2"),
            })
        registros.append(registro)

    inseridos = storage.inserir_noticias(registros)
    logger.info(f"Novos registros inseridos: {inseridos}")
    return inseridos


def geocodificar_pendentes():
    logger.info("=== ETAPA 2: Geocodificacao ===")
    pendentes = storage.buscar_sem_geocodificar()
    logger.info(f"Registros para geocodificar: {len(pendentes)}")

    for i, reg in enumerate(pendentes, 1):
        logger.info(
            f"[{i}/{len(pendentes)}] [{reg['loc_tipo']}] {reg['loc_endereco']}"
        )
        coords = geocodificar(
            endereco=reg["loc_endereco"],
            loc_tipo=reg["loc_tipo"],
            rua1=reg.get("loc_rua1"),
            rua2=reg.get("loc_rua2"),
            municipio=reg.get("municipio", "Passo Fundo"),
            km_rodovia=reg.get("km_rodovia"),
        )
        if coords:
            storage.atualizar_coordenadas(reg["id"], coords[0], coords[1])
            logger.info(f"  -> ({coords[0]:.5f}, {coords[1]:.5f})")
        else:
            storage.marcar_sem_coordenada(reg["id"])
            logger.info("  -> nao encontrado")


def main():
    storage.inicializar()
    coletar_e_salvar()
    geocodificar_pendentes()

    logger.info("=== ETAPA 3: Deduplicacao ===")
    dup_stats = deduplicar()

    stats = storage.estatisticas()
    logger.info("=== RESUMO ===")
    logger.info(f"Total de artigos:    {stats['total']}")
    logger.info(f"Acidentes unicos:    {dup_stats['acidentes_unicos']}")
    logger.info(f"Acompanhamentos:     {dup_stats['acompanhamentos']}")
    logger.info(f"Com coordenada:      {stats['com_coordenada']}")
    logger.info(f"Sem localizacao:     {stats['sem_localizacao']}")


if __name__ == "__main__":
    main()
