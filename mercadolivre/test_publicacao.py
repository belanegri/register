from datetime import timedelta
from unittest.mock import patch
from io import BytesIO
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from estoque.models import Categoria, Peca, FotoPeca
from .api import ErroIntegracao, Cliente
from .forms import PublicacaoForm
from .models import Anuncio, Conexao, Publicacao
from .publicacao import assinatura, confirmar, preparar
from .publicacao_api import ClientePublicacao, Rejeitada
from .seguranca import cifrar
from .tests import CONFIG, item


@override_settings(**{**CONFIG, "MERCADOLIVRE_PUBLISH_ENABLED": True})
class PublicacaoTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("publicador")
        self.client.force_login(self.admin)
        self.peca = Peca.objects.create(nome="Farol Gol", categoria=Categoria.objects.create(nome="Faróis"), preco_venda=100, quantidade=2)
        self.outra = Peca.objects.create(nome="Lanterna", categoria=self.peca.categoria, preco_venda=50, quantidade=3)
        self.foto = FotoPeca.objects.create(peca=self.peca, imagem="teste/farol.webp")
        self.conexao = Conexao.objects.create(instalacao="loja-teste", cliente_id="12345", vendedor_id="9876",
            conectada=True, access_token_cifrado=cifrar("access-secreto"), refresh_token_cifrado=cifrar("refresh-secreto"),
            expira_em=timezone.now() + timedelta(hours=1))
        self.dados = {"titulo": "Farol Gol", "preco": "120.50", "quantidade": "1", "condicao": "used",
            "tipo": "gold_special", "envio": "me2", "descricao": "Farol usado e testado.", "fotos": [self.foto.pk], "attr_BRAND": "Original"}
        self.categoria = {"id": "MLB123", "name": "Faróis", "settings": {"listing_allowed": True, "max_pictures_per_item": 12, "max_title_length": 60}}
        self.attrs = [{"id": "BRAND", "name": "Marca", "value_type": "string", "tags": {"required": True}}]
        self.tipos = [{"id": "gold_special", "name": "Clássico"}]

    def form(self, **updates):
        return PublicacaoForm({**self.dados, **updates}, peca=self.peca, categoria=self.categoria, atributos=self.attrs, tipos=self.tipos)

    def rascunho(self, **extras):
        return Publicacao.objects.create(peca=self.peca, conexao=self.conexao, usuario=self.admin,
            payload={"title": "Farol", "category_id": "MLB123", "available_quantity": 1, "price": 120.5},
            descricao="Farol usado.", fotos=[self.foto.pk], assinatura=assinatura(self.peca), **extras)

    def test_form_limita_estoque_fotos_da_peca_e_atributos(self):
        self.assertTrue(self.form().is_valid())
        for updates, campo in [({"quantidade": "3"}, "quantidade"), ({"attr_BRAND": ""}, "attr_BRAND"),
                               ({"titulo": "a" * 61}, "titulo"), ({"preco": "-1"}, "preco")]:
            form = self.form(**updates)
            self.assertFalse(form.is_valid())
            self.assertIn(campo, form.errors)
        outra_foto = FotoPeca.objects.create(peca=self.outra, imagem="teste/outra.webp")
        self.assertFalse(self.form(fotos=[outra_foto.pk]).is_valid())

    @patch("mercadolivre.publicacao.fotos_payload", return_value=[{"source": "https://storage.test/foto"}])
    @patch("mercadolivre.publicacao.ClientePublicacao")
    def test_preparar_so_valida_e_nao_publica(self, cls, fotos):
        cls.return_value.enviar.side_effect = [{"id": 9876, "tags": []}, {}]
        form = self.form()
        self.assertTrue(form.is_valid())
        pub = preparar(self.admin, self.peca, form)
        self.assertEqual(pub.estado, "revisao")
        self.assertEqual(pub.payload["available_quantity"], 1)
        self.assertNotIn("pictures", pub.payload)
        self.assertNotIn("storage.test", str(pub.payload))
        self.assertEqual([c.args[1] for c in cls.return_value.enviar.call_args_list], ["/users/me", "/items/validate"])
        self.assertFalse(Anuncio.objects.exists())

    @patch("mercadolivre.publicacao.fotos_payload", return_value=[{"source": "https://storage.test/foto"}])
    @patch("mercadolivre.publicacao.ClientePublicacao")
    def test_user_products_envia_family_name(self, cls, fotos):
        cls.return_value.enviar.side_effect = [{"id": 9876, "tags": ["user_product_seller"]}, {}]
        form = self.form()
        self.assertTrue(form.is_valid())
        pub = preparar(self.admin, self.peca, form)
        self.assertIn("family_name", pub.payload)
        self.assertNotIn("title", pub.payload)

    @patch("mercadolivre.publicacao.fotos_payload", return_value=[{"source": "https://storage.test/foto"}])
    @patch("mercadolivre.publicacao.ClientePublicacao")
    def test_confirmar_apenas_peca_revisada_e_bloqueia_reenvio(self, cls, fotos):
        pub = self.rascunho()
        cls.return_value.enviar.side_effect = [{}, item(available_quantity=1, price=120.5), {}]
        resultado = confirmar(self.admin, pub.pk)
        self.assertEqual(resultado.estado, "publicada")
        self.assertEqual(Anuncio.objects.get().peca_id, self.peca.pk)
        self.assertEqual([c.args[1] for c in cls.return_value.enviar.call_args_list], ["/items/validate", "/items", "/items/MLB123/description"])
        self.peca.refresh_from_db()
        self.outra.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 2)
        self.assertEqual(self.peca.preco_venda, 100)
        self.assertEqual(self.outra.quantidade, 3)
        with self.assertRaises(ErroIntegracao):
            confirmar(self.admin, pub.pk)
        self.assertEqual(cls.return_value.enviar.call_count, 3)

    @patch("mercadolivre.publicacao.fotos_payload", return_value=[{"source": "https://storage.test/foto"}])
    @patch("mercadolivre.publicacao.ClientePublicacao")
    def test_timeout_apos_envio_bloqueia_nova_tentativa(self, cls, fotos):
        pub = self.rascunho()
        cls.return_value.enviar.side_effect = [{}, ErroIntegracao("Tempo esgotado")]
        with self.assertRaises(ErroIntegracao):
            confirmar(self.admin, pub.pk)
        pub.refresh_from_db()
        self.assertEqual(pub.estado, "incerta")
        with self.assertRaises(ErroIntegracao):
            confirmar(self.admin, pub.pk)
        self.assertEqual(cls.return_value.enviar.call_count, 2)

    @patch("mercadolivre.publicacao.fotos_payload", return_value=[{"source": "https://storage.test/foto"}])
    @patch("mercadolivre.publicacao.ClientePublicacao")
    def test_descricao_falha_preserva_id_e_nao_repete_publicacao(self, cls, fotos):
        pub = self.rascunho()
        cls.return_value.enviar.side_effect = [{}, item(), ErroIntegracao("Falha")]
        resultado = confirmar(self.admin, pub.pk)
        self.assertEqual(resultado.item_id, "MLB123")
        self.assertEqual(resultado.estado, "publicada")
        self.assertIn("descrição", resultado.aviso)

    @patch("mercadolivre.publicacao.ClientePublicacao")
    def test_peca_alterada_ou_revisao_expirada_nao_envia(self, cls):
        pub = self.rascunho()
        self.peca.quantidade = 1
        self.peca.save()
        with self.assertRaises(ErroIntegracao):
            confirmar(self.admin, pub.pk)
        cls.return_value.enviar.assert_not_called()
        Publicacao.objects.filter(pk=pub.pk).update(assinatura=assinatura(self.peca), criado_em=timezone.now() - timedelta(minutes=16))
        with self.assertRaises(ErroIntegracao):
            confirmar(self.admin, pub.pk)
        cls.return_value.enviar.assert_not_called()

    @patch("mercadolivre.publicacao.ClientePublicacao")
    def test_outra_conta_usuario_sem_permissao_e_loja_desligada(self, cls):
        pub = self.rascunho()
        with override_settings(MERCADOLIVRE_PUBLISH_ENABLED=False):
            with self.assertRaises(ErroIntegracao):
                confirmar(self.admin, pub.pk)
        comum = get_user_model().objects.create_user("comum")
        with self.assertRaises(ErroIntegracao):
            confirmar(comum, pub.pk)
        with override_settings(MERCADOLIVRE_SELLER_ID="111"):
            with self.assertRaises(ErroIntegracao):
                confirmar(self.admin, pub.pk)
        cls.return_value.enviar.assert_not_called()

    @patch("mercadolivre.publicacao.confirmar")
    def test_get_e_post_sem_confirmacao_nao_publicam(self, confirmar_mock):
        pub = self.rascunho()
        url = reverse("mercadolivre:revisar_publicacao", args=[pub.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 400)
        confirmar_mock.assert_not_called()
        self.assertEqual(self.client.post(url, {"confirmacao": str(pub.pk)}).status_code, 302)
        confirmar_mock.assert_called_once_with(self.admin, pub.pk)

    @patch("mercadolivre.publicacao_api.build_opener")
    def test_transporte_nao_altera_anuncios_existentes_ou_outros_endpoints(self, opener):
        for metodo, caminho in [("PUT", "/items/MLB123"), ("DELETE", "/items/MLB123"), ("POST", "/orders"),
                                ("POST", "/items/MLB123"), ("POST", "/items/MLA123/description")]:
            with self.assertRaises(ErroIntegracao):
                ClientePublicacao().enviar(metodo, caminho, "token")
        with override_settings(MERCADOLIVRE_PUBLISH_ENABLED=False):
            with self.assertRaises(ErroIntegracao):
                ClientePublicacao().enviar("POST", "/items", "token", {})
        with self.assertRaises(ErroIntegracao):
            Cliente()._enviar("POST", "/items", token="token")
        opener.assert_not_called()

    @patch("mercadolivre.publicacao.fotos_payload", return_value=[{"source": "https://storage.test/foto"}])
    @patch("mercadolivre.publicacao.ClientePublicacao")
    def test_segundo_envio_durante_post_e_bloqueado(self, cls, fotos):
        pub = self.rascunho()
        def resposta(metodo, caminho, *args, **kwargs):
            if caminho == "/items":
                self.assertEqual(Publicacao.objects.get(pk=pub.pk).estado, "enviando")
                with self.assertRaises(ErroIntegracao):
                    confirmar(self.admin, pub.pk)
                return item()
            return {}
        cls.return_value.enviar.side_effect = resposta
        self.assertEqual(confirmar(self.admin, pub.pk).estado, "publicada")
        self.assertEqual(sum(c.args[1] == "/items" for c in cls.return_value.enviar.call_args_list), 1)

    @patch("mercadolivre.publicacao.fotos_payload", return_value=[{"source": "https://storage.test/foto"}])
    @patch("mercadolivre.publicacao.ClientePublicacao")
    def test_rejeicao_definitiva_e_vendedor_incorreto(self, cls, fotos):
        pub = self.rascunho()
        cls.return_value.enviar.side_effect = [{}, Rejeitada("Dados inválidos")]
        with self.assertRaises(Rejeitada):
            confirmar(self.admin, pub.pk)
        pub.refresh_from_db()
        self.assertEqual(pub.estado, "rejeitada")
        pub.estado = "revisao"
        pub.save()
        cls.return_value.enviar.side_effect = [{}, item(seller_id=111)]
        with self.assertRaises(ErroIntegracao):
            confirmar(self.admin, pub.pk)
        pub.refresh_from_db()
        self.assertEqual(pub.estado, "incerta")
        self.assertFalse(Anuncio.objects.exists())

    def test_csrf_e_revisao_de_outro_usuario(self):
        from django.test import Client
        pub = self.rascunho()
        url = reverse("mercadolivre:revisar_publicacao", args=[pub.pk])
        seguro = Client(enforce_csrf_checks=True)
        seguro.force_login(self.admin)
        self.assertEqual(seguro.post(url, {"confirmacao": str(pub.pk)}).status_code, 403)
        outro = get_user_model().objects.create_superuser("outro_admin")
        self.client.force_login(outro)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"confirmacao": str(pub.pk)}).status_code, 404)

    @patch("mercadolivre.publicacao.metadados")
    @patch("mercadolivre.publicacao.fotos_payload", return_value=[{"source": "https://storage.test/foto"}])
    @patch("mercadolivre.publicacao.ClientePublicacao")
    def test_fluxo_formulario_revisao_e_painel(self, cls, fotos, metadados_mock):
        metadados_mock.return_value = (self.categoria, self.attrs, self.tipos)
        url = reverse("mercadolivre:preparar_publicacao", args=[self.peca.pk]) + "?categoria=MLB123"
        self.assertContains(self.client.get(url), "Validar e revisar")
        cls.return_value.enviar.assert_not_called()
        cls.return_value.enviar.side_effect = [{"id": 9876}, {}]
        resposta = self.client.post(url, self.dados)
        pub = Publicacao.objects.get()
        self.assertRedirects(resposta, reverse("mercadolivre:revisar_publicacao", args=[pub.pk]))
        self.assertEqual(pub.resumo["atributos"], [{"nome": "Marca", "valor": "Original"}])
        painel = self.client.get(reverse("mercadolivre:painel"))
        self.assertContains(painel, "Minhas publicações recentes")
        self.assertContains(painel, "<title>Mercado Livre · REGISTER</title>", html=True)
        html = painel.content.decode()
        self.assertLess(html.index('<h2>Peças selecionadas manualmente</h2>'), html.index('<h2>Anúncios importados</h2>'))
        self.assertLess(html.index('<h2>Minhas publicações recentes</h2>'), html.index('<h2>Anúncios importados</h2>'))
        self.assertEqual([c.args[1] for c in cls.return_value.enviar.call_args_list], ["/users/me", "/items/validate"])

    def test_fotos_com_miniatura_preservam_ids_e_selecao(self):
        form = self.form()
        html = str(form["fotos"])
        self.assertIn('name="fotos"', html)
        self.assertIn(f'value="{self.foto.pk}"', html)
        self.assertIn('checked', html)
        self.assertIn('editor-photo-option', html)
        self.assertIn('<img ', html)
        self.assertTrue(form.is_valid())
        self.assertEqual(list(form.cleaned_data["fotos"]), [self.foto])

    @patch("mercadolivre.publicacao_api.build_opener")
    def test_erros_http_sanitizados_e_falhas_ambiguas(self, opener):
        opener.return_value.open.side_effect = HTTPError("https://api.mercadolibre.com/items", 400, "erro", {},
            BytesIO(b'{"message":"segredo-token", "cause":[{"code":"item.attributes.missing_required"},{"code":"segredo/token"}]}'))
        with self.assertRaises(Rejeitada) as contexto:
            ClientePublicacao().enviar("POST", "/items", "token-secreto", {})
        self.assertIn("item.attributes.missing_required", str(contexto.exception))
        self.assertNotIn("segredo", str(contexto.exception))
        for erro in [HTTPError("url", 500, "segredo", {}, BytesIO(b'')), URLError("token-secreto")]:
            opener.return_value.open.side_effect = erro
            with self.assertRaises(ErroIntegracao) as contexto:
                ClientePublicacao().enviar("POST", "/items", "token-secreto", {})
            self.assertNotIsInstance(contexto.exception, Rejeitada)
            self.assertNotIn("segredo", str(contexto.exception))
