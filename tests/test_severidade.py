"""Testes da classificação de severidade pelos scrapers."""
import pytest

from scrapers.rdplanalto import classificar_severidade


class TestClassificarSeveridade:
    @pytest.mark.parametrize("titulo", [
        "Homem morre em acidente na ERS-324",
        "Colisão deixa duas pessoas mortas na BR-285",
        "Identificada vítima fatal do acidente",
        "Idosa morreu após atropelamento",
        "Motociclista vem a óbito em colisão",
    ])
    def test_fatal(self, titulo):
        assert classificar_severidade(titulo) == "fatal"

    @pytest.mark.parametrize("titulo", [
        "Grave acidente deixa três feridos na ERS-135",
        "Colisão deixa motorista ferido",
        "Acidente deixa pessoa hospitalizada",
    ])
    def test_grave(self, titulo):
        assert classificar_severidade(titulo) == "grave"

    @pytest.mark.parametrize("titulo", [
        "Balada Segura autua 15 motoristas por embriaguez",
        "Operação Corpus Christi reforça fiscalização",
        "DNIT anuncia obras na BR-153",
    ])
    def test_fiscalizacao(self, titulo):
        assert classificar_severidade(titulo) == "fiscalizacao"

    @pytest.mark.parametrize("titulo", [
        "Colisão entre dois veículos na Avenida Brasil",
        "Carro bate em poste no centro",
    ])
    def test_colisao_default(self, titulo):
        assert classificar_severidade(titulo) == "colisao"

    def test_fatal_tem_prioridade_sobre_grave(self):
        # título com "grave" E "morre" deve ser fatal
        assert classificar_severidade("Grave acidente deixa um morto e dois feridos") == "fatal"

    def test_debitos_nao_e_fatal(self):
        # regressão: "débitos" não deve disparar fatal por causa de "bito"
        titulo = "Veículo com quase R$ 20 mil em débitos é retirado de circulação"
        assert classificar_severidade(titulo) != "fatal"
