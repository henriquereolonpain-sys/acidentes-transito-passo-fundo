"""
Scraper para rdplanalto.com.
Coleta categorias: transito + policia (filtrando por acidentes).
Paginacao: tenta /page/N/ ate receber 404 ou pagina sem noticias novas.
"""

import re
import time
import logging
from dataclasses import dataclass
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://rdplanalto.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}
DELAY_SECONDS = 1.5

# Categorias a raspar e seus slugs
CATEGORIAS = {
    "transito": f"{BASE_URL}/categoria/transito/",
    "policia":  f"{BASE_URL}/categoria/policia/",
}

# Palavras de TRÂNSITO — obrigatório estar presente em notícias da categoria policia
# Inclui padrões antigos: "ERS 135", "BR 285" (com espaço, sem hífen)
KEYWORDS_TRANSITO = re.compile(
    r"acidente|colisao|colis\xE3o|batida|capotamento|atropel|"
    r"saida de pista|sa\xEDda de pista|capotou|tombamento|tomba|"
    r"motorista|motociclista|ciclista|pedestre|veiculo|ve\xEDculo|"
    r"caminhao|caminh\xE3o|onibus|\xF4nibus|carro|moto\b|"
    r"tr\xE2nsito|transito|rodovia|"
    r"br[-\s]\d{2,3}|ers[-\s]\d{2,3}|rs[-\s]\d{2,3}|perimetral|"
    r"ferragens|colid|tombou|capotou|choque",
    re.IGNORECASE,
)

# Palavras de resultado (morte/lesão) — sozinhas NÃO bastam para categoria policia
KEYWORDS_RESULTADO = re.compile(
    r"morre|morte|morreu|fatal|obito|\xF3bito|vitima|v\xEDtima|ferido|ferida",
    re.IGNORECASE,
)

# Classificacao de severidade pelo titulo
_FATAL = re.compile(
    r"\bmorre\b|\bmorrem\b|\bmorreu\b|\bmorreram\b|\bmort[oa]s?\b|\bmortes\b|"
    r"\bfatal\b|\bfatais\b|\b[oó]bitos?\b|\bfalec|\bv[ií]tima[s]? fatal",
    re.IGNORECASE,
)
_GRAVE = re.compile(
    r"grave|ferido|ferida|hospitaliz|uti\b|escalpelamento|amputac",
    re.IGNORECASE,
)
_FISCALIZACAO = re.compile(
    r"balada segura|opera[cç][aã]o|autua|embriaguez|alcool|\xE1lcool|"
    r"dnit|obras|sinalizacao|sinalizac\xE3o",
    re.IGNORECASE,
)


def classificar_severidade(titulo: str) -> str:
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


def _parse_data(texto: str) -> datetime | None:
    texto = texto.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, fmt)
        except ValueError:
            continue
    return None


def _contar_links_artigo(html: str) -> int:
    """Conta quantos links parecem artigos (sem filtro de categoria). Usado para detectar fim de paginação."""
    soup = BeautifulSoup(html, "html.parser")
    count = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith(BASE_URL + "/"):
            continue
        if any(p in href for p in ["/categoria/", "/page/", "/tag/", "/author/"]):
            continue
        slug = href.rstrip("/").split("/")[-1]
        if len(slug) >= 10 and slug.count("-") >= 2:
            h3 = a.find("h3")
            titulo = h3.get_text(strip=True) if h3 else a.get_text(strip=True)
            if titulo and len(titulo) >= 20:
                count += 1
    return count


def _extrair_noticias_da_pagina(html: str, categoria: str) -> list[Noticia]:
    soup = BeautifulSoup(html, "html.parser")
    noticias = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith(BASE_URL + "/"):
            continue
        # ignora links de navegacao
        if any(p in href for p in ["/categoria/", "/page/", "/tag/", "/author/"]):
            continue
        if href.rstrip("/") == BASE_URL:
            continue

        slug = href.rstrip("/").split("/")[-1]
        if len(slug) < 10 or slug.count("-") < 2:
            continue

        h3 = a.find("h3")
        titulo = h3.get_text(strip=True) if h3 else a.get_text(strip=True)
        if not titulo or len(titulo) < 20:
            continue

        # descarta links de navegação, páginas institucionais e seções do site
        _SLUG_IGNORAR = re.compile(
            r"^(sobre|contato|publicidade|privacidade|anuncie|equipe|"
            r"quem-somos|fale-conosco|categoria|tag|author|page|feed)",
            re.IGNORECASE,
        )
        if _SLUG_IGNORAR.match(slug):
            continue

        # Para policia: exige pelo menos uma palavra de trânsito no título
        # (evita capturar homicídios, roubos, etc. que também têm "morte")
        if categoria == "policia" and not KEYWORDS_TRANSITO.search(titulo):
            continue

        data = None
        parent = a.parent
        for _ in range(4):
            if parent is None:
                break
            texto_data = parent.find(string=re.compile(r"\d{2}/\d{2}/\d{4}"))
            if texto_data:
                data = _parse_data(str(texto_data))
                break
            parent = parent.parent

        severidade = classificar_severidade(titulo)

        noticias.append(Noticia(
            titulo=titulo,
            url=href,
            slug=slug,
            data_publicacao=data,
            categoria=categoria,
            severidade=severidade,
        ))

    # deduplica por URL
    vistos: set[str] = set()
    unicos = []
    for n in noticias:
        if n.url not in vistos:
            vistos.add(n.url)
            unicos.append(n)

    return unicos


def _scrape_categoria(
    categoria: str, base: str, max_paginas: int,
    urls_existentes: set[str] | None = None,
) -> list[Noticia]:
    todas: list[Noticia] = []
    session = requests.Session()
    session.headers.update(HEADERS)
    # URLs já no banco (para detectar que chegamos em território já coletado)
    urls_ja_coletadas = urls_existentes or set()
    urls_vistas: set[str] = set()
    paginas_ja_coletadas_consecutivas = 0

    for pagina in range(1, max_paginas + 1):
        url = base if pagina == 1 else f"{base}page/{pagina}/"

        resp = None
        for tentativa in range(1, 4):
            try:
                resp = session.get(url, timeout=20)
                break
            except requests.RequestException as e:
                logger.warning(f"[{categoria}] Erro pagina {pagina} tentativa {tentativa}: {e}")
                if tentativa < 3:
                    time.sleep(5 * tentativa)
                else:
                    logger.warning(f"[{categoria}] Desistindo da pagina {pagina} apos 3 tentativas")

        if resp is None:
            # reconecta e continua na próxima pagina em vez de parar tudo
            session = requests.Session()
            session.headers.update(HEADERS)
            time.sleep(10)
            continue

        if resp.status_code == 404:
            logger.info(f"[{categoria}] 404 na pagina {pagina} - fim da categoria")
            break
        if resp.status_code != 200:
            logger.warning(f"[{categoria}] HTTP {resp.status_code} na pagina {pagina}")
            time.sleep(5)
            continue

        noticias = _extrair_noticias_da_pagina(resp.text, categoria)
        total_links = _contar_links_artigo(resp.text)

        # Página sem NENHUM link de artigo = fim real da paginação (404 silencioso ou loop)
        if total_links == 0:
            logger.info(f"[{categoria}] Pagina {pagina}: sem links de artigo - fim real")
            break

        novas_desta_sessao = [n for n in noticias if n.url not in urls_vistas]

        # Todos os links desta sessão já foram vistos = loop de paginação
        if total_links > 0 and novas_desta_sessao == [] and len(noticias) == 0:
            # Página tem links mas nenhum passou o filtro de categoria — CONTINUA
            if pagina % 100 == 0:
                logger.info(f"[{categoria}] Pagina {pagina}: sem acidentes nesta pagina, continuando...")
            time.sleep(DELAY_SECONDS)
            continue

        if novas_desta_sessao == [] and len(noticias) > 0:
            # Todos já foram vistos nesta sessão = loop de paginação real
            logger.info(f"[{categoria}] Pagina {pagina}: loop de paginacao detectado - fim")
            break

        genuinamente_novas = [n for n in novas_desta_sessao if n.url not in urls_ja_coletadas]
        ja_no_banco = len(novas_desta_sessao) - len(genuinamente_novas)

        for n in novas_desta_sessao:
            urls_vistas.add(n.url)
        todas.extend(genuinamente_novas)

        # Se a página inteira já estava no banco, incrementa contador de parada
        if novas_desta_sessao and not genuinamente_novas:
            paginas_ja_coletadas_consecutivas += 1
            if paginas_ja_coletadas_consecutivas >= 10:
                logger.info(f"[{categoria}] 10 paginas consecutivas ja no banco - fim")
                break
        else:
            paginas_ja_coletadas_consecutivas = 0

        if pagina % 50 == 0 or genuinamente_novas:
            logger.info(
                f"[{categoria}] Pagina {pagina}: {len(genuinamente_novas)} novas | "
                f"{ja_no_banco} ja no banco | total sessao: {len(todas)}"
            )

        time.sleep(DELAY_SECONDS)

    return todas


# Limites por categoria (páginas)
MAX_PAGINAS = {
    "transito": 200,    # categoria existe desde ~2024, crescimento contínuo
    "policia":  1500,   # vai até ~2013
}


def scrape(urls_existentes: set[str] | None = None) -> list[Noticia]:
    """
    Coleta todas as categorias e retorna lista deduplicada por URL.
    urls_existentes: conjunto de URLs já no banco para pular território já coletado.
    """
    todas: list[Noticia] = []
    urls_globais: set[str] = set()

    for categoria, base_url in CATEGORIAS.items():
        max_pag = MAX_PAGINAS.get(categoria, 200)
        logger.info(f"=== Coletando categoria: {categoria} (max {max_pag} paginas) ===")
        noticias = _scrape_categoria(
            categoria, base_url, max_pag, urls_existentes=urls_existentes
        )
        novas = [n for n in noticias if n.url not in urls_globais]
        for n in novas:
            urls_globais.add(n.url)
        todas.extend(novas)
        logger.info(f"[{categoria}] Total unico novo: {len(novas)}")

    return todas
