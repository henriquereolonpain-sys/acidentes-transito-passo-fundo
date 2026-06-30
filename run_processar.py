"""
Processa o banco em sequência:
1. Geocodifica registros pendentes
2. Enriquece artigos fatais/graves com hora, km e vítima do corpo
3. Roda deduplicação

Execute com: python run_processar.py
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

from pipeline.geocoder import geocodificar
from pipeline import storage
from pipeline.deduplicar import deduplicar
from pipeline.body_scraper import enriquecer

storage.inicializar()

# 1. Geocodificação
pendentes = storage.buscar_sem_geocodificar()
logger.info(f"=== GEOCODIFICACAO: {len(pendentes)} registros ===")
for i, reg in enumerate(pendentes, 1):
    if i % 100 == 0:
        logger.info(f"  {i}/{len(pendentes)}")
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
    else:
        storage.marcar_sem_coordenada(reg["id"])

# 2. Enriquecimento de fatais e graves
logger.info("=== ENRIQUECIMENTO DE FATAIS/GRAVES ===")
stats = enriquecer(limite=900, severidades=["fatal", "grave"])
logger.info(f"  hora={stats['com_hora']} km={stats['com_km']} vitima={stats['com_vitima']} erros={stats['erros']}")

# 3. Deduplicação
logger.info("=== DEDUPLICACAO ===")
dup = deduplicar()
logger.info(f"  Acidentes unicos: {dup['acidentes_unicos']}")

# 4. Nível de confiança (fact-checking)
logger.info("=== CONFIANCA ===")
from pipeline.confianca import calcular
buckets = calcular()
logger.info(f"  Alta: {buckets['alta']} | Media: {buckets['media']} | Baixa: {buckets['baixa']}")

# Resumo
db = storage.estatisticas()
logger.info(f"=== FIM: {db['total']} artigos | {db['com_coordenada']} com coordenada ===")
