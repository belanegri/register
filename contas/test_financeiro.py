import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from django.db import close_old_connections, connections, connection
from django.core.exceptions import ValidationError

from caixa.models import MovimentoCaixa
from caixa.services import abrir
from vendas.models import FormaPagamento
from .models import ContaPagar, AnexoConta, PagamentoConta
from .forms import ContaForm
from .services import avancar_data, criar_contas, registrar_pagamento


class CadastroFinanceiroTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser('financeiro')
        self.client.force_login(self.usuario)
        self.forma = FormaPagamento.objects.get(nome='PIX')

    def dados(self, **extras):
        dados = dict(chave=str(uuid.uuid4()), descricao='Manutenção da oficina', fornecedor='Fornecedor teste',
                     categoria='Manutenção de Equipamentos', tipo_conta='empresa', valor_original='100,00',
                     desconto='0', juros='0', multa='0', acrescimos='0', vencimento='2027-01-31', modo='unica',
                     forma_prevista=self.forma.pk, competencia='2027-01')
        return dict(dados, **extras)

    def criar(self, **extras):
        dados = self.dados(**extras)
        resposta = self.client.post(reverse('contas:nova'), dados)
        self.assertEqual(resposta.status_code, 302, getattr(resposta, 'context', None) and resposta.context['form'].errors)
        return ContaPagar.objects.filter(lote=dados['chave']).order_by('parcela'), dados

    def pagar(self, conta, **extras):
        dados = dict(chave=str(uuid.uuid4()), valor=str(conta.saldo), data=str(timezone.localdate()),
                     forma=self.forma.pk, origem='externo')
        dados.update(extras)
        return self.client.post(reverse('contas:pagar', args=[conta.pk]), dados), dados

    def test_calculo_servidor_cadastro_nao_paga(self):
        contas, _ = self.criar(desconto='10', juros='3', multa='2', acrescimos='1')
        conta = contas.get()
        self.assertEqual(conta.valor, 96)
        self.assertEqual(conta.saldo, 96)
        self.assertEqual(conta.competencia, date(2027, 1, 1))
        self.assertFalse(PagamentoConta.objects.exists())
        self.assertFalse(MovimentoCaixa.objects.exists())

    def test_invalidos_nao_salvam(self):
        for extras in [dict(desconto='101'), dict(juros='-1'), dict(valor_original='0'),
                       dict(descricao=''), dict(emissao='2027-02-01'),
                       dict(modo='parcelada', quantidade_lancamentos='121'),
                       dict(modo='recorrente', quantidade_lancamentos='2'), dict(competencia='2027-13')]:
            response = self.client.post(reverse('contas:nova'), self.dados(**extras))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors, extras)
        self.assertFalse(ContaPagar.objects.exists())

    def test_parcelas_centavos_vencimento_e_reenvio(self):
        contas, dados = self.criar(modo='parcelada', quantidade_lancamentos='3')
        self.assertEqual(list(contas.values_list('valor', flat=True)), [Decimal('33.34'), Decimal('33.33'), Decimal('33.33')])
        self.assertEqual(list(contas.values_list('vencimento', flat=True)), [date(2027,1,31), date(2027,2,28), date(2027,3,31)])
        self.client.post(reverse('contas:nova'), dados)
        self.assertEqual(ContaPagar.objects.count(), 3)
        self.assertEqual(sum(c.valor for c in contas), 100)

    def test_frequencias_calendario_e_recorrencias(self):
        self.assertEqual(avancar_data(date(2028,1,31), 1, 'mensal'), date(2028,2,29))
        self.assertEqual(avancar_data(date(2028,2,29), 1, 'anual'), date(2029,2,28))
        for freq, esperado in [('semanal',date(2027,2,7)), ('bimestral',date(2027,3,31)),
                               ('trimestral',date(2027,4,30)), ('semestral',date(2027,7,31)), ('anual',date(2028,1,31))]:
            contas, _ = self.criar(modo='recorrente', quantidade_lancamentos='2', frequencia=freq, data_programada='2027-01-30')
            self.assertEqual(contas[1].vencimento, esperado)
            self.assertEqual(sum(c.valor for c in contas), 200)

    def test_edicao_nao_regera_serie_e_salvar_outra(self):
        contas, dados = self.criar(modo='parcelada', quantidade_lancamentos='3')
        conta = contas[1]
        dados.update(valor_original='40', modo='recorrente', quantidade_lancamentos='10', frequencia='anual')
        r = self.client.post(reverse('contas:editar', args=[conta.pk]), dados)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(ContaPagar.objects.count(), 3)
        conta.refresh_from_db()
        self.assertEqual(conta.modo, 'parcelada')
        self.assertEqual(conta.valor, 40)
        self.assertEqual(contas[0].valor, Decimal('33.34'))
        response = self.client.post(reverse('contas:nova'), self.dados(acao='outra'))
        self.assertRedirects(response, reverse('contas:nova'))

    def test_pagamento_parcial_ajustes_saldo_e_idempotencia(self):
        conta = self.criar()[0].get()
        response, dados = self.pagar(conta, valor='40', juros='5', desconto='2')
        self.assertEqual(response.status_code, 302)
        self.client.post(reverse('contas:pagar', args=[conta.pk]), dados)
        conta.refresh_from_db()
        self.assertEqual(conta.valor, 103)
        self.assertEqual(conta.saldo, 63)
        self.assertEqual(conta.status, 'parcial')
        self.assertEqual(conta.pagamentos.count(), 1)
        response, _ = self.pagar(conta, valor='64')
        self.assertContains(response, 'ultrapassar o saldo')
        self.assertEqual(self.pagar(conta, valor='63')[0].status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.saldo, 0)
        self.assertEqual(conta.status, 'paga')
        self.assertEqual(conta.pagamentos.count(), 2)
        self.assertFalse(MovimentoCaixa.objects.exists())

    def test_pagamento_caixa_somente_valor_pago(self):
        caixa = abrir(self.usuario, 200)
        dinheiro = FormaPagamento.objects.get(nome='Dinheiro')
        conta = self.criar()[0].get()
        response, dados = self.pagar(conta, valor='30', origem='caixa', forma=dinheiro.pk)
        self.assertEqual(response.status_code, 302)
        self.client.post(reverse('contas:pagar', args=[conta.pk]), dados)
        self.assertEqual(caixa.saldo_esperado, 170)
        self.assertEqual(MovimentoCaixa.objects.count(), 1)

    def test_status_filtros_e_soma_saldo(self):
        conta = self.criar(vencimento=str(timezone.localdate()-timedelta(days=1)))[0].get()
        self.assertEqual(conta.situacao, 'Atrasada')
        self.pagar(conta, valor='40')
        conta.refresh_from_db()
        self.assertEqual(conta.situacao, 'Parcialmente paga')
        self.assertTrue(conta.atrasada)
        response = self.client.get(reverse('contas:lista'), {'status':'pendente'})
        self.assertEqual(response.context['pendente'], 60)
        self.assertEqual(response.context['atrasado'], 60)
        self.assertEqual(self.client.get(reverse('contas:lista'), {'status':'parcial'}).context['pagina'].paginator.count, 1)
        programada = self.criar(vencimento=str(timezone.localdate()+timedelta(days=5)), data_programada=str(timezone.localdate()))[0].get()
        self.assertEqual(programada.situacao, 'Programada')

    def test_documentos_multiplos_e_comprovante_separados(self):
        arquivos = [SimpleUploadedFile(f'cobranca{i}.pdf', b'%PDF-1.4\n%%EOF') for i in range(2)]
        contas, _ = self.criar(documentos=arquivos)
        conta = contas.get()
        self.assertEqual(conta.anexos.filter(tipo='cobranca').count(), 2)
        response, _ = self.pagar(conta, valor='20', comprovante=SimpleUploadedFile('pago.pdf', b'%PDF-1.4\n%%EOF'))
        self.assertEqual(response.status_code, 302)
        anexo = conta.anexos.get(tipo='comprovante')
        self.assertEqual(anexo.pagamento.valor, 20)
        self.assertEqual(self.client.get(reverse('contas:pdf_individual', args=[conta.pk])).status_code, 200)
        response = self.client.post(reverse('contas:nova'), self.dados(documentos=[SimpleUploadedFile('ruim.html', b'<html>')]))
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(ContaPagar.objects.count(), 1)

    def test_historico_protegido_edicao_cancelamento_exclusao(self):
        conta, dados = self.criar()
        conta = conta.get()
        self.pagar(conta, valor='20')
        dados.update(valor_original='1', desconto='500', fornecedor='Fornecedor atualizado')
        self.assertEqual(self.client.post(reverse('contas:editar', args=[conta.pk]), dados).status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.valor, 100)
        self.assertEqual(conta.fornecedor, 'Fornecedor atualizado')
        self.client.post(reverse('contas:cancelar', args=[conta.pk]), {'motivo':'Teste'})
        self.client.post(reverse('contas:excluir', args=[conta.pk]), {'confirmar':'sim'})
        conta.refresh_from_db()
        self.assertEqual(conta.status, 'parcial')
        sem_pagamento = self.criar()[0].get()
        self.client.post(reverse('contas:excluir', args=[sem_pagamento.pk]), {'confirmar':'sim'})
        self.assertFalse(ContaPagar.objects.filter(pk=sem_pagamento.pk).exists())

    def test_permissoes_e_formas_disponiveis(self):
        form = ContaForm()
        for nome in ['Boleto', 'PIX', 'Transferência', 'Cartão', 'Dinheiro', 'Débito automático', 'Outros']:
            self.assertTrue(form.fields['forma_prevista'].queryset.filter(nome=nome).exists())
        conta = self.criar()[0].get()
        self.client.force_login(get_user_model().objects.create_user('sem_financeiro'))
        for nome, args in [('nova', []), ('editar', [conta.pk]), ('pagar', [conta.pk]), ('excluir', [conta.pk])]:
            self.assertEqual(self.client.post(reverse('contas:'+nome, args=args), {}).status_code, 403)

    def test_formulario_renderizado_para_qa(self):
        pasta = Path('.local/contas-qa')
        pasta.mkdir(parents=True, exist_ok=True)
        response = self.client.get(reverse('contas:nova'))
        for texto in ['Identificação', 'Valores', 'Datas', 'Pagamento', 'Recorrência', 'Documentos', 'Observações', 'Salvar e criar outra']:
            self.assertContains(response, texto)
        (pasta / 'nova.html').write_text(response.content.decode(), encoding='utf-8')
        conta = self.criar()[0].get()
        response = self.client.get(reverse('contas:editar', args=[conta.pk]))
        (pasta / 'editar.html').write_text(response.content.decode(), encoding='utf-8')


class ConcorrenciaFinanceiroTests(TransactionTestCase):
    def test_reenvios_simultaneos_criam_uma_serie(self):
        from concurrent.futures import ThreadPoolExecutor
        usuario = get_user_model().objects.create_superuser('serie-concorrente')
        form = ContaForm(dict(chave=str(uuid.uuid4()), descricao='Série', fornecedor='Teste', categoria='Internet',
                             tipo_conta='empresa', valor_original='90', vencimento='2027-01-31', modo='parcelada',
                             quantidade_lancamentos='3'))
        self.assertTrue(form.is_valid(), form.errors)
        def executar(_):
            close_old_connections()
            try:
                return criar_contas(get_user_model().objects.get(pk=usuario.pk), form.cleaned_data)[1]
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(executar, range(2)))
        self.assertCountEqual(resultados, [True, False])
        self.assertEqual(ContaPagar.objects.count(), 3)

    def test_pagamentos_simultaneos_nao_excedem_saldo(self):
        from concurrent.futures import ThreadPoolExecutor
        usuario = get_user_model().objects.create_superuser('pagamento-concorrente')
        forma = FormaPagamento.objects.create(nome='Forma concorrência')
        conta = ContaPagar.objects.create(descricao='Teste', fornecedor='Teste', valor=100, vencimento=timezone.localdate(), criado_por=usuario)
        def executar(_):
            close_old_connections()
            try:
                registrar_pagamento(get_user_model().objects.get(pk=usuario.pk), conta.pk,
                    dict(chave=uuid.uuid4(), valor=80, juros=0, desconto=0, origem='externo', data=timezone.localdate(), forma=forma))
                return 'ok'
            except ValidationError:
                return 'bloqueado'
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(executar, range(2)))
        self.assertCountEqual(resultados, ['ok', 'bloqueado'])
        conta.refresh_from_db()
        self.assertEqual(conta.saldo, 20)


class MigracaoFinanceiroTests(TransactionTestCase):
    def test_contas_antigas_preservam_valores_pagamento_e_anexos(self):
        from django.db.migrations.executor import MigrationExecutor
        antiga = [('contas', '0004_contapagar_pix_copia_cola')]
        nova = [('contas', '0006_contapagar_codigo_barras_contapagar_linha_digitavel')]
        executor = MigrationExecutor(connection)
        executor.migrate(antiga)
        try:
            apps = executor.loader.project_state(antiga).apps
            from django.conf import settings
            user = apps.get_model(settings.AUTH_USER_MODEL).objects.create(username='historico-financeiro')
            conta = apps.get_model('contas', 'ContaPagar').objects.create(descricao='Histórico', fornecedor='Original',
                valor='120.50', status='paga', criado_por_id=user.pk, pago_por_id=user.pk, pago_em=date(2026,1,15),
                vencimento=date(2026,1,15), forma_nome='Forma histórica')
            apps.get_model('contas', 'AnexoConta').objects.create(conta_id=conta.pk, link='https://example.test/antigo', criado_por_id=user.pk)
            executor = MigrationExecutor(connection)
            executor.migrate(nova)
            atual = ContaPagar.objects.get(pk=conta.pk)
            self.assertEqual(atual.valor, Decimal('120.50'))
            self.assertEqual(atual.valor_original, atual.valor)
            self.assertEqual(atual.valor_pago, atual.valor)
            self.assertEqual(atual.saldo, 0)
            self.assertEqual(atual.pago_em, date(2026,1,15))
            self.assertEqual(atual.forma_nome, 'Forma histórica')
            self.assertEqual(atual.anexos.get().link, 'https://example.test/antigo')
            self.assertFalse(atual.pagamentos.exists())
        finally:
            MigrationExecutor(connection).migrate(nova)
