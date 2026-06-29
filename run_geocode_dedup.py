"""
Roda só geocodificação + deduplicação no que já está no banco.
Útil quando já coletamos os artigos e só precisamos processar.
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

from pipeline.geocoder import geocodificar
from pipeline import storage
from pipeline.deduplicar import deduplicar

storage.inicializar()

# Geocodificação
pendentes = storage.buscar_sem_geocodificar()
logger.info(f"Registros para geocodificar: {len(pendentes)}")

for i, reg in enumerate(pendentes, 1):
    if i % 50 == 0:
        logger.info(f"  Progresso: {i}/{len(pendentes)}")
    coords = geocodificar(
        endereco=reg["loc_endereco"],
        loc_tipo=reg["loc_tipo"],
        rua1=reg.get("loc_rua1"),
        rua2=reg.get("loc_rua2"),
        municipio=reg.get("municipio", "Passo Fundo"),
    )
    if coords:
        storage.atualizar_coordenadas(reg["id"], coords[0], coords[1])
    else:
        storage.marcar_sem_coordenada(reg["id"])

# Deduplicação
logger.info("Deduplicando...")
stats = deduplicar()
logger.info(f"Acidentes unicos: {stats['acidentes_unicos']} | Acompanhamentos: {stats['acompanhamentos']}")

# Resumo
db_stats = storage.estatisticas()
logger.info(f"Total artigos: {db_stats['total']} | Com coordenada: {db_stats['com_coordenada']}")
