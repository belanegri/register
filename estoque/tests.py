from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from veiculos.models import Veiculo
from .models import Categoria, Localizacao, Peca


class EstoqueTests(TestCase):
    def test_etiqueta_individual_com_acesso_de_consulta(self):
        url = reverse("estoque:etiqueta", args=[self.peca.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.vendedor)
        response = self.client.get(url)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertContains(self.client.get(reverse("estoque:lista")), url)
        self.assertEqual(self.client.get(reverse("estoque:etiqueta", args=[999999])).status_code, 404)

    def test_editar_quantidade_pela_tela_de_estoque(self):
        from core.models import Evento
        usuario = get_user_model().objects.create_superuser("gestor_estoque")
        self.client.force_login(usuario)
        url = reverse("estoque:editar", args=[self.peca.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        dados = {"nome": self.peca.nome, "marca": "Volkswagen", "aplicacao": "Gol",
            "categoria": self.categoria.pk, "preco_venda": "250", "custo": "0", "quantidade": "7",
            "status": "disponivel", "condicao": "usada", "versao_estoque": self.peca.atualizado_em.isoformat(),
            "motivo": "Contagem das peças na prateleira"}
        self.assertEqual(self.client.post(url, dados).status_code, 302)
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 7)
        evento = Evento.objects.get(acao="peca.alterada", objeto=self.peca.codigo)
        self.assertEqual(evento.dados["antes"]["quantidade"], "1")
        self.assertEqual(evento.dados["depois"]["quantidade"], "7")
        self.assertEqual(self.client.post(url, {**dados, "quantidade": "8"}).status_code, 200)
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 7)
        dados["versao_estoque"] = self.peca.atualizado_em.isoformat()
        self.client.post(url, {**dados, "quantidade": "-1"})
        self.client.post(url, {**dados, "quantidade": "9", "motivo": ""})
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 7)
        self.client.force_login(self.vendedor)
        self.assertEqual(self.client.post(url, dados).status_code, 403)

    def test_codigos_sequenciais_de_veiculos_e_localizacoes(self):
        for model, prefixo, dados in [
            (Localizacao, "LOC", {"nome": "Prateleira"}),
            (Veiculo, "VEI", {"marca": "Fiat", "modelo": "Uno", "data_entrada": date.today()}),
        ]:
            primeiro = model.objects.create(**dados)
            segundo = model.objects.create(**dados)
            self.assertTrue(primeiro.codigo.startswith(prefixo + "-"))
            self.assertEqual(int(segundo.codigo.split("-")[1]), int(primeiro.codigo.split("-")[1]) + 1)
            codigo = primeiro.codigo
            primeiro.save()
            primeiro.refresh_from_db()
            self.assertEqual(primeiro.codigo, codigo)

    def test_veiculo_sem_codigo_manual(self):
        from veiculos.forms import VeiculoAdminForm
        form = VeiculoAdminForm(data={"marca": "Fiat", "modelo": "Uno",
            "data_entrada": date.today(), "situacao": "recebido"})
        self.assertNotIn("codigo", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.save().codigo.startswith("VEI-"))

    def test_modelo_da_peca_filtrado_por_marca(self):
        from .forms import PecaAdminForm
        dados = {"nome": "Farol", "marca": "Volkswagen", "aplicacao": "Gol",
            "categoria": self.categoria.pk, "preco_venda": "100", "custo": "0",
            "quantidade": "1", "condicao": "usada", "status": "disponivel"}
        form = PecaAdminForm(data=dados)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().aplicacao, "Gol")
        form = PecaAdminForm(data={**dados, "aplicacao": "Onix"})
        self.assertFalse(form.is_valid())
        self.assertIn("aplicacao", form.errors)
        form = PecaAdminForm(data={**dados, "marca": "Outra marca", "aplicacao": "Modelo especial"})
        self.assertTrue(form.is_valid(), form.errors)

    def test_aplicacao_anterior_preservada(self):
        from .forms import PecaAdminForm
        form = PecaAdminForm(instance=self.peca)
        self.assertIn("Gol G6", form.catalogo[self.peca.marca])

    def test_codigo_automatico_unico_e_preservado_ao_editar(self):
        primeira = Peca.objects.create(nome="Peça automática", categoria=self.categoria, preco_venda=10)
        segunda = Peca.objects.create(nome="Outra peça", categoria=self.categoria, preco_venda=20)
        self.assertRegex(primeira.codigo, r"^REG\d{6,}$")
        self.assertNotEqual(primeira.codigo, segunda.codigo)
        codigo = primeira.codigo
        primeira.nome = "Nome atualizado"
        primeira.save()
        primeira.refresh_from_db()
        self.assertEqual(primeira.codigo, codigo)

    def test_formulario_peca_marca_e_codigo_automatico(self):
        from .forms import PecaAdminForm
        from django import forms
        form = PecaAdminForm(data={"nome": "Farol novo", "marca": "Chevrolet",
            "categoria": self.categoria.pk, "preco_venda": "100.00", "custo": "0",
            "quantidade": "1", "condicao": "usada", "status": "disponivel"})
        self.assertIsInstance(form.fields["marca"].widget, forms.Select)
        self.assertNotIn("codigo", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.save().codigo.startswith("REG"))

    @classmethod
    def setUpTestData(cls):
        cls.categoria, _ = Categoria.objects.get_or_create(nome="Iluminação")
        cls.veiculo = Veiculo.objects.create(codigo="V001", marca="Volkswagen", modelo="Gol",
            versao="G6", ano_modelo=2015, data_entrada=date.today())
        cls.localizacao = Localizacao.objects.create(codigo="A-03-02", nome="Prateleira 02")
        cls.peca = Peca.objects.create(codigo="P001", nome="Farol", categoria=cls.categoria,
            veiculo_origem=cls.veiculo, aplicacao="Gol G6", posicao="direito", ano_inicial=2013,
            ano_final=2016, localizacao=cls.localizacao, preco_venda=Decimal("250.00"))
        call_command("configurar_grupos", verbosity=0)
        cls.vendedor = get_user_model().objects.create_user("vendedor", password="senha-teste-forte")
        cls.vendedor.groups.add(Group.objects.get(name="Vendedor"))

    def test_busca_combina_termos_e_intervalo_de_ano(self):
        self.client.force_login(self.vendedor)
        response = self.client.get(reverse("estoque:lista"), {"q": "farol gol g6 2015 direito"})
        self.assertContains(response, "P001")
        self.assertEqual(response.context["pagina"].paginator.count, 1)
        response = self.client.get(reverse("estoque:lista"), {"q": "farol esquerdo"})
        self.assertEqual(response.context["pagina"].paginator.count, 0)

    def test_pdf_aplica_filtros_e_inclui_todos_os_resultados(self):
        disponiveis = [Peca.objects.create(nome=f"Relatorio estoque {i}", categoria=self.categoria,
            preco_venda=Decimal("10.00")) for i in range(21)]
        Peca.objects.create(nome="Relatorio estoque reservada", categoria=self.categoria,
            preco_venda=Decimal("10.00"), status=Peca.Status.RESERVADA)
        self.client.force_login(self.vendedor)
        with patch("estoque.pdf.gerar_pdf", return_value=HttpResponse("pdf", content_type="application/pdf")) as gerar:
            response = self.client.get(reverse("estoque:imprimir_pdf"), {
                "q": "Relatorio estoque", "status": Peca.Status.DISPONIVEL, "page": 2,
            })
        self.assertEqual(response.status_code, 200)
        resultados = list(gerar.call_args.args[0])
        self.assertEqual(len(resultados), 21)
        self.assertEqual({peca.pk for peca in resultados}, {peca.pk for peca in disponiveis})
        self.assertEqual(gerar.call_args.kwargs, {"consulta": "Relatorio estoque", "status": Peca.Status.DISPONIVEL})

    def test_pdf_requer_permissao_e_responde_com_pdf(self):
        url = reverse("estoque:imprimir_pdf")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.vendedor)
        response = self.client.get(url, {"status": Peca.Status.DISPONIVEL})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertEqual(response["Cache-Control"], "private, no-store")
        sem_permissao = get_user_model().objects.create_user("sem_permissao_pdf")
        self.client.force_login(sem_permissao)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_login_e_permissoes(self):
        self.assertEqual(self.client.get(reverse("estoque:lista")).status_code, 302)
        sem_grupo = get_user_model().objects.create_user("sem_grupo")
        self.client.force_login(sem_grupo)
        self.assertEqual(self.client.get(reverse("estoque:lista")).status_code, 403)
        self.assertNotContains(self.client.get("/"), "Peças disponíveis")
        self.client.force_login(self.vendedor)
        self.assertEqual(self.client.get(reverse("estoque:lista")).status_code, 200)
        self.assertFalse(self.vendedor.has_perm("estoque.change_peca"))

    def test_validacoes_de_ano_e_saldo(self):
        self.peca.ano_final = 2010
        with self.assertRaises(ValidationError):
            self.peca.full_clean()
        self.peca.ano_final = 2016
        self.peca.quantidade = 0
        with self.assertRaises(ValidationError):
            self.peca.full_clean()

    def test_banco_rejeita_precos_negativos(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Peca.objects.filter(pk=self.peca.pk).update(preco_venda=-1)

    def test_banco_rejeita_disponivel_sem_saldo(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Peca.objects.filter(pk=self.peca.pk).update(quantidade=0)

    def test_origem_e_categoria_protegidas(self):
        with self.assertRaises(ProtectedError):
            self.veiculo.delete()
        with self.assertRaises(ProtectedError):
            self.categoria.delete()

    def test_localizacao_rejeita_ciclo(self):
        filha = Localizacao.objects.create(codigo="FILHA", nome="Filha", pai=self.localizacao)
        self.localizacao.pai = filha
        with self.assertRaises(ValidationError):
            self.localizacao.full_clean()

    def test_dashboard_conta_unidades(self):
        self.peca.quantidade = 3
        self.peca.save()
        self.client.force_login(self.vendedor)
        response = self.client.get("/")
        self.assertEqual(response.context["disponiveis"], 3)
        self.assertEqual(response.context["cadastros"], 1)

    def test_grupos_nao_sobrescrevem_permissoes_existentes(self):
        grupo = Group.objects.get(name="Vendedor")
        grupo.permissions.clear()
        call_command("configurar_grupos", verbosity=0)
        self.assertEqual(grupo.permissions.count(), 0)

    def test_logout_exige_post(self):
        self.client.force_login(self.vendedor)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("accounts:logout")).status_code, 302)

    def test_admin_abre_cadastros_e_registra_autor(self):
        from django.contrib.admin.models import LogEntry
        admin = get_user_model().objects.create_superuser("admin_teste", password="senha-teste-forte")
        self.client.force_login(admin)
        for route in ["admin:estoque_peca_add", "admin:estoque_categoria_add",
                      "admin:estoque_localizacao_add", "admin:veiculos_veiculo_add"]:
            self.assertEqual(self.client.get(reverse(route)).status_code, 200)
        response = self.client.post(reverse("admin:estoque_categoria_add"), {
            "nome": "Categoria de teste", "descricao": "", "ativa": "on", "_save": "Salvar",
        })
        self.assertEqual(response.status_code, 302)
        categoria = Categoria.objects.get(nome="Categoria de teste")
        self.assertTrue(LogEntry.objects.filter(user=admin, object_id=str(categoria.pk), action_flag=1).exists())

    def test_csrf_impede_logout_sem_token(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.vendedor)
        self.assertEqual(client.post(reverse("accounts:logout")).status_code, 403)
