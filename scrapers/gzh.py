"""
Scraper para GZH Passo Fundo — seção trânsito.
URL: https://gauchazh.clicrbs.com.br/passo-fundo/transito/ultimas-noticias/pagina/{N}/

Diferencial: os teasers das matérias já contêm horário e km do acidente,
o que melhora a deduplicação e a geocodificação de rodovias.
"""

import re
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://gauchazh.clicrbs.com.br"
LISTAGEM_URL = f"{BASE_URL}/passo-fundo/transito/ultimas-noticias/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}
DELAY_SECONDS = 1.5

_RE_HORA = re.compile(
    r"(?:às\s+|por volta das?\s+)(\d{1,2}[h:]\d{0,2}(?:min)?|\d{1,2}h\d{0,2})",
    re.IGNORECASE,
)
_RE_KM = re.compile(r"\bkm\s*(\d+[,.]?\d*)", re.IGNORECASE)
_RE_DATA_URL = re.compile(r"/noticia/(\d{4})/(\d{2})/")


@dataclass
class NoticiaGZH:
    titulo: str
    url: str
    slug: str
    data_publicacao: datetime | None
    teaser: str
    hora_acidente: str | None       # ex: "7h30", "14h"
    km_rodovia: str | None          # ex: "43", "220"
    severidade: str = "colisao"


def _parse_data_url(url: str) -> datetime | None:
    """Extrai data do padrão /noticia/YYYY/MM/ na URL."""
    m = _RE_DATA_URL.search(url)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            pass
    return None


def _classificar_severidade(titulo: str, teaser: str) -> str:
    texto = (titulo + " " + teaser).lower()
    if any(p in texto for p in ["morre", "morrem", "morreu", "morreram",
                                  "morto", "morta", "fatal", "óbito", "obito",
                                  "vítima fatal", "vitima fatal", "faleceu"]):
        return "fatal"
    if any(p in texto for p in ["grave", "ferido", "ferida", "hospitaliz", "uti",
                                  "atropel", "escalpelamento"]):
        return "grave"
    return "colisao"


def _extrair_artigos_da_pagina(html: str) -> list[NoticiaGZH]:
    soup = BeautifulSoup(html, "html.parser")
    artigos = []
    vistos: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/transito/noticia/" not in href:
            continue

        url = href if href.startswith("http") else BASE_URL + href
        if url in vistos:
            continue
        vistos.add(url)

        slug = url.rstrip("/").rstrip(".html").split("/")[-1]

        # Título: texto do link ou h2/h3 dentro
        titulo_tag = a.find(["h2", "h3"])
        titulo = titulo_tag.get_text(strip=True) if titulo_tag else a.get_text(strip=True)
        titulo = re.sub(r"\s+", " ", titulo).strip()
        if len(titulo) < 20:
            continue

        # Teaser: está no div pai do <a>, como nó irmão fora do link
        teaser = ""
        pai = a.parent
        if pai:
            # Texto do pai sem incluir o texto do próprio link
            texto_pai = pai.get_text(separator=" ", strip=True)
            texto_link = a.get_text(separator=" ", strip=True)
            # Remove o texto do link do texto do pai — o que sobrar é o teaser
            teaser = texto_pai.replace(texto_link, "").strip()
            teaser = re.sub(r"\s+", " ", teaser).strip()

        # Hora e km do teaser
        hora = None
        km = None
        if teaser:
            m_hora = _RE_HORA.search(teaser)
            if m_hora:
                hora = m_hora.group(1).replace(":", "h")
            m_km = _RE_KM.search(teaser)
            if m_km:
                km = m_km.group(1)

        data = _parse_data_url(url)
        severidade = _classificar_severidade(titulo, teaser)

        artigos.append(NoticiaGZH(
            titulo=titulo,
            url=url,
            slug=slug,
            data_publicacao=data,
            teaser=teaser,
            hora_acidente=hora,
            km_rodovia=km,
            severidade=severidade,
        ))

    return artigos


def scrape(max_paginas: int = 200, start_page: int = 1,
           urls_existentes: set[str] | None = None) -> list[NoticiaGZH]:
    """
    Coleta páginas de transito do GZH Passo Fundo.
    start_page: página inicial (útil para retomar após interrupção).
    urls_existentes: URLs já no banco — puladas mas não causam stop por 'loop'.
    """
    todas: list[NoticiaGZH] = []
    urls_vistas: set[str] = set(urls_existentes or [])
    session = requests.Session()
    session.headers.update(HEADERS)

    paginas_sem_novidade = 0  # páginas consecutivas sem artigos novos

    for pagina in range(start_page, start_page + max_paginas):
        url = LISTAGEM_URL if pagina == 1 else f"{LISTAGEM_URL}pagina/{pagina}/"

        resp = None
        for tentativa in range(1, 5):
            try:
                resp = session.get(url, timeout=20)
                break
            except requests.RequestException as e:
                logger.warning(f"[gzh] Pag {pagina} tentativa {tentativa}: {e}")
                espera = 10 * tentativa
                logger.info(f"[gzh] Aguardando {espera}s antes de tentar novamente...")
                time.sleep(espera)

        if resp is None:
            logger.warning(f"[gzh] Pag {pagina}: 4 tentativas falharam, pulando")
            paginas_sem_novidade += 1
            if paginas_sem_novidade >= 3:
                logger.info("[gzh] 3 páginas com falha consecutiva, encerrando")
                break
            continue

        if resp.status_code == 404:
            logger.info(f"[gzh] Pag {pagina}: 404 — fim da paginação")
            break
        if resp.status_code != 200:
            logger.warning(f"[gzh] Pag {pagina}: HTTP {resp.status_code}, aguardando 10s")
            time.sleep(10)
            continue

        artigos = _extrair_artigos_da_pagina(resp.text)

        if not artigos:
            paginas_sem_novidade += 1
            if paginas_sem_novidade >= 5:
                logger.info("[gzh] 5 páginas sem artigos, encerrando")
                break
            continue

        novos = [a for a in artigos if a.url not in urls_vistas]

        # Todos já vistos nesta sessão = loop de paginação real
        if not novos and all(a.url in (urls_existentes or set()) for a in artigos):
            paginas_sem_novidade += 1
        else:
            paginas_sem_novidade = 0

        for a in novos:
            urls_vistas.add(a.url)
        todas.extend(novos)

        if novos:
            logger.info(f"[gzh] Pag {pagina}: {len(novos)} novas | total sessao: {len(todas)}")

        time.sleep(DELAY_SECONDS)

    return todas
