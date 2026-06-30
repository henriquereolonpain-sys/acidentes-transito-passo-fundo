"""Testes das funções puras do geocoder (parsing de BR e km)."""
import pytest

from pipeline.geocoder import _RE_BR, _parse_km
from pipeline.km_ref import _normalizar_br


class TestParseBR:
    @pytest.mark.parametrize("endereco,esperado", [
        ("BR-285, Colorado, RS, Brasil", "285"),
        ("BR-153, Erechim, RS", "153"),
        ("acidente na BR 470", "470"),
        ("BR-116, Passo Fundo", "116"),
    ])
    def test_extrai_br(self, endereco, esperado):
        m = _RE_BR.search(endereco)
        assert m is not None
        assert m.group(1) == esperado

    def test_endereco_sem_br(self):
        assert _RE_BR.search("ERS-324, Passo Fundo, RS") is None


class TestParseKm:
    @pytest.mark.parametrize("valor,esperado", [
        ("365,6", 365.6),
        ("220", 220.0),
        ("km 14", 14.0),
        ("48.5", 48.5),
    ])
    def test_parse(self, valor, esperado):
        assert _parse_km(valor) == esperado

    def test_none(self):
        assert _parse_km(None) is None
        assert _parse_km("sem numero") is None


class TestNormalizarBR:
    @pytest.mark.parametrize("valor,esperado", [
        ("BR-285", "285"),
        ("285", "285"),
        ("0285", "285"),
        ("285.0", "285"),
    ])
    def test_normaliza(self, valor, esperado):
        assert _normalizar_br(valor) == esperado

    def test_none(self):
        assert _normalizar_br(None) is None
        assert _normalizar_br("sem digito") is None
