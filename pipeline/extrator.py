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
]

# Compila regex para extração de município (busca no título original com acentos)
_RE_MUNICIPIO = re.compile(
    r"\bem\s+(" + "|".join(re.escape(m) for m in _MUNICIPIOS) + r")\b",
    re.IGNORECASE,
)

# Também aceita "em Passo Fundo" vindo do slug normalizado
_RE_MUNICIPIO_SLUG = re.compile(
    r"\b(passo fundo|carazinho|marau|erechim|sarandi|soledade|tapejara|"
    r"sertao|casca|colorado|vila maria|ronda alta|pontao|coxilha|ernestina|"
    r"gaurama|erebango|viadutos|serafina correa)\b",
    re.IGNORECASE,
)


def _normalizar(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _slug_para_texto(slug: str) -> str:
    return slug.replace("-", " ")


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
        _mapa = {
            "passo fundo": "Passo Fundo",
            "carazinho": "Carazinho",
            "marau": "Marau",
            "erechim": "Erechim",
            "sarandi": "Sarandi",
            "soledade": "Soledade",
            "tapejara": "Tapejara",
            "sertao": "Sertão",
            "casca": "Casca",
            "colorado": "Colorado",
            "vila maria": "Vila Maria",
            "ronda alta": "Ronda Alta",
            "pontao": "Pontão",
            "coxilha": "Coxilha",
            "ernestina": "Ernestina",
            "gaurama": "Gaurama",
            "erebango": "Erebango",
            "viadutos": "Viadutos",
            "serafina correa": "Serafina Corrêa",
        }
        return _mapa.get(m2.group(1).lower(), "Passo Fundo")

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

_RUIDO_FINAL = re.compile(
    r"\s+(?:passo\s+fundo|em\s+passo|em|no|na|passo|fundo|rs|"
    r"carazinho|marau|erechim|sarandi|soledade|colorado|coxilha)\s*$",
    re.IGNORECASE,
)


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
            rua1 = _RUIDO_FINAL.sub("", m.group("rua1")).strip().title()
            rua2 = _RUIDO_FINAL.sub("", m.group("rua2")).strip().title()
            endereco = f"{rua1} e {rua2}, {municipio}, RS, Brasil"
            return {
                "tipo": tipo,
                "endereco": endereco,
                "rua1": rua1,
                "rua2": rua2,
                "municipio_loc": municipio,
            }

        if tipo == "rodovia":
            rod = m.group("rod").upper().replace(" ", "-").replace("--", "-")
            return {"tipo": tipo, "endereco": f"{rod}, {municipio}, RS, Brasil"}

        if tipo == "trevo":
            trevo = _RUIDO_FINAL.sub("", m.group("trevo")).strip().title()
            return {"tipo": tipo, "endereco": f"Trevo {trevo}, {municipio}, RS, Brasil"}

        if tipo == "logradouro":
            tipo_log = m.group("tipo").title()
            nome = _RUIDO_FINAL.sub("", m.group("nome")).strip().title()
            return {"tipo": tipo, "endereco": f"{tipo_log} {nome}, {municipio}, RS, Brasil"}

        if tipo == "bairro":
            bairro = _RUIDO_FINAL.sub("", m.group("bairro")).strip().title()
            return {"tipo": tipo, "endereco": f"Bairro {bairro}, {municipio}, RS, Brasil"}

    return None
