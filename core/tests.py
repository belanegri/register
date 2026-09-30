from io import BytesIO

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from .models import ConfiguracaoEmpresa


class ConfiguracaoEmpresaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser("admin_empresa", password="SenhaTeste987!")
        cls.usuario = get_user_model().objects.create_user("operador_empresa", password="SenhaTeste987!", is_staff=True)
        cls.autorizado = get_user_model().objects.create_user("autorizado_empresa")
        cls.autorizado.user_permissions.add(Permission.objects.get(codename="change_configuracaoempresa"))

    def setUp(self):
        self.url = reverse("core:configuracao_empresa")

    def test_login_e_acesso_sem_criacao_por_get(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        resposta = self.client.post(reverse("accounts:login"), {"username": "admin_empresa", "password": "SenhaTeste987!"})
        self.assertEqual(resposta.status_code, 302)
        self.assertContains(self.client.get(self.url), "Configurações da Empresa")
        self.assertEqual(ConfiguracaoEmpresa.objects.count(), 0)

    def test_staff_sem_permissao_nao_acessa_nem_grava(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"nome_fantasia": "Indevida"}).status_code, 403)
        self.assertNotContains(self.client.get(reverse("dashboard:index")), self.url)
        self.assertFalse(ConfiguracaoEmpresa.objects.exists())

    def test_autorizado_cria_edita_e_persiste_todos_campos(self):
        self.client.force_login(self.autorizado)
        dados = {"razao_social": "Empresa de teste Ltda", "nome_fantasia": "Loja de teste",
                 "documento": "12.345.678/0001-90", "inscricao_estadual": "Isento",
                 "telefone": "(11) 1234-5678", "whatsapp": "(11) 91234-5678",
                 "email": "teste@example.com", "cep": "01234-567", "endereco": "Rua Teste",
                 "numero": "s/n", "complemento": "Sala 1", "bairro": "Centro",
                 "cidade": "São Paulo", "estado": "SP"}
        self.assertRedirects(self.client.post(self.url, dados), self.url)
        config = ConfiguracaoEmpresa.objects.get()
        for campo, valor in dados.items():
            self.assertEqual(getattr(config, campo), valor)
        criado = config.criado_em
        alterado = config.atualizado_em
        dados["nome_fantasia"] = "Nome alterado"
        self.assertRedirects(self.client.post(self.url, dados), self.url)
        config.refresh_from_db()
        self.assertEqual(ConfiguracaoEmpresa.objects.count(), 1)
        self.assertEqual(config.nome_fantasia, "Nome alterado")
        self.assertEqual(config.criado_em, criado)
        self.assertGreater(config.atualizado_em, alterado)
        self.assertContains(self.client.get(self.url), "Nome alterado")

    def test_banco_impede_segunda_configuracao_e_chave_falsa(self):
        config = ConfiguracaoEmpresa.objects.create(nome_fantasia="Original")
        for unica in [True, False]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                ConfiguracaoEmpresa.objects.bulk_create([ConfiguracaoEmpresa(unica=unica)])
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConfiguracaoEmpresa.objects.filter(pk=config.pk).update(unica=False)
        config.refresh_from_db()
        self.assertEqual(config.nome_fantasia, "Original")
        self.assertEqual(ConfiguracaoEmpresa.objects.count(), 1)

    def test_logo_upload_e_remocao_sem_apagar_arquivo(self):
        self.client.force_login(self.admin)
        conteudo = BytesIO()
        Image.new("RGB", (12, 12), "white").save(conteudo, format="PNG")
        logo = SimpleUploadedFile("logo.png", conteudo.getvalue(), content_type="image/png")
        self.assertRedirects(self.client.post(self.url, {"nome_fantasia": "Teste", "logo": logo}), self.url)
        config = ConfiguracaoEmpresa.objects.get()
        caminho, storage = config.logo.name, config.logo.storage
        self.assertTrue(storage.exists(caminho))
        self.assertContains(self.client.get(self.url), "Logo da empresa")
        self.assertRedirects(self.client.post(self.url, {"nome_fantasia": "Teste", "logo-clear": "on"}), self.url)
        config.refresh_from_db()
        self.assertFalse(config.logo)
        self.assertTrue(storage.exists(caminho))

    def test_dados_invalidos_preservam_configuracao(self):
        config = ConfiguracaoEmpresa.objects.create(nome_fantasia="Original")
        self.client.force_login(self.admin)
        resposta = self.client.post(self.url, {"nome_fantasia": "Alterada", "email": "invalido", "estado": "XX"})
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["form"].errors)
        config.refresh_from_db()
        self.assertEqual(config.nome_fantasia, "Original")
        resposta = self.client.post(self.url, {"logo": SimpleUploadedFile("logo.png", b"nao e imagem")})
        self.assertIn("logo", resposta.context["form"].errors)

    def test_csrf_obrigatorio(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.url, {"nome_fantasia": "Indevida"}).status_code, 403)
        self.assertFalse(ConfiguracaoEmpresa.objects.exists())

    def test_paginas_existentes_e_menu(self):
        self.client.force_login(self.admin)
        for nome in ["dashboard:index", "estoque:lista", "clientes:lista", "vendas:lista", "caixa:painel", "contas:lista", "admin:index", "accounts:password_change"]:
            with self.subTest(pagina=nome):
                self.assertEqual(self.client.get(reverse(nome)).status_code, 200)
        self.assertContains(self.client.get(reverse("dashboard:index")), self.url)
        self.assertFalse(ConfiguracaoEmpresa.objects.exists())

    def test_marca_register_e_empresa_separada(self):
        login = reverse("accounts:login")
        self.assertContains(self.client.get(login), "REGISTER")
        self.assertNotContains(self.client.get(login), "PontoCar")
        self.assertFalse(ConfiguracaoEmpresa.objects.exists())
        config = ConfiguracaoEmpresa.objects.create(nome_fantasia="Empresa teste A", razao_social="Razão teste")
        self.assertContains(self.client.get(login), "Empresa: Empresa teste A")
        config.nome_fantasia = ""
        config.save()
        self.assertContains(self.client.get(login), "Empresa: Razão teste")
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("admin:index")), "REGISTER")
