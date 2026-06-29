"""Testes da extração de dados do corpo: mortos, feridos, hora, km, número por extenso."""
import pytest

from pipeline.body_scraper import (
    _extrair_contagem, _parse_num,
    _RE_MORTOS, _RE_MORTE_SINGULAR, _RE_FERIDOS, _RE_FERIDO_SINGULAR,
    _RE_HORA, _RE_KM,
)


class TestParseNum:
    def test_digito(self):
        assert _parse_num("3") == 3

    @pytest.mark.parametrize("palavra,esperado", [
        ("um", 1), ("uma", 1), ("dois", 2), ("duas", 2),
        ("três", 3), ("tres", 3), ("quatro", 4), ("cinco", 5),
    ])
    def test_por_extenso(self, palavra, esperado):
        assert _parse_num(palavra) == esperado

    def test_invalido_retorna_none(self):
        assert _parse_num("xyz") is None
        assert _parse_num(None) is None


class TestMortos:
    @pytest.mark.parametrize("texto,esperado", [
        ("colisão deixa dois mortos na BR-285", 2),
        ("acidente resultou na morte de três pessoas", 3),
        ("Homem morre após saída de pista", 1),          # singular implícito
        ("idosa morreu após atropelamento", 1),
        ("acidente deixa uma pessoa morta", 1),
        ("grave acidente com morte registrado", 1),       # "com morte"
        ("sete crianças mortas no acidente", 7),          # substantivo entre num e morto
    ])
    def test_extrai_mortos(self, texto, esperado):
        assert _extrair_contagem(_RE_MORTOS, _RE_MORTE_SINGULAR, texto) == esperado

    def test_sem_morte_retorna_none(self):
        assert _extrair_contagem(_RE_MORTOS, _RE_MORTE_SINGULAR, "colisão sem vítimas no centro") is None


class TestFeridos:
    @pytest.mark.parametrize("texto,esperado", [
        ("deixa três pessoas feridas na ERS-324", 3),
        ("colisão deixa quatro feridos", 4),
        ("duas pessoas ficaram feridas no acidente", 2),
        ("motorista ficou ferido", 1),                    # singular
        ("sete crianças feridas em ônibus escolar", 7),
    ])
    def test_extrai_feridos(self, texto, esperado):
        assert _extrair_contagem(_RE_FERIDOS, _RE_FERIDO_SINGULAR, texto) == esperado


class TestHoraKm:
    @pytest.mark.parametrize("texto,esperado", [
        ("ocorreu por volta das 7h30min", "7h30min"),
        ("acidente às 14h no centro", "14h"),
        ("por volta das 22h30 na BR-285", "22h30"),
    ])
    def test_hora(self, texto, esperado):
        m = _RE_HORA.search(texto)
        assert m is not None
        assert m.group(1) == esperado

    @pytest.mark.parametrize("texto,esperado", [
        ("no km 43 da BR-153", "43"),
        ("registrado no km 365,6 da BR-285", "365,6"),
        ("no quilômetro 220 da ERS-324", "220"),
    ])
    def test_km(self, texto, esperado):
        m = _RE_KM.search(texto)
        assert m is not None
        valor = next(g for g in m.groups() if g)
        assert valor == esperado
