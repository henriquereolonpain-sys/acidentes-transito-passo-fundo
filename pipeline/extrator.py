"""
Extrai localização e município de slugs/títulos de notícias de acidentes.
"""

import re
import unicodedata


# Municípios conhecidos da região do Planalto (ordem importa: mais específico primeiro)
_MUNICIPIOS = [
    "Passo Fundo", "Carazinho", "Marau", "Erechim", "Sarandi",
    "Lagoa Vermelha", "Getulio Vargas", "Getúlio Vargas", "Soledade",
    "Tapejara", "Sertao", "Sertão", "Agua Santa", "Água Santa",
    "Casca", "Guapore", "Guaporé", "Nao-Me-Toque", "Não-Me-Toque",
    "Colorado", "Vila Maria", "Ronda Alta", "Pontao", "Pontão",
    "Coxilha", "Ernestina", "Chapadao do Sul", "Chapadão do Sul",
    "Palmeira das Missoes", "Palmeira das Missões", "Serafina Correa",
    "Serafina Corrêa", "Gaurama", "Erebango", "Itatiba do Sul",
    "Viadutos", "Barra do Rio Azul", "Marcelino Ramos",
    # microrregião de Tapejara (Alto Uruguai / Norte gaúcho)
    "Sananduva", "Ibiaca", "Ibiaçá", "Ibiraiaras", "Vila Langaro", "Vila Lângaro",
    "Charrua", "Cacique Doble", "Santa Cecilia do Sul", "Santa Cecília do Sul",
    "Sao Joao da Urtiga", "São João da Urtiga", "Machadinho",
    "Maximiliano de Almeida", "Tupanci do Sul", "Caseiros", "Ciriaco", "Ciríaco",
    "David Canabarro", "Vanini", "Muliterno", "Santo Expedito do Sul",
    "Nova Alvorada", "Barracao", "Barracão",
]

# Compila regex para extração de município (busca no título original com acentos)
_RE_MUNICIPIO = re.compile(
    r"\bem\s+(" + "|".join(re.escape(m) for m in _MUNICIPIOS) + r")\b",
    re.IGNORECASE,
)

# _RE_MUNICIPIO_SLUG e _MUNI_NORM são construídos abaixo (após _normalizar)


def _normalizar(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _slug_para_texto(slug: str) -> str:
    return slug.replace("-", " ")


# Mapa nome-normalizado -> nome próprio (prefere a variante acentuada) e regex
# de município no slug — ambos a partir da lista COMPLETA de municípios, para
# que extrair_municipio reconheça as mesmas cidades que a extração de local.
_MUNI_NORM = {}
for _m in _MUNICIPIOS:
    _k = _normalizar(_m)
    if _k not in _MUNI_NORM or any(ord(c) > 127 for c in _m):
        _MUNI_NORM[_k] = _m
_RE_MUNICIPIO_SLUG = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_MUNI_NORM, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)


def extrair_municipio(titulo: str, slug: str) -> str:
    """
    Tenta extrair o município da notícia.
    Retorna o nome normalizado ou 'Passo Fundo' como default.
    """
    # 1. Busca no título com acentos
    m = _RE_MUNICIPIO.search(titulo)
    if m:
        nome = m.group(1).strip().title()
        # Normaliza variantes
        _norm = {
            "Nao-Me-Toque": "Não-Me-Toque",
            "Getulio Vargas": "Getúlio Vargas",
            "Agua Santa": "Água Santa",
            "Pontao": "Pontão",
            "Serafina Correa": "Serafina Corrêa",
            "Chapadao Do Sul": "Chapadão do Sul",
            "Palmeira Das Missoes": "Palmeira das Missões",
            "Guapore": "Guaporé",
        }
        return _norm.get(nome, nome)

    # 2. Busca no slug normalizado
    texto_slug = _slug_para_texto(_normalizar(slug))
    m2 = _RE_MUNICIPIO_SLUG.search(texto_slug)
    if m2:
        return _MUNI_NORM.get(m2.group(1).lower(), "Passo Fundo")

    return "Passo Fundo"


# Padrões de localização em ordem de especificidade
_PADROES = [
    # cruzamento entre duas ruas
    (
        "cruzamento",
        re.compile(
            r"cruzamento\s+(?:d[ao]s?\s+)?ruas?\s+"
            r"(?P<rua1>[\w\s]+?)\s+e\s+(?P<rua2>[\w\s]+?)"
            r"(?:\s+(?:na|no|em)\s+[\w\s]+)?$",
            re.IGNORECASE,
        ),
    ),
    # rodovias estaduais/federais
    (
        "rodovia",
        re.compile(r"(?P<rod>(?:ers|br|rs)\s*-?\s*\d{2,3})", re.IGNORECASE),
    ),
    # trevo / rotatória (limita a 3 palavras para não capturar descrição do acidente)
    (
        "trevo",
        re.compile(
            r"trevo\s+(?:d[aeo]\s+)?(?!acesso|bairro|entrada)(?P<trevo>[\w]+)",
            re.IGNORECASE,
        ),
    ),
    # avenida / rua / alameda / estrada
    (
        "logradouro",
        re.compile(
            r"(?P<tipo>avenida|av\b|rua|alameda|estrada|travessa|rodovia)\s+"
            r"(?P<nome>(?:[\w]+\s*){1,6})",
            re.IGNORECASE,
        ),
    ),
    # bairro
    (
        "bairro",
        re.compile(
            r"(?:no\s+bairro|bairro)\s+(?P<bairro>(?:[\w]+\s*){1,4})",
            re.IGNORECASE,
        ),
    ),
]

# Ruído no fim do nome: conectores + qualquer município conhecido (sem acento).
# Ordena por tamanho decrescente pra casar "passo fundo" antes de "passo".
_NOISE_MUNI = sorted({_normalizar(m) for m in _MUNICIPIOS}, key=len, reverse=True)
_RUIDO_FINAL = re.compile(
    r"\s+(?:" + "|".join(re.escape(w) for w in _NOISE_MUNI) +
    r"|em|no|na|de|da|do|dos|das|rs|regiao|interior|centro|area|central|"
    r"proximo|perto|frente)\s*$",
    re.IGNORECASE,
)


def _limpar_ruido(s: str) -> str:
    """Remove repetidamente conectores/municípios grudados no fim do nome."""
    prev = None
    while prev != s:
        prev = s
        s = _RUIDO_FINAL.sub("", s).strip()
    return s


# Fallback a nível de cidade (aproximado) — só quando nenhum local específico
# casou. Exige um município conhecido no texto (evita casar ruído/estatística).
_CIDADE_ALT = "|".join(re.escape(w) for w in _NOISE_MUNI)  # normalizados, maiores primeiro
_PADROES += [
    ("centro", re.compile(
        r"(?:centro|area\s+central|regiao\s+central)\s+d[eo]\s+(?P<cidade>"
        + _CIDADE_ALT + r")\b", re.IGNORECASE)),
    ("cidade", re.compile(
        r"interior\s+d[eo]\s+(?P<cidade>" + _CIDADE_ALT + r")\b", re.IGNORECASE)),
    ("cidade", re.compile(
        r"\bentre\s+(?P<cidade>" + _CIDADE_ALT + r")\s+e\s+(?:" + _CIDADE_ALT + r")\b",
        re.IGNORECASE)),
    ("cidade", re.compile(
        r"\bem\s+(?P<cidade>" + _CIDADE_ALT + r")\b", re.IGNORECASE)),
]


def extrair_localizacao(slug: str, municipio: str = "Passo Fundo") -> dict | None:
    """
    Extrai localização do slug. Usa o município fornecido nas queries de geocodificação.
    Retorna dict com tipo, endereco, e campos auxiliares para o geocoder.
    """
    texto = _slug_para_texto(_normalizar(slug))

    for tipo, padrao in _PADROES:
        m = padrao.search(texto)
        if not m:
            continue

        if tipo == "cruzamento":
            rua1 = _limpar_ruido(m.group("rua1")).title()
            rua2 = _limpar_ruido(m.group("rua2")).title()
            endereco = f"{rua1} e {rua2}, {municipio}, RS, Brasil"
            return {
                "tipo": tipo,
                "endereco": endereco,
                "rua1": rua1,
                "rua2": rua2,
                "municipio_loc": municipio,
            }

        if tipo == "rodovia":
            # normaliza "ers324"/"br 386" -> "ERS-324"/"BR-386" (Nominatim não acha sem hífen)
            rod = re.sub(r"[\s-]", "", m.group("rod").upper())
            rod = re.sub(r"^(ERS|BR|RS)(\d+)$", r"\1-\2", rod)
            return {"tipo": tipo, "endereco": f"{rod}, {municipio}, RS, Brasil"}

        if tipo == "trevo":
            trevo = _limpar_ruido(m.group("trevo")).title()
            return {"tipo": tipo, "endereco": f"Trevo {trevo}, {municipio}, RS, Brasil"}

        if tipo == "logradouro":
            tipo_log = m.group("tipo").title()
            nome = _limpar_ruido(m.group("nome")).title()
            return {"tipo": tipo, "endereco": f"{tipo_log} {nome}, {municipio}, RS, Brasil"}

        if tipo == "bairro":
            bairro = _limpar_ruido(m.group("bairro")).title()
            return {"tipo": tipo, "endereco": f"Bairro {bairro}, {municipio}, RS, Brasil"}

        if tipo in ("centro", "cidade"):
            cidade_norm = _normalizar(m.group("cidade")).strip()
            # Passo Fundo já tem cobertura precisa densa — não empilha centroides lá
            if cidade_norm == "passo fundo":
                continue
            cidade = m.group("cidade").strip().title()
            if tipo == "centro":
                return {"tipo": "centro", "endereco": f"Centro, {cidade}, RS, Brasil"}
            return {"tipo": "cidade", "endereco": f"{cidade}, RS, Brasil"}

    return None
