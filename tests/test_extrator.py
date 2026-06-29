"""Testes da extração de município e localização a partir de slugs de notícias."""
import pytest

from pipeline.extrator import extrair_municipio, extrair_localizacao


class TestExtrairMunicipio:
    def test_passo_fundo_default(self):
        assert extrair_municipio("Acidente em Passo Fundo", "acidente-passo-fundo") == "Passo Fundo"

    def test_municipio_vizinho_do_titulo(self):
        assert extrair_municipio("Homem morre na ERS-324 em Marau", "homem-morre-ers-324-marau") == "Marau"

    def test_municipio_com_acento_normalizado(self):
        # "Getúlio Vargas" deve voltar com acento correto
        assert extrair_municipio("Acidente em Getúlio Vargas", "acidente-getulio-vargas") == "Getúlio Vargas"

    def test_sem_municipio_reconhecido_cai_em_passo_fundo(self):
        assert extrair_municipio("Acidente em cidade desconhecida", "acidente-cidade-x") == "Passo Fundo"

    def test_extrai_do_slug_quando_titulo_nao_tem(self):
        assert extrair_municipio("Grave acidente registrado", "acidente-grave-carazinho") == "Carazinho"


class TestExtrairLocalizacao:
    def test_cruzamento_de_ruas(self):
        slug = "acidente-e-registrado-no-cruzamento-das-ruas-joao-de-cesaro-e-coronel-pelegrini-em-passo-fundo"
        loc = extrair_localizacao(slug, "Passo Fundo")
        assert loc is not None
        assert loc["tipo"] == "cruzamento"
        assert "Joao De Cesaro" in loc["rua1"]
        assert "Coronel Pelegrini" in loc["rua2"]

    def test_rodovia_estadual(self):
        loc = extrair_localizacao("acidente-na-ers-324-em-passo-fundo", "Passo Fundo")
        assert loc["tipo"] == "rodovia"
        assert "ERS-324" in loc["endereco"]

    def test_rodovia_federal(self):
        loc = extrair_localizacao("colisao-na-br-285-colorado", "Colorado")
        assert loc["tipo"] == "rodovia"
        assert "BR-285" in loc["endereco"]
        assert "Colorado" in loc["endereco"]

    def test_logradouro_avenida(self):
        loc = extrair_localizacao("grave-acidente-avenida-brasil-passo-fundo", "Passo Fundo")
        assert loc["tipo"] == "logradouro"
        assert "Avenida Brasil" in loc["endereco"]

    def test_trevo(self):
        loc = extrair_localizacao("colisao-no-trevo-bortot-em-passo-fundo", "Passo Fundo")
        assert loc["tipo"] == "trevo"
        assert "Bortot" in loc["endereco"]

    def test_bairro(self):
        loc = extrair_localizacao("acidente-no-bairro-sao-jose-passo-fundo", "Passo Fundo")
        assert loc["tipo"] == "bairro"
        assert "Sao Jose" in loc["endereco"]

    def test_municipio_usado_no_endereco(self):
        # o município passado deve aparecer no endereço montado (geocoding correto)
        loc = extrair_localizacao("acidente-na-ers-324-vila-maria", "Vila Maria")
        assert "Vila Maria" in loc["endereco"]

    def test_slug_sem_local_retorna_none(self):
        loc = extrair_localizacao("homem-e-preso-por-furto", "Passo Fundo")
        assert loc is None
