import base64
import hashlib
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client as TestClient, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.auditoria import Evento
from estoque.models import Categoria, Peca
from vendas.models import Venda
from .api import Cliente, ErroIntegracao, SemRedirect
from .models import Anuncio, Conexao, Selecao, TentativaOAuth
from .seguranca import cifrar, decifrar, validar_configuracao
from .servicos import conectar, importar_lote, token_atual


CONFIG = dict(MERCADOLIVRE_ENABLED=True, MERCADOLIVRE_CLIENT_ID="12345",
    MERCADOLIVRE_CLIENT_SECRET="segredo-de-teste", MERCADOLIVRE_SELLER_ID="9876",
    MERCADOLIVRE_INSTALLATION_ID="loja-teste", MERCADOLIVRE_TOKEN_KEY=Fernet.generate_key().decode(),
    MERCADOLIVRE_REDIRECT_URI="https://testserver/mercado-livre/oauth/callback/", ALLOWED_HOSTS=["testserver"])


def credenciais(**extras):
    return {"user_id": 9876, "access_token": "access-secreto", "refresh_token": "refresh-secreto",
            "expires_in": 21600, "scope": "read offline_access", **extras}


def item(**extras):
    return {"id": "MLB123", "seller_id": 9876, "title": "Farol Gol", "status": "active",
            "price": 199.90, "currency_id": "BRL", "available_quantity": 9, "sold_quantity": 3,
            "seller_custom_field": "SKU-001", "variations": [], **extras}


@override_settings(**CONFIG)
class IntegracaoTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("admin_ml")
        self.comum = get_user_model().objects.create_user("consulta_ml")
        self.client.force_login(self.admin)
        self.categoria = Categoria.objects.create(nome="Categoria ML")
        self.peca = Peca.objects.create(nome="Farol", categoria=self.categoria, preco_venda=100, quantidade=2)

    def conexao(self, **extras):
        return Conexao.objects.create(instalacao="loja-teste", cliente_id="12345", vendedor_id="9876",
            conectada=True, access_token_cifrado=cifrar("access-secreto"), refresh_token_cifrado=cifrar("refresh-secreto"),
            expira_em=timezone.now() + timedelta(hours=1), **extras)

    def anuncio(self, conexao=None):
        return Anuncio.objects.create(conexao=conexao or self.conexao(), item_id="MLB123", titulo="Farol ML",
            status="active", preco=200, moeda="BRL", quantidade=4)

    def iniciar_oauth(self):
        resposta = self.client.post(reverse("mercadolivre:autorizar"))
        self.assertEqual(resposta.status_code, 302)
        return parse_qs(urlsplit(resposta.url).query)

    def test_oauth_pkce_scope_state_e_post(self):
        self.assertEqual(self.client.get(reverse("mercadolivre:autorizar")).status_code, 405)
        parametros = self.iniciar_oauth()
        self.assertEqual(parametros["scope"], ["read offline_access"])
        self.assertEqual(parametros["code_challenge_method"], ["S256"])
        verifier = self.client.session["ml_oauth"]["verifier"]
        esperado = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(parametros["code_challenge"], [esperado])
        self.assertNotIn("segredo-de-teste", str(parametros))

    @patch("mercadolivre.servicos.Cliente")
    def test_callback_salva_tokens_cifrados_sem_publicar(self, api):
        api.return_value.token.return_value = credenciais()
        api.return_value.consultar.return_value = {"id": 9876, "nickname": "PontoCar"}
        parametros = self.iniciar_oauth()
        resposta = self.client.get(reverse("mercadolivre:callback"), {"state": parametros["state"][0], "code": "codigo-secreto"})
        self.assertRedirects(resposta, reverse("mercadolivre:painel"))
        conexao = Conexao.objects.get()
        self.assertTrue(conexao.conectada)
        self.assertNotIn("access-secreto", conexao.access_token_cifrado)
        self.assertEqual(decifrar(conexao.refresh_token_cifrado), "refresh-secreto")
        self.assertEqual(api.return_value.consultar.call_args.args[0], "/users/me")
        self.assertFalse(Anuncio.objects.exists())
        self.assertFalse(Selecao.objects.exists())
        self.assertNotIn("codigo-secreto", str(list(Evento.objects.values())))

    @patch("mercadolivre.views.conectar")
    def test_callback_rejeita_state_invalido_e_outra_sessao(self, conectar_mock):
        parametros = self.iniciar_oauth()
        url = reverse("mercadolivre:callback")
        self.assertEqual(self.client.get(url, {"state": "invalido", "code": "code"}).status_code, 400)
        outro = TestClient()
        outro.force_login(self.admin)
        self.assertEqual(outro.get(url, {"state": parametros["state"][0], "code": "code"}).status_code, 400)
        self.iniciar_oauth()
        self.assertEqual(self.client.get(url, {"state": "estado inválido", "code": "code"}).status_code, 400)
        conectar_mock.assert_not_called()

    @patch("mercadolivre.views.conectar")
    def test_callback_expiracao_e_troca_configuracao(self, conectar_mock):
        parametros = self.iniciar_oauth()
        TentativaOAuth.objects.update(expira_em=timezone.now() - timedelta(seconds=1))
        url = reverse("mercadolivre:callback")
        self.assertEqual(self.client.get(url, {"state": parametros["state"][0], "code": "code"}).status_code, 400)
        parametros = self.iniciar_oauth()
        with override_settings(MERCADOLIVRE_INSTALLATION_ID="outra-loja"):
            self.assertEqual(self.client.get(url, {"state": parametros["state"][0], "code": "code"}).status_code, 400)
        conectar_mock.assert_not_called()

    @patch("mercadolivre.views.conectar")
    def test_callback_erro_consumido_nao_pode_repetir(self, conectar_mock):
        parametros = self.iniciar_oauth()
        sessao_antiga = dict(self.client.session["ml_oauth"])
        url = reverse("mercadolivre:callback")
        dados = {"state": parametros["state"][0], "error": "access_denied"}
        self.assertEqual(self.client.get(url, dados).status_code, 302)
        sessao = self.client.session
        sessao["ml_oauth"] = sessao_antiga
        sessao.save()
        self.assertEqual(self.client.get(url, dados).status_code, 400)
        conectar_mock.assert_not_called()

    @patch("mercadolivre.servicos.Cliente")
    def test_conectar_rejeita_outra_conta_e_scope_write(self, api):
        for dados in (credenciais(user_id=555), credenciais(scope="read write offline_access"), credenciais(refresh_token="")):
            api.return_value.token.return_value = dados
            with self.assertRaises(ErroIntegracao):
                conectar("code", "verifier")
        self.assertFalse(Conexao.objects.exists())
        api.return_value.consultar.assert_not_called()

    @patch("mercadolivre.servicos.Cliente")
    def test_perfil_de_outro_vendedor_rejeitado(self, api):
        api.return_value.token.return_value = credenciais()
        api.return_value.consultar.return_value = {"id": 555}
        with self.assertRaises(ErroIntegracao):
            conectar("code", "verifier")
        self.assertFalse(Conexao.objects.exists())

    @patch("mercadolivre.servicos.Cliente")
    def test_renovacao_persiste_novo_refresh_mesmo_se_importacao_falha(self, api):
        conexao = self.conexao()
        conexao.expira_em = timezone.now() - timedelta(seconds=1)
        conexao.save()
        api.return_value.token.return_value = credenciais(access_token="novo-access", refresh_token="novo-refresh")
        api.return_value.consultar.side_effect = ErroIntegracao("Indisponível")
        with self.assertRaises(ErroIntegracao):
            importar_lote()
        conexao.refresh_from_db()
        self.assertEqual(decifrar(conexao.refresh_token_cifrado), "novo-refresh")
        self.assertEqual(api.return_value.token.call_args.args[0]["grant_type"], "refresh_token")
        self.assertEqual(token_atual()[2], "novo-access")
        self.assertEqual(api.return_value.token.call_count, 1)

    @patch("mercadolivre.servicos.Cliente")
    def test_importacao_idempotente_preserva_vinculo_estoque_preco_vendas(self, api):
        anuncio = self.anuncio()
        anuncio.peca = self.peca
        anuncio.save()
        vendas_antes = Venda.objects.count()
        api.return_value.consultar.side_effect = [
            {"results": ["MLB123"], "scroll_id": "cursor"}, [{"status_code": 200, "body": item()}],
            {"results": ["MLB123"], "scroll_id": "cursor2"}, [{"status_code": 200, "body": item(price=210)}]]
        self.assertEqual(importar_lote(), (1, False))
        self.assertEqual(importar_lote(reiniciar=True), (1, False))
        anuncio.refresh_from_db()
        self.peca.refresh_from_db()
        self.assertEqual(Anuncio.objects.count(), 1)
        self.assertEqual(anuncio.peca_id, self.peca.pk)
        self.assertEqual(anuncio.preco, Decimal("210"))
        self.assertEqual(self.peca.quantidade, 2)
        self.assertEqual(self.peca.preco_venda, Decimal("100"))
        self.assertFalse(self.peca.postada_online)
        self.assertEqual(Venda.objects.count(), vendas_antes)
        self.assertFalse(Selecao.objects.exists())
        self.assertEqual(api.return_value.consultar.call_args_list[1].args[0], "/items/bulk")

    @patch("mercadolivre.servicos.Cliente")
    def test_scan_continua_ate_vazio_sem_duplicar(self, api):
        conexao = self.conexao()
        api.return_value.consultar.side_effect = [{"results": ["MLB123"], "scroll_id": "cursor"},
            [{"status_code": 200, "body": item()}], {"results": []}]
        importar_lote()
        self.assertEqual(importar_lote(), (0, True))
        self.assertEqual(api.return_value.consultar.call_args.kwargs["scroll_id"], "cursor")
        self.assertEqual(importar_lote(), (0, True))
        self.assertEqual(api.return_value.consultar.call_count, 3)
        conexao.refresh_from_db()
        self.assertTrue(conexao.importacao_concluida)

    @patch("mercadolivre.servicos.Cliente")
    def test_cursor_expirado_exige_reinicio(self, api):
        self.conexao(cursor="antigo", cursor_expira_em=timezone.now() - timedelta(seconds=1))
        with self.assertRaisesMessage(ErroIntegracao, "expirou"):
            importar_lote()
        api.return_value.consultar.assert_not_called()
        api.return_value.consultar.return_value = {"results": []}
        self.assertEqual(importar_lote(reiniciar=True), (0, True))
        self.assertNotIn("scroll_id", api.return_value.consultar.call_args.kwargs)

    @patch("mercadolivre.servicos.Cliente")
    def test_lote_incompleto_ou_outra_conta_nao_persiste(self, api):
        self.conexao()
        for resultado in ([], [{"status_code": 403}], [{"status_code": 200, "body": item(seller_id=111)}],
                          [{"status_code": 200, "body": item(price="NaN")}],
                          [{"status_code": 200, "body": item(id="MLB999")} ]):
            api.return_value.consultar.side_effect = [{"results": ["MLB123"], "scroll_id": "c"}, resultado]
            with self.assertRaises(ErroIntegracao):
                importar_lote()
            self.assertFalse(Anuncio.objects.exists())
            self.assertEqual(Conexao.objects.get().cursor, "")

    @patch("mercadolivre.servicos.Cliente")
    def test_lojas_isoladas_configuracao_e_chave(self, api):
        self.conexao()
        for config in ({"MERCADOLIVRE_SELLER_ID": "222"}, {"MERCADOLIVRE_INSTALLATION_ID": "loja2"},
                       {"MERCADOLIVRE_CLIENT_ID": "333"}, {"MERCADOLIVRE_TOKEN_KEY": Fernet.generate_key().decode()},
                       {"MERCADOLIVRE_ENABLED": False}):
            with override_settings(**config), self.assertRaises(ErroIntegracao):
                importar_lote()
        api.return_value.consultar.assert_not_called()

    def test_configuracao_insegura_rejeitada(self):
        for config in ({"MERCADOLIVRE_TOKEN_KEY": ""}, {"MERCADOLIVRE_REDIRECT_URI": "http://testserver/mercado-livre/oauth/callback/"},
                       {"MERCADOLIVRE_REDIRECT_URI": "https://outra-loja/mercado-livre/oauth/callback/"},
                       {"MERCADOLIVRE_CLIENT_SECRET": ""}):
            with override_settings(**config), self.assertRaises(ErroIntegracao):
                validar_configuracao()

    def test_vincular_desvincular_e_codigo_invalido(self):
        anuncio = self.anuncio()
        url = reverse("mercadolivre:vincular", args=[anuncio.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.post(url, {"codigo": "INEXISTENTE"}), "Nenhuma peça")
        self.assertEqual(self.client.post(url, {"codigo": self.peca.codigo}).status_code, 302)
        anuncio.refresh_from_db()
        self.assertEqual(anuncio.peca_id, self.peca.pk)
        self.assertFalse(Selecao.objects.exists())
        self.assertEqual(self.client.post(reverse("mercadolivre:desvincular", args=[anuncio.pk])).status_code, 302)
        anuncio.refresh_from_db()
        self.assertIsNone(anuncio.peca_id)

    @patch("mercadolivre.api.Cliente._enviar")
    def test_selecao_explicita_individual_reversivel_sem_api(self, enviar):
        url = reverse("mercadolivre:selecionar", args=[self.peca.pk])
        self.assertContains(self.client.get(url), "publicação indisponível")
        self.assertFalse(Selecao.objects.exists())
        self.assertEqual(self.client.post(url, {"acao": "todas"}).status_code, 400)
        self.client.post(url, {"acao": "selecionar"})
        self.client.post(url, {"acao": "selecionar"})
        self.assertEqual(list(Selecao.objects.values_list("peca_id", flat=True)), [self.peca.pk])
        self.client.post(url, {"acao": "remover"})
        self.assertFalse(Selecao.objects.exists())
        enviar.assert_not_called()

    def test_desconectar_apaga_tokens_preserva_historico(self):
        anuncio = self.anuncio()
        anuncio.peca = self.peca
        anuncio.save()
        self.iniciar_oauth()
        self.client.post(reverse("mercadolivre:desconectar"))
        conexao = Conexao.objects.get()
        self.assertFalse(conexao.conectada)
        self.assertEqual(conexao.access_token_cifrado, "")
        self.assertEqual(conexao.refresh_token_cifrado, "")
        self.assertFalse(TentativaOAuth.objects.exists())
        anuncio.refresh_from_db()
        self.assertEqual(anuncio.peca_id, self.peca.pk)

    def test_permissoes_get_seguro_e_csrf(self):
        anuncio = self.anuncio()
        self.client.force_login(self.comum)
        for nome in ("painel", "autorizar", "importar", "desconectar"):
            self.assertEqual(self.client.post(reverse("mercadolivre:" + nome)).status_code, 403)
        self.comum.user_permissions.add(Permission.objects.get(codename="gerenciar_integracao"))
        self.assertEqual(self.client.get(reverse("mercadolivre:painel")).status_code, 200)
        self.assertEqual(self.client.post(reverse("mercadolivre:vincular", args=[anuncio.pk]), {"codigo": self.peca.codigo}).status_code, 403)
        self.assertEqual(self.client.post(reverse("mercadolivre:selecionar", args=[self.peca.pk]), {"acao": "selecionar"}).status_code, 403)
        self.client.force_login(self.admin)
        for nome in ("importar", "desconectar", "autorizar"):
            self.assertEqual(self.client.get(reverse("mercadolivre:" + nome)).status_code, 405)
        csrf_client = TestClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(reverse("mercadolivre:autorizar")).status_code, 403)

    def test_painel_escapa_conteudo_nao_exibe_tokens_e_sem_cache(self):
        anuncio = self.anuncio()
        anuncio.titulo = '<script>alert("x")</script>'
        anuncio.save()
        resposta = self.client.get(reverse("mercadolivre:painel"))
        self.assertContains(resposta, "&lt;script&gt;")
        self.assertNotContains(resposta, "access-secreto")
        self.assertNotContains(resposta, "refresh-secreto")
        self.assertIn("no-store", resposta["Cache-Control"])
        self.assertEqual(resposta["Referrer-Policy"], "same-origin")

    @patch("mercadolivre.views.importar_lote", return_value=(0, True))
    def test_formulario_https_preserva_referencia_e_csrf(self, importar_mock):
        cliente = TestClient(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        painel = reverse("mercadolivre:painel")
        resposta = cliente.get(painel, secure=True)
        self.assertEqual(resposta["Referrer-Policy"], "same-origin")
        token = cliente.cookies["csrftoken"].value
        dados = {"csrfmiddlewaretoken": token}
        url = reverse("mercadolivre:importar")
        # Sem Origin/Referer, o Django deve continuar recusando o POST HTTPS.
        self.assertEqual(cliente.post(url, dados, secure=True).status_code, 403)
        importar_mock.assert_not_called()
        resposta = cliente.post(url, dados, secure=True, HTTP_REFERER="https://testserver" + painel)
        self.assertEqual(resposta.status_code, 302)
        importar_mock.assert_called_once()
        parametros = self.iniciar_oauth()
        resposta = self.client.get(reverse("mercadolivre:callback"), {"state": parametros["state"][0], "error": "access_denied"})
        self.assertEqual(resposta["Referrer-Policy"], "no-referrer")

    def test_funcionalidade_oculta_quando_desabilitada(self):
        url = reverse("estoque:detalhe", args=[self.peca.pk])
        self.assertContains(self.client.get(url), "Anunciar no Mercado Livre")
        with override_settings(MERCADOLIVRE_ENABLED=False):
            self.assertNotContains(self.client.get(url), "Anunciar no Mercado Livre")
            self.assertEqual(self.client.get(reverse("mercadolivre:painel")).status_code, 403)


class TransporteTests(TestCase):
    @patch("mercadolivre.api.build_opener")
    def test_bloqueia_escrita_caminhos_arbitrarios_e_url_externa(self, opener):
        for metodo, caminho in [("POST", "/items"), ("PUT", "/items/MLB123"), ("DELETE", "/items/MLB123"),
                                ("GET", "https://outro.test/users/me"), ("GET", "/orders/search"),
                                ("GET", "/users/me?access_token=segredo")]:
            with self.assertRaises(ErroIntegracao):
                Cliente()._enviar(metodo, caminho)
        opener.assert_not_called()

    @patch("mercadolivre.api.build_opener")
    def test_token_so_no_header_post_form_timeout_sem_redirect(self, opener):
        opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'{}'
        Cliente().consultar("/users/me", "segredo")
        req = opener.return_value.open.call_args.args[0]
        self.assertNotIn("segredo", req.full_url)
        self.assertEqual(req.get_header("Authorization"), "Bearer segredo")
        self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 15)
        Cliente().token({"client_secret": "secret", "grant_type": "authorization_code"})
        req = opener.return_value.open.call_args.args[0]
        self.assertEqual(req.method, "POST")
        self.assertIn(b"client_secret=secret", req.data)
        self.assertIsNone(SemRedirect().redirect_request(None, None, 302, "", {}, "https://outro.test"))

    @patch("mercadolivre.api.build_opener")
    def test_erros_sanitizados(self, opener):
        for erro in (HTTPError("https://api", 401, "access-secreto", {}, None),
                     HTTPError("https://api", 429, "access-secreto", {}, None), URLError("access-secreto")):
            opener.return_value.open.side_effect = erro
            with self.assertRaises(ErroIntegracao) as capturado:
                Cliente().consultar("/users/me", "access-secreto")
            self.assertNotIn("access-secreto", str(capturado.exception))
