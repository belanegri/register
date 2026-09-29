from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.contrib.admin.sites import site
from django.db import IntegrityError, transaction
from .models import Peca, Categoria
from .codigo_barras import gerar_svg


class CodigoBarrasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("barcode_admin")
        cls.peca = Peca.objects.create(nome="Farol", categoria=Categoria.objects.first(), preco_venda=25)

    def test_sequencia_preserva_legado_e_unicidade(self):
        nova = Peca.objects.create(nome="Lanterna", categoria=self.peca.categoria, preco_venda=20)
        self.assertEqual(int(nova.codigo[3:]), int(self.peca.codigo[3:]) + 1)
        antiga = Peca.objects.create(codigo="PC-000123", nome="Legado", categoria=self.peca.categoria, preco_venda=10)
        antiga.save()
        self.assertEqual(antiga.codigo, "PC-000123")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Peca.objects.create(codigo=nova.codigo, nome="Duplicada", categoria=self.peca.categoria, preco_venda=1)

    def test_codigo_svg_e_permissoes(self):
        url = reverse("estoque:codigo_barras", args=[self.peca.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        sem_permissao = get_user_model().objects.create_user("sem_barcode")
        self.client.force_login(sem_permissao)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.user)
        resposta = self.client.get(url)
        self.assertEqual(resposta["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", resposta.content)
        self.assertIn(b"<rect", resposta.content)
        self.assertEqual(self.client.get(reverse("estoque:codigo_barras",args=[999999])).status_code,404)

    def test_exibicao_e_etiqueta(self):
        self.client.force_login(self.user)
        for rota in ["detalhe", "editar", "etiqueta"]:
            resposta = self.client.get(reverse("estoque:"+rota,args=[self.peca.pk]))
            self.assertContains(resposta, reverse("estoque:codigo_barras",args=[self.peca.pk]))
        resposta = self.client.get(reverse("estoque:etiqueta",args=[self.peca.pk]))
        self.assertNotContains(resposta, "R$")
        self.assertNotContains(resposta, 'data-etiqueta="57x29"')
        self.assertContains(resposta,"Imprimir etiqueta")
        admin = site._registry[Peca]
        self.assertIn("Disponível após salvar",admin.codigo_barras(None))
        self.assertIn("codigo-barras.svg",admin.codigo_barras(self.peca))

    def test_code128_rejeita_unicode_nao_representavel(self):
        with self.assertRaises(ValueError):
            gerar_svg("PEÇA")
        self.assertIn("<svg", gerar_svg("PC-000123"))
