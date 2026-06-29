"""
Extrai informações do corpo das matérias: hora, km, nome da vítima, causa.
Atualiza as colunas hora_acidente, km_rodovia, teaser no banco.

Foca nos artigos mais relevantes (fatais sem hora) para maximizar retorno.
"""

import re
import time
import logging
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

import duckdb
from pipeline.storage import _conexao, DB_PATH

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://www.google.com/",
}

# Regex para extrair dados do corpo
_RE_HORA = re.compile(
    r"(?:às|por volta das?\s+|às\s+|ocorreu\s+às\s+|registrado\s+às\s+)"
    r"(\d{1,2}[h:]\d{0,2}(?:min)?|\d{1,2}h\d{0,2})",
    re.IGNORECASE,
)
_RE_KM = re.compile(
    r"\bkm\s*(\d+[,.]?\d*)\b|\bquilômetro\s+(\d+)\b|\bquilometro\s+(\d+)\b",
    re.IGNORECASE,
)
_RE_VITIMA = re.compile(
    r"(?:identificad[ao]s?\s+como|v[ií]tima\s+(?:é|foi|era)\s+|"
    r"v[ií]tima\s+fatal[,\s]+|faleceu\s+|morreu\s+o\s+|morreu\s+a\s+)"
    r"([A-ZÁÉÍÓÚÂÊÔÀÃÕÇ][a-záéíóúâêôàãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÀÃÕÇ][a-záéíóúâêôàãõç]+){1,4})",
    re.IGNORECASE,
)
_RE_CAUSA = re.compile(
    r"\b(excesso de velocidade|imprudência|embriaguez|alcoolizado|"
    r"falta de aten[cç][aã]o|aquaplanagem|pista molhada|dormiu ao volante|"
    r"animais na pista|ultrapassagem indevida|sem habilita[cç][aã]o|"
    r"colis[aã]o frontal|avan[cç]o de sinal|freada brusca)\b",
    re.IGNORECASE,
)
_RE_CLIMA = re.compile(
    r"\b(chuva|chovendo|pista molhada|neblina|granizo|vento forte|"
    r"visibilidade reduzida|gelo na pista|tempo chuvoso|garoa)\b",
    re.IGNORECASE,
)
# Números por extenso → inteiro (notícias quase nunca usam dígitos)
_NUM_EXTENSO = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "três": 3, "tres": 3,
    "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
}
_NUM_PAT = r"(\d+|um|uma|dois|duas|tr[êe]s|quatro|cinco|seis|sete|oito|nove|dez)"

# Substantivos que podem aparecer entre o número e morto/ferido
_PESSOA = r"(?:pessoas?|crian[çc]as?|mulheres?|homens?|jovens?|"\
          r"ocupantes?|adultos?|idosos?|v[ií]timas?|tripulantes?)"

# Mortos: "X pessoas mortas", "morte de X", "X óbitos", "X vítimas fatais"
_RE_MORTOS = re.compile(
    rf"{_NUM_PAT}\s+(?:{_PESSOA}\s+)?mort[ao]s?"
    rf"|mort[ea]\s+de\s+{_NUM_PAT}"
    rf"|{_NUM_PAT}\s+[óo]bitos?"
    rf"|{_NUM_PAT}\s+v[ií]timas?\s+fatais?"
    rf"|resultou\s+(?:na|em)\s+mort[ea]\s+de\s+{_NUM_PAT}",
    re.IGNORECASE,
)
# Singular implícito: "morre", "morreu", "com morte", "vem a óbito" → 1 morte
_RE_MORTE_SINGULAR = re.compile(
    r"\b(morre|morreu|veio? a [óo]bito|vem a [óo]bito|"
    r"com morte|uma morte|morte de um|morte de uma|"
    r"morto|morta|perdeu a vida|faleceu)\b",
    re.IGNORECASE,
)

# Feridos: "X feridos", "X crianças feridas", "X pessoas ficam/ficaram feridas"
_RE_FERIDOS = re.compile(
    rf"{_NUM_PAT}\s+(?:{_PESSOA}\s+)?ferid[ao]s?"
    rf"|deixa\s+{_NUM_PAT}\s+(?:{_PESSOA}\s+)?ferid[ao]s?"
    rf"|{_NUM_PAT}\s+(?:{_PESSOA}\s+)?fic(?:am|aram|ou|a)\s+ferid[ao]s?",
    re.IGNORECASE,
)
_RE_FERIDO_SINGULAR = re.compile(
    r"\b(deixa\s+(?:um\s+)?ferid[ao]|motorista\s+ferid[ao]|condutor\s+ferid[ao]|"
    r"fica\s+ferid[ao]|ficou\s+ferid[ao]|ficaram?\s+ferid[ao]|sai\s+ferid[ao])\b",
    re.IGNORECASE,
)


def _parse_num(texto: str | None) -> int | None:
    """Converte dígito ou número por extenso para inteiro."""
    if not texto:
        return None
    texto = texto.strip().lower()
    if texto.isdigit():
        return int(texto)
    # normaliza acentos de 'três'
    texto = texto.replace("ê", "e")
    return _NUM_EXTENSO.get(texto.replace("tres", "tres"))


def _extrair_contagem(regex: re.Pattern, regex_singular: re.Pattern, texto: str) -> int | None:
    """Tenta extrair contagem explícita; cai no singular implícito."""
    m = regex.search(texto)
    if m:
        for g in m.groups():
            val = _parse_num(g)
            if val is not None:
                return val
    if regex_singular.search(texto):
        return 1
    return None
_RE_VEICULOS = re.compile(
    r"\b(caminh[aã]o|carreta|[oô]nibus|micro-[oô]nibus|carro|autom[oó]vel|"
    r"moto(?:cicleta)?|bicicleta|caminh(?:onete|oneta)|van|trator|"
    r"quadriciclo|ambulância|viatura)\b",
    re.IGNORECASE,
)


@dataclass
class DadosCorpo:
    hora: str | None = None
    periodo_dia: str | None = None   # madrugada/manha/tarde/noite quando sem hora exata
    km: str | None = None
    vitima: str | None = None
    causa: str | None = None
    condicao_climatica: str | None = None
    n_mortos: int | None = None
    n_feridos: int | None = None
    veiculos: str | None = None
    teaser: str | None = None


def _extrair_corpo(html: str, fonte: str, titulo: str = "") -> DadosCorpo:
    soup = BeautifulSoup(html, "html.parser")

    # Remove ruído
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside",
                               "iframe", ".sharedaddy", ".related-posts"]):
        tag.decompose()

    # Pega todos os parágrafos com conteúdo real (>40 chars)
    # Usa <p> diretamente pois seletores de container pegam conteúdo errado
    paragrafos = []
    for p in soup.find_all("p"):
        txt = p.get_text(strip=True)
        if len(txt) > 40:
            paragrafos.append(txt)

    # Fallback: tenta seletores de container se não achou parágrafos
    if not paragrafos:
        for seletor in [".entry-content", ".post-content", ".td-post-content", "article", "main"]:
            el = soup.select_one(seletor)
            if el:
                txt = el.get_text(separator=" ", strip=True)
                if len(txt) > 100:
                    paragrafos = [txt]
                    break

    texto = " ".join(paragrafos)
    texto = re.sub(r"\s+", " ", texto)
    teaser = paragrafos[0][:250] if paragrafos else texto[:250]

    # Extrai campos
    hora_m = _RE_HORA.search(texto)
    hora = hora_m.group(1).replace(":", "h") if hora_m else None

    # Período do dia quando não há hora exata
    periodo_dia = None
    if not hora:
        if re.search(r"\b(madrugada|amanhecer)\b", texto, re.IGNORECASE):
            periodo_dia = "madrugada"
        elif re.search(r"\b(pela manhã|de manhã|início da manhã|manhã cedo)\b", texto, re.IGNORECASE):
            periodo_dia = "manha"
        elif re.search(r"\b(à tarde|na tarde|fim de tarde)\b", texto, re.IGNORECASE):
            periodo_dia = "tarde"
        elif re.search(r"\b(à noite|na noite|início da noite)\b", texto, re.IGNORECASE):
            periodo_dia = "noite"

    km_m = _RE_KM.search(texto)
    km = next((g for g in (km_m.group(1), km_m.group(2), km_m.group(3)) if g), None) if km_m else None

    vitima_m = _RE_VITIMA.search(texto)
    vitima = vitima_m.group(1).strip() if vitima_m else None

    causa_m = _RE_CAUSA.search(texto)
    causa = causa_m.group(1).lower() if causa_m else None

    clima_m = _RE_CLIMA.search(texto)
    clima = clima_m.group(1).lower() if clima_m else None

    # Mortos/feridos: o título costuma ter a contagem mais clara que o corpo
    texto_com_titulo = (titulo + ". " + texto) if titulo else texto
    n_mortos = _extrair_contagem(_RE_MORTOS, _RE_MORTE_SINGULAR, texto_com_titulo)
    n_feridos = _extrair_contagem(_RE_FERIDOS, _RE_FERIDO_SINGULAR, texto_com_titulo)

    # Veículos: coleta todos mencionados, deduplicados
    veiculos_encontrados = list(dict.fromkeys(
        v.lower() for v in _RE_VEICULOS.findall(texto)
    ))
    veiculos = ", ".join(veiculos_encontrados[:5]) if veiculos_encontrados else None

    return DadosCorpo(
        hora=hora, periodo_dia=periodo_dia, km=km, vitima=vitima, causa=causa,
        condicao_climatica=clima, n_mortos=n_mortos,
        n_feridos=n_feridos, veiculos=veiculos, teaser=teaser,
    )


def buscar_artigos_para_enriquecer(limite: int = 200, severidades: list = None) -> list[dict]:
    """Retorna artigos que ainda não têm hora extraída."""
    sevs = severidades or ["fatal", "grave"]
    placeholders = ",".join(f"'{s}'" for s in sevs)

    with _conexao() as con:
        rows = con.execute(f"""
            SELECT id, url, fonte, severidade, titulo
            FROM acidentes
            WHERE (body_scraped IS NULL OR body_scraped = FALSE)
              AND severidade IN ({placeholders})
              AND fonte IN ('rdplanalto', 'uirapuru')
              AND (tipo_cobertura IS NULL OR tipo_cobertura != 'acompanhamento')
            ORDER BY
                CASE severidade WHEN 'fatal' THEN 1 WHEN 'grave' THEN 2 ELSE 3 END,
                id
            LIMIT {limite}
        """).fetchall()

    return [{"id": r[0], "url": r[1], "fonte": r[2], "severidade": r[3], "titulo": r[4]} for r in rows]


def atualizar_artigo(id: int, dados: DadosCorpo):
    campos = {
        "hora_acidente":      dados.hora,
        "periodo_dia":        dados.periodo_dia,
        "km_rodovia":         dados.km,
        "teaser":             dados.teaser,
        "vitima_nome":        dados.vitima,
        "causa_acidente":     dados.causa,
        "condicao_climatica": dados.condicao_climatica,
        "n_mortos":           dados.n_mortos,
        "n_feridos":          dados.n_feridos,
        "veiculos":           dados.veiculos,
    }
    updates = [f"{col} = ?" for col, val in campos.items() if val is not None]
    vals = [val for val in campos.values() if val is not None]
    # Sempre marca como scraped, mesmo que nada tenha sido extraído
    updates.append("body_scraped = TRUE")
    vals.append(id)
    with _conexao() as con:
        con.execute(f"UPDATE acidentes SET {', '.join(updates)} WHERE id = ?", vals)


def enriquecer(limite: int = 200, severidades: list = None, delay: float = 1.2) -> dict:
    """
    Busca o corpo dos artigos mais relevantes e atualiza o banco.
    Retorna estatísticas do processo.
    """
    artigos = buscar_artigos_para_enriquecer(limite=limite, severidades=severidades)
    logger.info(f"Artigos para enriquecer: {len(artigos)}")

    session = requests.Session()
    session.headers.update(HEADERS)

    stats = {"total": len(artigos), "com_hora": 0, "com_km": 0, "com_vitima": 0, "erros": 0}

    for i, art in enumerate(artigos, 1):
        try:
            resp = session.get(art["url"], timeout=15)
            if resp.status_code != 200:
                stats["erros"] += 1
                continue

            dados = _extrair_corpo(resp.text, art["fonte"], titulo=art.get("titulo", ""))
            atualizar_artigo(art["id"], dados)

            if dados.hora:
                stats["com_hora"] += 1
            if dados.km:
                stats["com_km"] += 1
            if dados.vitima:
                stats["com_vitima"] += 1

            if i % 25 == 0 or i == len(artigos):
                logger.info(
                    f"  [{i}/{len(artigos)}] hora={stats['com_hora']} "
                    f"km={stats['com_km']} vitima={stats['com_vitima']}"
                )

            time.sleep(delay)

        except Exception as e:
            logger.warning(f"Erro em {art['url']}: {e}")
            stats["erros"] += 1

    return stats
