"""
Enriquece artigos com dados do corpo: hora, km, vítima, causa.
Execute com: python run_enriquecer.py [limite]
  limite: quantos artigos processar (padrão: 200, use 0 para todos os fatais)
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)

from pipeline.body_scraper import enriquecer

limite = int(sys.argv[1]) if len(sys.argv) > 1 else 200

print(f"Enriquecendo até {limite} artigos fatais e graves...")
stats = enriquecer(limite=limite, severidades=["fatal", "grave"])

print()
print("=== RESULTADO ===")
print(f"  Processados: {stats['total']}")
print(f"  Com hora:    {stats['com_hora']} ({stats['com_hora']/max(stats['total'],1)*100:.0f}%)")
print(f"  Com km:      {stats['com_km']}")
print(f"  Com vítima:  {stats['com_vitima']}")
print(f"  Erros:       {stats['erros']}")
