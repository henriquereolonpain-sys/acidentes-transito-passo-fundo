"""
Geocodifica endereços usando Nominatim (logradouros/rodovias) e
Overpass API (cruzamentos de ruas — muito mais preciso para OSM local).
"""

import logging
import time
import re

import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

logger = logging.getLogger(__name__)

_geolocator = Nominatim(
    user_agent="passo-fundo-acidentes/1.0",
    timeout=15,
)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Bounding boxes por município (sul, oeste, norte, leste)
_BBOX_MUNICIPIOS = {
    "Passo Fundo":       (-28.35, -52.60, -28.10, -52.25),
    "Carazinho":         (-28.40, -52.90, -28.15, -52.60),
    "Marau":             (-28.55, -52.30, -28.30, -52.00),
    "Erechim":           (-27.75, -52.40, -27.55, -52.15),
    "Sarandi":           (-27.98, -52.98, -27.80, -52.78),
    "Soledade":          (-28.95, -52.65, -28.65, -52.40),
    "Vila Maria":        (-28.55, -52.50, -28.40, -52.30),
}
_BBOX_DEFAULT = (-28.50, -52.70, -27.50, -52.00)  # região geral do planalto


def _bbox_para_municipio(municipio: str) -> tuple:
    return _BBOX_MUNICIPIOS.get(municipio, _BBOX_DEFAULT)


def _slug_para_termo_busca(nome: str) -> str:
    """
    Extrai o termo mais distintivo de um nome de rua para usar no Overpass.
    Remove stopwords e prefixos comuns.
    """
    stopwords = {"rua", "avenida", "av", "de", "da", "do", "das", "dos",
                 "e", "em", "na", "no", "a", "o", "as", "os"}
    palavras = [p for p in nome.lower().split() if p not in stopwords and len(p) > 2]
    if not palavras:
        return nome
    # Retorna a palavra mais longa (geralmente o sobrenome/nome próprio mais específico)
    return max(palavras, key=len)


def _overpass_cruzamento(rua1: str, rua2: str, municipio: str) -> tuple[float, float] | None:
    """
    Usa Overpass API para encontrar o nó de interseção de duas ruas.
    rua1 e rua2 são nomes sem acento (vindos do slug).
    """
    bbox = _bbox_para_municipio(municipio)
    bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"

    termo1 = _slug_para_termo_busca(rua1)
    termo2 = _slug_para_termo_busca(rua2)

    query = f"""
[out:json][timeout:30];
(
  way({bbox_str})[highway][name~"{termo1}",i];
)->.r1;
(
  way({bbox_str})[highway][name~"{termo2}",i];
)->.r2;
node(w.r1)(w.r2);
out body;
"""
    try:
        time.sleep(1)
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=35)
        resp.raise_for_status()
        data = resp.json()
        elementos = data.get("elements", [])
        if elementos:
            el = elementos[0]
            logger.debug(f"Overpass achou cruzamento '{rua1}' x '{rua2}': ({el['lat']}, {el['lon']})")
            return (el["lat"], el["lon"])
    except Exception as e:
        logger.warning(f"Overpass erro para '{rua1}' x '{rua2}': {e}")

    return None


def _nominatim_geocode(endereco: str, tentativas: int = 2) -> tuple[float, float] | None:
    for tentativa in range(1, tentativas + 1):
        try:
            time.sleep(1.2)
            location = _geolocator.geocode(
                endereco,
                exactly_one=True,
                language="pt",
                country_codes="br",
            )
            if location:
                return (location.latitude, location.longitude)
            return None
        except GeocoderTimedOut:
            logger.warning(f"Nominatim timeout ({tentativa}/{tentativas}): {endereco}")
            time.sleep(2 ** tentativa)
        except GeocoderServiceError as e:
            logger.error(f"Nominatim erro: {e}")
            return None
    return None


_RE_BR = re.compile(r"\bBR-?\s*(\d{2,3})\b", re.IGNORECASE)


def _parse_km(km_rodovia) -> float | None:
    """'365,6' / '220' / 'km 14' -> float."""
    if km_rodovia is None:
        return None
    m = re.search(r"(\d+(?:[,.]\d+)?)", str(km_rodovia))
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def geocodificar(endereco: str, loc_tipo: str = None,
                 rua1: str = None, rua2: str = None,
                 municipio: str = "Passo Fundo",
                 km_rodovia=None) -> tuple[float, float] | None:
    """
    Geocodifica um endereço usando a estratégia mais adequada ao tipo de local.

    - Cruzamentos: Overpass primeiro (mais preciso), cai no Nominatim.
    - Rodovia federal (BR) com km: usa a referência km->coordenada da PRF (ponto exato).
    - Resto: Nominatim direto.
    """
    if loc_tipo == "cruzamento" and rua1 and rua2:
        coords = _overpass_cruzamento(rua1, rua2, municipio)
        if coords:
            return coords
        logger.debug(f"Overpass falhou, tentando Nominatim para '{rua1}, {municipio}'")
        coords = _nominatim_geocode(f"{rua1}, {municipio}, RS, Brasil")
        if coords:
            return coords

    # Rodovia federal com km conhecido: usa o ponto exato da referência PRF
    if loc_tipo == "rodovia" and km_rodovia is not None:
        m_br = _RE_BR.search(endereco or "")
        km = _parse_km(km_rodovia)
        if m_br and km is not None:
            from pipeline.km_ref import buscar_coord
            coords = buscar_coord(m_br.group(1), km)
            if coords:
                logger.debug(f"km_ref: BR-{m_br.group(1)} km {km} -> {coords}")
                return coords

    return _nominatim_geocode(endereco)
