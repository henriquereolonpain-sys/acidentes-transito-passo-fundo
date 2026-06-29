"""
Scraper para Rádio Uirapuru FM — categorias trânsito e polícia.
URL: https://rduirapuru.com.br/category/{categoria}/page/{N}/

Requer headers completos de browser (403 sem eles).
WordPress padrão: artigos em h2.post-item-title, paginação /page/N/.
"""

import re
import time
import logging
from dataclasses import dataclass
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://rduirapuru.com.br"
DELAY_SECONDS = 1.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.google.com/",
}

CATEGORIAS = {
    "transito": f"{BASE_URL}/category/transito/",
    "policia":  f"{BASE_URL}/category/policia/",
}

KEYWORDS_TRANSITO = re.compile(
    r"acidente|colisao|colis\xE3o|batida|capotamento|atropel|"
    r"saida de pista|capotou|tombamento|tomba|motorista|motociclista|"
    r"ciclista|veiculo|ve\xEDculo|caminhao|caminh\xE3o|moto\b|"
    r"tr\xE2nsito|transito|rodovia|br-\d|ers-\d|perimetral",
    re.IGNORECASE,
)

_FATAL = re.compile(
    r"\bmorre\b|\bmorrem\b|\bmorreu\b|\bmorreram\b|\bmort[oa]s?\b|\bmortes\b|"
    r"\bfatal\b|\bfatais\b|\b[oó]bitos?\b|\bfalec|\bv[ií]tima[s]? fatal",
    re.IGNORECASE,
)
_GRAVE = re.compile(
    r"\bgrave\b|\bferido\b|\bferida\b|\bhospitaliz|\buti\b|\bescalpelamento",
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
    fonte: str = "uirapuru"


def _parse_data(texto: str) -> datetime | None:
    texto = texto.strip()
    meses = {
        "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3,
        "abril": 4, "maio": 5, "junho": 6, "julho": 7,
        "agosto": 8, "setembro": 9, "outubro": 10,
        "novembro": 11, "dezembro": 12,
    }
    # "25 de junho de 2026"
    m = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", texto, re.IGNORECASE)
    if m:
        mes = meses.get(m.group(2).lower())
        if mes:
            try:
                return datetime(int(m.group(3)), mes, int(m.group(1)))
            except ValueError:
                pass
    # "25/06/2026"
    m2 = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if m2:
        try:
            return datetime(int(m2.group(3)), int(m2.group(2)), int(m2.group(1)))
        except ValueError:
            pass
    return None


def _extrair_da_pagina(html: str, categoria: str) -> list[Noticia]:
    soup = BeautifulSoup(html, "html.parser")
    noticias = []
    vistos: set[str] = set()

    for h2 in soup.find_all("h2", class_=lambda c: c and "post-item" in c):
        a = h2.find("a", href=True)
        if not a:
            continue

        url = a["href"]
        if not url.startswith("http"):
            url = BASE_URL + url
        if url in vistos:
            continue
        vistos.add(url)

        titulo = a.get_text(strip=True)
        if not titulo or len(titulo) < 15:
            continue

        slug = url.rstrip("/").split("/")[-1]

        # Filtra policia: só aceita com palavra de trânsito
        if categoria == "policia" and not KEYWORDS_TRANSITO.search(titulo):
            continue

        # Data: busca no card pai
        data = None
        card = h2.find_parent(["article", "div"])
        if card:
            time_tag = card.find("time")
            if time_tag:
                data = _parse_data(time_tag.get("datetime", "") or time_tag.get_text())
            if not data:
                txt = card.get_text()
                m = re.search(r"\d{2}/\d{2}/\d{4}", txt)
                if m:
                    data = _parse_data(m.group())

        noticias.append(Noticia(
            titulo=titulo,
            url=url,
            slug=slug,
            data_publicacao=data,
            categoria=categoria,
            severidade=_classificar_severidade(titulo),
        ))

    return noticias


def _scrape_categoria(categoria: str, base: str, max_paginas: int,
                      urls_existentes: set[str] | None = None) -> list[Noticia]:
    todas: list[Noticia] = []
    urls_vistas: set[str] = set(urls_existentes or [])
    session = requests.Session()
    session.headers.update(HEADERS)
    paginas_vazias = 0

    for pagina in range(1, max_paginas + 1):
        url = base if pagina == 1 else f"{base}page/{pagina}/"

        resp = None
        for tentativa in range(1, 5):
            try:
                resp = session.get(url, timeout=20)
                break
            except requests.RequestException as e:
                espera = 10 * tentativa
                logger.warning(f"[uirapuru/{categoria}] Pag {pagina} tentativa {tentativa}: {e} — aguarda {espera}s")
                time.sleep(espera)

        if resp is None:
            paginas_vazias += 1
            if paginas_vazias >= 3:
                break
            continue

        if resp.status_code == 404:
            logger.info(f"[uirapuru/{categoria}] Pag {pagina}: 404 — fim")
            break
        if resp.status_code == 403:
            logger.warning(f"[uirapuru/{categoria}] Pag {pagina}: 403 — aguarda 30s e tenta novamente")
            time.sleep(30)
            continue
        if resp.status_code != 200:
            logger.warning(f"[uirapuru/{categoria}] Pag {pagina}: HTTP {resp.status_code}")
            time.sleep(5)
            continue

        noticias = _extrair_da_pagina(resp.text, categoria)

        if not noticias:
            paginas_vazias += 1
            if paginas_vazias >= 5:
                logger.info(f"[uirapuru/{categoria}] 5 paginas sem artigos — fim")
                break
            time.sleep(DELAY_SECONDS)
            continue

        paginas_vazias = 0
        novos = [n for n in noticias if n.url not in urls_vistas]
        for n in novos:
            urls_vistas.add(n.url)
        todas.extend(novos)

        logger.info(f"[uirapuru/{categoria}] Pag {pagina}: {len(novos)} novas | total: {len(todas)}")
        time.sleep(DELAY_SECONDS)

    return todas


def scrape(max_paginas: int = 200,
           urls_existentes: set[str] | None = None) -> list[Noticia]:
    todas: list[Noticia] = []
    urls_globais: set[str] = set(urls_existentes or [])

    for categoria, base_url in CATEGORIAS.items():
        logger.info(f"=== Uirapuru: {categoria} ===")
        noticias = _scrape_categoria(categoria, base_url, max_paginas, urls_globais)
        novas = [n for n in noticias if n.url not in urls_globais]
        for n in novas:
            urls_globais.add(n.url)
        todas.extend(novas)
        logger.info(f"[uirapuru/{categoria}] Total unico: {len(novas)}")

    return todas
