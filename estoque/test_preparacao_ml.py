from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import PecaAdminForm
from .models import Categoria, FotoPeca, Peca
from mercadolivre.forms import PublicacaoForm
from mercadolivre.models import Publicacao, Selecao


@override_settings(MERCADOLIVRE_ENABLED=False, MERCADOLIVRE_PUBLISH_ENABLED=False)
class PreparacaoMercadoLivreTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nome="Preparação ML")
        self.dados = dict(nome="Farol", categoria=self.categoria.pk, custo="0", preco_venda="100",
                          quantidade="2", status="disponivel", condicao="usada")
        self.meta = {"id": "MLB123", "settings": {"max_pictures_per_item": 1}}

    def anuncio(self, peca, data=None, attrs=None):
        return PublicacaoForm(data, peca=peca, categoria=self.meta, atributos=attrs or [],
                              tipos=[{"id": "gold_special", "name": "Clássico"}])

    @patch("mercadolivre.publicacao_api.ClientePublicacao.enviar")
    def test_cadastro_guarda_preparacao_sem_conexao_nem_publicacao(self, api):
        form = PecaAdminForm({**self.dados, "ml_titulo": "Farol original", "ml_descricao": "Peça testada",
            "ml_categoria_id": "MLB123", "ml_preco": "140.50", "ml_quantidade": "1",
            "ml_retirada": "true", "ml_frete_gratis": "false"})
        self.assertTrue(form.is_valid(), form.errors)
        peca = form.save()
        peca.refresh_from_db()
        self.assertEqual(peca.ml_preco, Decimal("140.50"))
        self.assertTrue(peca.ml_retirada)
        self.assertIs(peca.ml_frete_gratis, False)
        self.assertEqual((peca.preco_venda, peca.quantidade), (100, 2))
        self.assertFalse(peca.postada_online)
        self.assertFalse(Selecao.objects.exists())
        self.assertFalse(Publicacao.objects.exists())
        api.assert_not_called()

    def test_campos_opcionais_e_validacao(self):
        form = PecaAdminForm(self.dados)
        self.assertTrue(form.is_valid(), form.errors)
        peca = form.save()
        self.assertIsNone(peca.ml_retirada)
        self.assertIsNone(peca.ml_preco)
        for campo, valor in [("ml_categoria_id", "categoria"), ("ml_preco", "0"), ("ml_quantidade", "0")]:
            form = PecaAdminForm({**self.dados, campo: valor})
            self.assertFalse(form.is_valid())
            self.assertIn(campo, form.errors)

    def test_prefill_limita_saldo_fotos_e_mapeia_atributos(self):
        peca = Peca.objects.create(nome="Farol", categoria=self.categoria, preco_venda=100, quantidade=2,
            ml_titulo="Farol original", ml_descricao="Testado", ml_preco=140, ml_quantidade=4,
            ml_fabricante="Bosch", ml_numero_peca="ABC", ml_retirada=True, ml_frete_gratis=False,
            observacoes="Informação interna")
        foto = FotoPeca.objects.create(peca=peca, imagem="teste/a.jpg")
        FotoPeca.objects.create(peca=peca, imagem="teste/b.jpg")
        attrs = [{"id": "BRAND", "name": "Marca", "value_type": "list", "values": [{"id": "1", "name": "Bosch"}]},
                 {"id": "PART_NUMBER", "name": "Referência", "value_type": "string"}]
        form = self.anuncio(peca, attrs=attrs)
        self.assertEqual(form["titulo"].value(), "Farol original")
        self.assertEqual(form["descricao"].value(), "Testado")
        self.assertEqual(form["quantidade"].value(), 2)
        self.assertEqual(form["attr_BRAND"].value(), "1")
        self.assertEqual(form["attr_PART_NUMBER"].value(), "ABC")
        self.assertEqual(form["fotos"].value(), [foto.pk])
        self.assertIn("saldo atual", form.fields["quantidade"].help_text)

    def test_edicoes_e_desmarcacoes_prevalecem_sobre_sugestoes(self):
        peca = Peca.objects.create(nome="Farol", categoria=self.categoria, preco_venda=100, quantidade=2,
            ml_descricao="Texto salvo", ml_retirada=True, ml_frete_gratis=True, ml_tipo="gold_pro")
        FotoPeca.objects.create(peca=peca, imagem="teste/a.jpg")
        sugestao = self.anuncio(peca)
        self.assertEqual(sugestao["tipo"].value(), "")
        self.assertEqual(sugestao.fields["tipo"].choices[0][0], "")
        form = self.anuncio(peca, {"titulo": "Outro título", "descricao": "", "preco": "150",
            "quantidade": "1", "condicao": "used", "tipo": "gold_special", "envio": "me2"})
        self.assertFalse(form.is_valid())
        self.assertEqual(form["descricao"].value(), "")
        self.assertFalse(form.cleaned_data["retirada"])
        self.assertFalse(form.cleaned_data["frete_gratis"])
        self.assertFalse(form["fotos"].value())
        self.assertEqual(form.cleaned_data["preco"], Decimal("150"))

    def test_admin_e_edicao_exibem_campos_sem_conta_ml(self):
        self.client.force_login(get_user_model().objects.create_superuser("preparador"))
        response = self.client.get(reverse("admin:estoque_peca_add"))
        self.assertContains(response, "Preparar anúncio no Mercado Livre")
        self.assertContains(response, 'name="ml_descricao"')
        peca = Peca.objects.create(nome="Farol", categoria=self.categoria, preco_venda=100, quantidade=2)
        url = reverse("estoque:editar", args=[peca.pk])
        self.assertContains(self.client.get(url), 'name="ml_descricao"')
        response = self.client.post(url, {**self.dados, "versao_estoque": peca.atualizado_em.isoformat(),
                                        "ml_descricao": "Descrição para anúncio"})
        self.assertEqual(response.status_code, 302)
        peca.refresh_from_db()
        self.assertEqual(peca.ml_descricao, "Descrição para anúncio")
        self.assertEqual(peca.quantidade, 2)
