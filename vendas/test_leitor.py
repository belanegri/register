from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from estoque.models import Peca, Categoria


class LeitorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("leitor_admin")
        cls.peca = Peca.objects.create(nome="Farol", categoria=Categoria.objects.first(), preco_venda=25, quantidade=2)

    def setUp(self):
        self.client.force_login(self.user)

    def scan(self, codigo):
        return self.client.post(reverse("vendas:carrinho"), {"acao":"codigo","codigo":codigo}, follow=True)

    def test_leitura_repetida_e_preco_negociado(self):
        self.scan(self.peca.codigo)
        self.client.post(reverse("vendas:carrinho"), {"acao":"preco","peca":self.peca.pk,"preco":"19.90"})
        self.scan(self.peca.codigo+"\r\n")
        item = self.client.session["carrinho"][str(self.peca.pk)]
        self.assertEqual(item["quantidade"],2)
        self.assertEqual(item["preco"],"19.90")
        self.assertTrue(item["preco_personalizado"])
        self.assertContains(self.scan(self.peca.codigo),"Saldo insuficiente")
        self.assertEqual(self.client.session["carrinho"][str(self.peca.pk)]["quantidade"],2)
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade,2)

    def test_inexistente_reservada_e_sem_saldo(self):
        self.assertContains(self.scan("NAO-EXISTE"),"Nenhuma peça encontrada")
        self.assertNotIn("carrinho", self.client.session)
        Peca.objects.filter(pk=self.peca.pk).update(status="reservada")
        self.assertContains(self.scan(self.peca.codigo),"Peça indisponível: Reservada")
        Peca.objects.filter(pk=self.peca.pk).update(status="vendida",quantidade=0)
        self.assertContains(self.scan(self.peca.codigo),"Peça sem estoque")
        self.assertNotIn("carrinho", self.client.session)

    def test_legado_e_pesquisa_manual(self):
        Peca.objects.filter(pk=self.peca.pk).update(codigo="PC-000999")
        self.scan("PC-000999")
        self.assertIn(str(self.peca.pk),self.client.session["carrinho"])
        resposta=self.client.get(reverse("vendas:pdv"),{"q":"Farol"})
        self.assertContains(resposta,'name="q"')
        self.assertContains(resposta,'id="codigo-leitor"')
        self.assertEqual(list(resposta.context["pecas"]),[self.peca])

    def test_permissao_e_csrf(self):
        user=get_user_model().objects.create_user("sem_pdv")
        self.client.force_login(user)
        self.assertEqual(self.scan(self.peca.codigo).status_code,403)
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("vendas:carrinho"),{"acao":"codigo","codigo":self.peca.codigo}).status_code,403)
