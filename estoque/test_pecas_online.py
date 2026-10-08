from io import BytesIO
from base64 import urlsafe_b64decode
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
import re
import base64
import zlib
from .models import Peca, Categoria
from .forms import PecaAdminForm


class PecasOnlineTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nome="Online teste")
        self.peca = Peca.objects.create(nome="Farol", categoria=self.categoria,
            preco_venda=100, quantidade=2)
        self.client.force_login(get_user_model().objects.create_superuser("online_teste"))

    def test_campos_no_cadastro_e_edicao_sem_mudar_saldo(self):
        form = PecaAdminForm()
        self.assertIn("postada_online", form.fields)
        self.assertIn("compativel", form.fields)
        url = reverse("estoque:editar", args=[self.peca.pk])
        self.assertContains(self.client.get(url), 'name="compativel"')
        response = self.client.post(url, {"nome": "Farol", "categoria": self.categoria.pk,
            "preco_venda": "100", "custo": "0", "quantidade": "2",
            "status": "disponivel", "condicao": "usada", "compativel": "Gol 2012\nVoyage 2013",
            "postada_online": "on", "versao_estoque": self.peca.atualizado_em.isoformat()})
        self.assertEqual(response.status_code, 302)
        self.peca.refresh_from_db()
        self.assertTrue(self.peca.postada_online)
        self.assertEqual(self.peca.compativel, "Gol 2012\nVoyage 2013")
        self.assertEqual(self.peca.quantidade, 2)
        self.assertContains(self.client.get(reverse("estoque:lista")), "Publicada online")
        self.assertContains(self.client.get(reverse("estoque:detalhe", args=[self.peca.pk])), "Voyage 2013")

    def test_modelos_diretos_uma_etiqueta_com_aviso_apenas_online(self):
        url = reverse("estoque:etiqueta", args=[self.peca.pk])
        for modelo in ("padrao", "online"):
            response = self.client.get(url, {"modelo": modelo})
            payload = response.context["etiqueta_direta"]
            pdf = urlsafe_b64decode(payload + '=' * (-len(payload) % 4))
            self.assertIn(b"/Count 1", pdf)
            dimensions = re.search(rb"/MediaBox \[ 0 0 ([\d.]+) ([\d.]+) \]", pdf)
            self.assertIsNotNone(dimensions)
            self.assertAlmostEqual(float(dimensions[1]), 57 * 72 / 25.4, places=3)
            self.assertAlmostEqual(float(dimensions[2]), 30 * 72 / 25.4, places=3)
            stream = re.search(rb"stream\r?\n(.*?)endstream", pdf, re.S)[1].strip()
            commands = zlib.decompress(base64.a85decode(stream, adobe=True))
            self.assertEqual(b"VENDAS ONLINE" in commands, modelo == "online")
            self.assertEqual(self.client.get(url, {"modelo": modelo, "formato": "pdf"}).status_code, 200)
        self.assertFalse(self.peca.postada_online)
        self.assertEqual(self.client.get(url, {"modelo": "desconhecido"}).status_code, 400)

    def test_compatibilidade_pesquisavel_e_defaults_seguros(self):
        self.assertFalse(self.peca.postada_online)
        self.assertEqual(self.peca.compativel, "")
        self.peca.compativel = "Voyage especial"
        self.peca.save()
        self.assertContains(self.client.get(reverse("estoque:lista"), {"q": "Voyage especial"}), self.peca.codigo)
