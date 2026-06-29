"""
Baixa e carrega dados da PRF para Passo Fundo e região.
Execute com: python run_prf.py [ano_inicio] [ano_fim]

Exemplos:
  python run_prf.py              # 2015 a 2024 (padrão)
  python run_prf.py 2020 2024    # só esses anos
  python run_prf.py 2024 2024    # só 2024
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

from scrapers.prf import carregar_anos, GDRIVE_IDS
from pipeline import storage


def main():
    storage.inicializar()

    # Intervalo de anos via args
    anos_disponiveis = sorted(GDRIVE_IDS.keys())
    if len(sys.argv) >= 3:
        ano_ini = int(sys.argv[1])
        ano_fim = int(sys.argv[2])
    elif len(sys.argv) == 2:
        ano_ini = int(sys.argv[1])
        ano_fim = ano_ini
    else:
        # Padrão: 2015 até o ano atual completo disponível na PRF
        # 2025 incluído mas marcado como parcial
        import datetime
        ano_ini = 2015
        ano_fim = datetime.date.today().year - 1  # ano anterior = completo

    anos = [a for a in anos_disponiveis if ano_ini <= a <= ano_fim]
    logger.info(f"Anos a processar: {anos}")

    df = carregar_anos(anos)

    if df.empty:
        logger.warning("Nenhum dado retornado.")
        return

    logger.info(f"Total filtrado para a regiao: {len(df)} acidentes")

    # Distribuição por severidade
    if "severidade" in df.columns:
        for sev, n in df["severidade"].value_counts().items():
            logger.info(f"  {sev}: {n}")

    import datetime
    ano_atual = datetime.date.today().year
    # Marca o ano em curso como parcial
    if "ano" in df.columns:
        df["ano_completo"] = df["ano"] < ano_atual

    inseridos = storage.inserir_prf(df)
    logger.info(f"Inseridos: {inseridos}")

    stats = storage.estatisticas_prf()
    logger.info(f"PRF no banco: {stats['total']} acidentes ({stats['ano_min']}-{stats['ano_max']})")
    logger.info(f"  Fatais: {stats['fatais']}")


if __name__ == "__main__":
    main()
