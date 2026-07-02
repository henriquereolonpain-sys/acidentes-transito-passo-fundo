"""
Scraper para Rádio Tapejara — seção de acidentes.
URL: https://www.radiotapejara.com.br/noticias/assunto/17/acidente

Paginação por POST (a URL não muda): o site tem um form #formPaginacao com
os campos paginacao (nº da página), tipo=assunto, id=17. Incrementando
`paginacao` o servidor devolve o próximo lote de notícias.

Estrutura de cada notícia na listagem:
  div.radio-latest-noticia-item > a[href="/noticia/{id}/{slug}"]
      div.radio-meta-date   -> "01/07/2026 09:44"
      h5.radio-titulo       -> título limpo
"""

import re
import time
import logging
from dataclasses import dataclass
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.radiotapejara.com.br"
LISTA_URL = f"{BASE_URL}/noticias/assunto/17/acidente"
POST_TIPO = "assunto"
POST_ID = "17"
DELAY_SECONDS = 1.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": LISTA_URL,
}

KEYWORDS_TRANSITO = re.compile(
    r"acidente|colis[ãa]o|batida|capot|atropel|sa[ií]da de pista|"
    r"tombamento|tomba\b|motorista|motociclista|ciclista|ve[íi]culo|"
    r"caminh[ãa]o|carreta|\bmoto\b|autom[óo]vel|carro\b|"
    r"tr[âa]nsito|transito|rodovia|br-?\d|ers-?\d|rs-?\d|perimetral|trevo|"
    r"pedestre|colidiu|colide|bateu|engavetamento",
    re.IGNORECASE,
)

_FATAL = re.compile(
    r"\bmorre\b|\bmorrem\b|\bmorreu\b|\bmorreram\b|\bmort[oa]s?\b|\bmortes\b|"
    r"\bfatal\b|\bfatais\b|\b[oó]bitos?\b|\bfalec|\bv[ií]tima[s]? fatal",
    re.IGNORECASE,
)
_GRAVE = re.compile(
    r"\bgrave\b|\bferido\b|\bferida\b|\bferidos\b|\bhospitaliz|\buti\b|"
    r"\bfratura|\bescalpelamento",
    re.IGNORECASE,
)
_FISCALIZACAO = re.compile(
    r"balada segura|opera[cç][aã]o|autua|embriaguez|álcool|alcool|"
    r"dnit|obras|sinalizacao",
    re.IGNORECASE,
)


def _classificar_severidade(titulo: str) -> str:
    if _FATAL.search(titulo):
        return "fatal"
    if _GRAVE.search(titulo):
        return "grave"
    if _FISCALIZACAO.search(titulo):
        return "fiscalizacao"
    return "colisao"


@dataclass
class Noticia:
    titulo: str
    url: str
    slug: str
    data_publicacao: datetime | None
    categoria: str
    severidade: str
    fonte: str = "tapejara"


def _parse_data(texto: str) -> datetime | None:
    """Aceita 'DD/MM/YYYY' e 'DD/MM/YYYY HH:MM'."""
    if not texto:
        return None
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _extrair_da_pagina(html: str) -> list[Noticia]:
    soup = BeautifulSoup(html, "html.parser")
    noticias: list[Noticia] = []
    vistos: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/noticia/" not in href.lower():
            continue

        url = href if href.startswith("http") else BASE_URL + href
        if url in vistos:
            continue
        vistos.add(url)

        # título limpo do h5.radio-titulo; fallback: texto do link sem a data
        h5 = a.find(class_="radio-titulo")
        if h5:
            titulo = h5.get_text(strip=True)
        else:
            txt = a.get_text(" ", strip=True)
            titulo = re.sub(r"^\d{2}/\d{2}/\d{4}\s*\d{0,2}:?\d{0,2}\s*", "", txt)
        if not titulo or len(titulo) < 15:
            continue

        # seção "acidente" inclui acidentes não-viários (trabalho, rural) —
        # mantém só os de trânsito
        if not KEYWORDS_TRANSITO.search(titulo):
            continue

        # data do div.radio-meta-date (ex.: "01/07/2026 09:44")
        data_el = a.find(class_="radio-meta-date")
        data = _parse_data(data_el.get_text(strip=True) if data_el else a.get_text())

        slug = url.rstrip("/").split("/")[-1]

        noticias.append(Noticia(
            titulo=titulo,
            url=url,
            slug=slug,
            data_publicacao=data,
            categoria="acidente",
            severidade=_classificar_severidade(titulo),
        ))

    return noticias


def scrape(max_paginas: int = 300,
           urls_existentes: set[str] | None = None) -> list[Noticia]:
    """
    Percorre a listagem de acidentes via POST paginado até parar de achar
    URLs novas (ou bater em território já coletado).
    """
    todas: list[Noticia] = []
    urls_vistas: set[str] = set(urls_existentes or [])
    session = requests.Session()
    session.headers.update(HEADERS)
    paginas_sem_novos = 0

    logger.info("=== Tapejara: acidentes ===")
    for pagina in range(1, max_paginas + 1):
        data = {"paginacao": str(pagina), "tipo": POST_TIPO, "id": POST_ID}

        resp = None
        for tentativa in range(1, 5):
            try:
                resp = session.post(LISTA_URL, data=data, timeout=20)
                break
            except requests.RequestException as e:
                espera = 10 * tentativa
                logger.warning(f"[tapejara] Pag {pagina} tentativa {tentativa}: {e} — aguarda {espera}s")
                time.sleep(espera)

        if resp is None or resp.status_code != 200:
            paginas_sem_novos += 1
            if paginas_sem_novos >= 3:
                break
            time.sleep(5)
            continue

        noticias = _extrair_da_pagina(resp.text)
        novos = [n for n in noticias if n.url not in urls_vistas]

        if not novos:
            paginas_sem_novos += 1
            if paginas_sem_novos >= 3:
                logger.info(f"[tapejara] 3 páginas sem novidades — fim")
                break
            time.sleep(DELAY_SECONDS)
            continue

        paginas_sem_novos = 0
        for n in novos:
            urls_vistas.add(n.url)
        todas.extend(novos)
        logger.info(f"[tapejara] Pag {pagina}: {len(novos)} novas | total: {len(todas)}")
        time.sleep(DELAY_SECONDS)

    logger.info(f"[tapejara] Total unico: {len(todas)}")
    return todas
