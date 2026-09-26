from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from caixa.services import abrir
from caixa.models import MovimentoCaixa
from vendas.models import FormaPagamento
from .models import ContaPagar

class ContasTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_superuser("gestor")
        self.client.force_login(self.user)
        self.conta=ContaPagar.objects.create(descricao="Aluguel",fornecedor="Locador",valor=100,vencimento=timezone.localdate()-timedelta(days=1),criado_por=self.user)
        self.forma=FormaPagamento.objects.get(nome="Dinheiro")

    def pagar(self,origem="externo"):
        return self.client.post(reverse("contas:pagar",args=[self.conta.pk]),{"data":timezone.localdate().isoformat(),"forma":self.forma.pk,"origem":origem})

    def test_paginas_e_pagamento_externo(self):
        for nome,args in [("lista",[]),("nova",[]),("detalhe",[self.conta.pk]),("editar",[self.conta.pk]),("cancelar",[self.conta.pk])]:
            self.assertEqual(self.client.get(reverse("contas:"+nome,args=args)).status_code,200)
        self.assertTrue(self.conta.atrasada)
        self.assertEqual(self.pagar().status_code,302)
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.status,"paga")
        self.assertFalse(MovimentoCaixa.objects.exists())
        self.assertContains(self.pagar(),"já foi paga")

    def test_pagamento_caixa_uma_vez(self):
        caixa=abrir(self.user,200)
        self.assertEqual(self.pagar("caixa").status_code,302)
        self.pagar("caixa")
        self.assertEqual(caixa.saldo_esperado,Decimal("100"))
        self.assertEqual(MovimentoCaixa.objects.count(),1)

    def test_saldo_insuficiente_nao_quita(self):
        abrir(self.user,10)
        self.assertContains(self.pagar("caixa"),"Sangria maior")
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.status,"pendente")
        self.assertFalse(MovimentoCaixa.objects.exists())

    def test_permissao_e_cancelamento(self):
        self.client.post(reverse("contas:cancelar",args=[self.conta.pk]),{"motivo":"Lançamento indevido"})
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.status,"cancelada")
        self.assertContains(self.pagar(),"já foi paga ou cancelada")
        self.client.force_login(get_user_model().objects.create_user("sem_acesso"))
        self.assertEqual(self.client.get(reverse("contas:lista")).status_code,403)

    def test_novos_campos_sem_descricao(self):
        from .forms import ContaForm
        from .categorias import CATEGORIAS
        self.assertEqual(len(CATEGORIAS),92)
        self.assertNotIn("descricao",ContaForm().fields)
        dados={"fornecedor":"Fornecedor teste","tipo_conta":"residencial","categoria":"Energia Elétrica","valor":"150,50","vencimento":"2026-10-15","data_programada":"2026-10-10","forma_prevista":self.forma.pk}
        response=self.client.post(reverse("contas:nova"),dados)
        self.assertEqual(response.status_code,302)
        conta=ContaPagar.objects.get(fornecedor="Fornecedor teste")
        self.assertEqual(conta.valor,Decimal("150.50"))
        self.assertEqual(conta.tipo_conta,"residencial")
        self.assertEqual(conta.categoria,"Energia Elétrica")
        self.assertEqual(str(conta.data_programada),"2026-10-10")
        self.assertEqual(conta.forma_prevista_id,self.forma.pk)
        self.assertEqual(conta.descricao,"")
        self.assertEqual(conta.status,"pendente")
        self.assertContains(self.client.get(reverse("contas:detalhe",args=[conta.pk])),"10/10/2026")
        dados["tipo_conta"]="empresa"
        self.assertEqual(self.client.post(reverse("contas:editar",args=[conta.pk]),dados).status_code,302)
        conta.refresh_from_db()
        self.assertEqual(conta.tipo_conta,"empresa")
        dados["categoria"]="Categoria inexistente"
        self.assertFalse(ContaForm(dados).is_valid())

    def test_filtros_pdf_sem_limite_da_paginacao(self):
        from .views import filtrar_contas
        from django.http import QueryDict
        for i in range(32):
            ContaPagar.objects.create(fornecedor=f"Fornecedor {i}",categoria="Internet",tipo_conta="empresa",valor=10,vencimento="2026-10-10",data_programada="2026-10-09",criado_por=self.user,forma_prevista=self.forma)
        filtros={"status":"todas","tipo_conta":"empresa","data_referencia":"data_programada","inicio":"2026-10-09","fim":"2026-10-09"}
        form,qs=filtrar_contas(filtros)
        self.assertTrue(form.is_valid())
        self.assertEqual(qs.count(),32)
        response=self.client.get(reverse("contas:lista"),filtros)
        self.assertEqual(len(response.context["pagina"]),30)
        self.assertEqual(response.context["pagina"].paginator.count,32)
        response=self.client.get(reverse("contas:pdf_relatorio"),filtros)
        self.assertEqual(response["Content-Type"],"application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        response=self.client.get(reverse("contas:pdf_individual",args=[self.conta.pk]))
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertEqual(self.client.get(reverse("contas:pdf_relatorio"),{"inicio":"invalido"}).status_code,400)

    def test_anexos_em_conta_paga_e_download_protegido(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from django.core.files.storage import InMemoryStorage
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import AnexoConta
        self.pagar()
        with patch.object(AnexoConta._meta.get_field("arquivo"),"storage",InMemoryStorage()):
            response=self.client.post(reverse("contas:anexar",args=[self.conta.pk]),{"comprovante":SimpleUploadedFile("recibo.pdf",b"%PDF-1.4\n%%EOF",content_type="application/pdf"),"link_acesso":"https://example.com/recibo"})
            self.assertEqual(response.status_code,302)
            anexo=AnexoConta.objects.get(conta=self.conta)
            response=self.client.get(reverse("contas:baixar_anexo",args=[anexo.pk]))
            self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-"))
            self.assertContains(self.client.get(reverse("contas:detalhe",args=[self.conta.pk])),"recibo.pdf")
            self.client.force_login(get_user_model().objects.create_user("anexo_sem_acesso"))
            self.assertEqual(self.client.get(reverse("contas:baixar_anexo",args=[anexo.pk])).status_code,403)
            self.assertEqual(self.client.get(reverse("contas:pdf_relatorio")).status_code,403)

    def test_recusa_anexo_invalido_e_link_inseguro(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .forms import AnexoForm
        self.assertFalse(AnexoForm({"link_acesso":"javascript:alert(1)"}).is_valid())
        self.assertFalse(AnexoForm({}, {"comprovante":SimpleUploadedFile("teste.html",b"<html>teste</html>")}).is_valid())
        self.assertFalse(AnexoForm({}, {"comprovante":SimpleUploadedFile("teste.png",b"nao e imagem")}).is_valid())

    def test_editar_excluir_anexos_e_arquivos(self):
        from unittest.mock import patch
        from django.core.files.storage import InMemoryStorage
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import AnexoConta
        storage=InMemoryStorage()
        with patch.object(AnexoConta._meta.get_field("arquivo"),"storage",storage):
            anexo=AnexoConta.objects.create(conta=self.conta,criado_por=self.user,arquivo=SimpleUploadedFile("antigo.pdf",b"%PDF-1.4"),nome_arquivo="antigo.pdf",link="https://example.com/antigo")
            url=reverse("contas:editar_anexo",args=[anexo.pk])
            self.assertContains(self.client.get(url),"antigo.pdf")
            antigo=anexo.arquivo.name
            with self.captureOnCommitCallbacks(execute=True):
                response=self.client.post(url,{"link_acesso":"https://example.com/novo","comprovante":SimpleUploadedFile("novo.pdf",b"%PDF-1.4")})
            self.assertEqual(response.status_code,302)
            anexo.refresh_from_db()
            self.assertEqual(anexo.link,"https://example.com/novo")
            self.assertEqual(anexo.nome_arquivo,"novo.pdf")
            self.assertFalse(storage.exists(antigo))
            self.assertTrue(storage.exists(anexo.arquivo.name))
            self.client.post(url,{"link_acesso":""})
            anexo.refresh_from_db()
            self.assertEqual(anexo.link,"")
            self.assertTrue(anexo.arquivo)
            self.assertContains(self.client.post(url,{"remover_arquivo":"on"}),"Mantenha um arquivo ou link")
            excluir=reverse("contas:excluir_anexo",args=[anexo.pk])
            self.assertEqual(self.client.get(excluir).status_code,200)
            self.assertTrue(AnexoConta.objects.filter(pk=anexo.pk).exists())
            nome=anexo.arquivo.name
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.client.post(excluir).status_code,302)
            self.assertFalse(AnexoConta.objects.filter(pk=anexo.pk).exists())
            self.assertFalse(storage.exists(nome))

    def test_remover_so_arquivo_e_permissoes_anexos(self):
        from unittest.mock import patch
        from django.core.files.storage import InMemoryStorage
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import AnexoConta
        with patch.object(AnexoConta._meta.get_field("arquivo"),"storage",InMemoryStorage()):
            anexo=AnexoConta.objects.create(conta=self.conta,criado_por=self.user,arquivo=SimpleUploadedFile("teste.pdf",b"%PDF-1.4"),nome_arquivo="teste.pdf",link="https://example.com")
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse("contas:editar_anexo",args=[anexo.pk]),{"remover_arquivo":"on","link_acesso":"https://example.com"})
            anexo.refresh_from_db()
            self.assertFalse(anexo.arquivo)
            self.assertEqual(anexo.link,"https://example.com")
            self.client.force_login(get_user_model().objects.create_user("sem_edicao_anexo"))
            for nome in ["editar_anexo","excluir_anexo"]:
                self.assertEqual(self.client.post(reverse("contas:"+nome,args=[anexo.pk])).status_code,403)
            self.assertTrue(AnexoConta.objects.filter(pk=anexo.pk).exists())

    def test_pix_copia_cola_salvo_e_exibido(self):
        from .forms import ContaForm
        codigo = "000201TESTE<>&"
        dados = {"fornecedor":"Fornecedor PIX","tipo_conta":"empresa","categoria":"Internet","valor":"50,00","vencimento":"2026-10-15","forma_prevista":self.forma.pk,"pix_copia_cola":codigo}
        form = ContaForm(dados, instance=self.conta)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.pix_copia_cola, codigo)
        response = self.client.get(reverse("contas:detalhe",args=[self.conta.pk]))
        self.assertContains(response,"Copiar código PIX")
        self.assertContains(response,"000201TESTE&lt;&gt;&amp;")
        self.assertContains(response,"js/copiar-pix.js")
