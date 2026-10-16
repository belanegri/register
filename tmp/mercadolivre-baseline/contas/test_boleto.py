from datetime import date
from decimal import Decimal
from django.test import SimpleTestCase, TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from .boleto import processar_boleto, BoletoInvalido, modulo11_boleto
from .forms import ContaForm, AnexoForm
from .models import ContaPagar
from .services import criar_contas
from . import test_financeiro

CODIGO = '00192100000000150001234567890123456789012345'
LINHA = '00191234546789012345767890123457210000000015000'

class LeituraBoletoTests(SimpleTestCase):
    def test_conversao_valor_e_ciclos(self):
        for codigo in [CODIGO, LINHA, '00191.23454 67890.123457 67890.123457 2 10000000015000']:
            dados = processar_boleto(codigo)
            self.assertEqual(dados['codigo_barras'], CODIGO)
            self.assertEqual(dados['linha_digitavel'], LINHA)
            self.assertEqual(dados['valor'], Decimal('150'))
            self.assertEqual(dados['vencimento'], date(2025, 2, 22))
        self.assertEqual(processar_boleto(CODIGO, 'anterior')['vencimento'], date(2000, 7, 3))

    def test_rejeita_digitos_e_formatos_invalidos(self):
        invalidos = ['', '0'*44, '8'*48, 'abc'+CODIGO, CODIGO+'1', CODIGO[:4]+'3'+CODIGO[5:]]
        for indice in [9, 20, 31, 32]:
            invalidos.append(LINHA[:indice]+str((int(LINHA[indice])+1)%10)+LINHA[indice+1:])
        for codigo in invalidos:
            with self.subTest(codigo=codigo), self.assertRaises(BoletoInvalido):
                processar_boleto(codigo)

    def test_sem_valor_sem_data(self):
        base = '0019'+'0'*14+CODIGO[19:]
        codigo = base[:4]+str(modulo11_boleto(base))+base[4:]
        dados = processar_boleto(codigo)
        self.assertIsNone(dados['valor'])
        self.assertIsNone(dados['vencimento'])

class CadastroBoletoTests(TestCase):
    setUp = test_financeiro.CadastroFinanceiroTests.setUp
    dados = test_financeiro.CadastroFinanceiroTests.dados
    criar = test_financeiro.CadastroFinanceiroTests.criar

    def test_criar_preencher_editar_limpar(self):
        contas, dados = self.criar(codigo_boleto=CODIGO, valor_original='', vencimento='')
        conta = contas.get()
        self.assertEqual(conta.codigo_barras, CODIGO)
        self.assertEqual(conta.linha_digitavel, LINHA)
        self.assertEqual(conta.valor_original, 150)
        self.assertEqual(conta.vencimento, date(2025, 2, 22))
        url = reverse('contas:editar', args=[conta.pk])
        self.assertContains(self.client.get(url), LINHA)
        dados.update(codigo_boleto=LINHA, valor_original='175', vencimento='2027-03-01')
        self.assertEqual(self.client.post(url, dados).status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.valor_original, 175)
        self.assertEqual(conta.vencimento, date(2027, 3, 1))
        dados['codigo_boleto'] = ''
        self.assertEqual(self.client.post(url, dados).status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.codigo_barras, '')
        self.assertEqual(conta.linha_digitavel, '')

    def test_invalido_nao_salva_e_anexo_independente(self):
        form = ContaForm(self.dados(codigo_boleto='123'))
        self.assertFalse(form.is_valid())
        self.assertIn('codigo_boleto', form.errors)
        self.assertTrue(AnexoForm({'link_acesso': 'https://example.com'}).is_valid())

    def test_serie_nao_repete_boleto_e_reenvio_idempotente(self):
        contas, dados = self.criar(codigo_boleto=CODIGO, modo='recorrente', frequencia='mensal', quantidade_lancamentos='2')
        self.assertEqual(contas[0].codigo_barras, CODIGO)
        self.assertEqual(contas[1].codigo_barras, '')
        self.client.post(reverse('contas:nova'), dados)
        self.assertEqual(ContaPagar.objects.count(), 2)
        form = ContaForm(self.dados(codigo_boleto=CODIGO, modo='parcelada', quantidade_lancamentos=2))
        self.assertFalse(form.is_valid())
        self.assertIn('codigo_boleto', form.errors)

    def test_endpoint_validacao_permissao_csrf(self):
        url = reverse('contas:ler_boleto')
        self.assertEqual(self.client.get(url).status_code, 405)
        r = self.client.post(url, {'codigo_boleto': LINHA})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['codigo_barras'], CODIGO)
        self.assertEqual(r.json()['vencimento'], '2025-02-22')
        self.assertEqual(self.client.post(url, {'codigo_boleto':'123'}).status_code, 400)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.usuario)
        self.assertEqual(csrf.post(url, {'codigo_boleto':CODIGO}).status_code, 403)
        usuario = get_user_model().objects.create_user('sem-permissao')
        self.client.force_login(usuario)
        self.assertEqual(self.client.post(url, {'codigo_boleto':CODIGO}).status_code, 403)

    def test_servico_sem_campos_boleto(self):
        form = ContaForm(self.dados())
        self.assertTrue(form.is_valid(), form.errors)
        dados = form.cleaned_data.copy()
        for campo in ['codigo_boleto', 'codigo_barras', 'linha_digitavel']:
            dados.pop(campo, None)
        contas, _ = criar_contas(self.usuario, dados)
        self.assertEqual(contas[0].codigo_barras, '')

    def test_edicao_antiga_e_valores_pagos_protegidos(self):
        contas, dados = self.criar(codigo_boleto=CODIGO, ciclo_boleto='anterior', vencimento='', valor_original='')
        conta = contas.get()
        self.assertEqual(ContaForm(instance=conta).initial['ciclo_boleto'], 'anterior')
        conta.valor_pago = Decimal('10')
        conta.status = 'parcial'
        conta.save()
        dados.update(valor_original='999', vencimento='2000-07-03')
        form = ContaForm(dados, instance=conta)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['valor_original'], 150)
        dados['codigo_boleto'] = '123'
        response = self.client.post(reverse('contas:editar', args=[conta.pk]), dados)
        self.assertEqual(response.status_code, 200)
        conta.refresh_from_db()
        self.assertEqual(conta.codigo_barras, CODIGO)
