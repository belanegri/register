import binascii
from decimal import Decimal
from django.test import SimpleTestCase, TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from .boleto import processar_boleto, modulo10, modulo11_arrecadacao, BoletoInvalido
from .pix import processar_pix, PixInvalido
from .captura import capturar_codigo, capturar_texto, CapturaInvalida
from .forms import ContaForm
from .models import ContaPagar
from . import test_financeiro
from .test_boleto import CODIGO, LINHA


def tlv(chave, valor):
    return chave + f'{len(valor):02d}' + valor


def pix_teste(valor='150.00', dinamico=False):
    conta = tlv('00', 'br.gov.bcb.pix') + (tlv('25', 'example.invalid/pix/teste') if dinamico else tlv('01', 'teste@example.invalid'))
    codigo = tlv('00', '01') + tlv('26', conta) + tlv('52', '0000') + tlv('53', '986')
    if valor is not None:
        codigo += tlv('54', valor)
    codigo += tlv('58', 'BR') + tlv('59', 'FORNECEDOR TESTE') + tlv('60', 'SAO PAULO') + tlv('62', tlv('05', 'TESTE123')) + '6304'
    return codigo + f'{binascii.crc_hqx(codigo.encode(), 0xffff):04X}'


def arrecadacao_teste(moeda='6'):
    resto = '83' + moeda + '00000015000' + '1234' + '0000000000000000000000000'
    dv = modulo10 if moeda in '67' else modulo11_arrecadacao
    codigo = resto[:3] + str(dv(resto)) + resto[3:]
    linha = ''.join(codigo[i:i+11] + str(dv(codigo[i:i+11])) for i in range(0,44,11))
    return codigo, linha


class CapturaParserTests(SimpleTestCase):
    def test_arrecadacao_44_48_e_moedas(self):
        self.assertEqual(modulo11_arrecadacao('01230067896'), 0)  # Exemplo FEBRABAN.
        for moeda in '6789':
            codigo, linha = arrecadacao_teste(moeda)
            self.assertEqual(len(linha), 48)
            for entrada in [codigo, linha]:
                dados = processar_boleto(entrada)
                self.assertEqual(dados['codigo_barras'], codigo)
                self.assertEqual(dados['linha_digitavel'], linha)
                self.assertEqual(dados['valor'], Decimal('150') if moeda in '68' else None)
                self.assertIsNone(dados['vencimento'])
            with self.assertRaises(BoletoInvalido):
                processar_boleto(linha[:11] + str((int(linha[11])+1)%10) + linha[12:])
            with self.assertRaises(BoletoInvalido):
                processar_boleto(codigo[:3] + str((int(codigo[3])+1)%10) + codigo[4:])

    def test_pix_estatico_crc_tlv_e_dinamico_sem_consultas(self):
        dados = processar_pix(pix_teste())
        self.assertEqual(dados['valor'], Decimal('150'))
        self.assertEqual(dados['fornecedor'], 'FORNECEDOR TESTE')
        self.assertEqual(dados['informacoes']['Identificador da transação (TXID)'], 'TESTE123')
        for codigo in [pix_teste()[:-1]+'Z', pix_teste().replace('150.00','950.00'), 'chave@example.invalid', pix_teste()[:-5]]:
            with self.subTest(codigo=codigo), self.assertRaises(PixInvalido):
                processar_pix(codigo)
        dados = processar_pix(pix_teste(None, True))
        self.assertIsNone(dados['valor'])
        self.assertIsNone(dados['vencimento'])
        self.assertIn('Dinâmico', dados['informacoes'].values())
        self.assertTrue(any('Nenhum endereço externo' in a for a in dados['avisos']))

    def test_pix_exemplo_oficial_bcb(self):
        codigo = '00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR5913Fulano de Tal6008BRASILIA62070503***63041D3D'
        self.assertEqual(processar_pix(codigo)['fornecedor'], 'Fulano de Tal')

    def test_texto_rotulos_e_conflitos(self):
        texto = 'Beneficiário: Oficina Exemplo\nPagador: Cliente Teste\nDescrição: Revisão mensal\nNúmero do documento: NF123\nValor do documento: R$ 150,00\nVencimento: 22/02/2025\nEmissão: 20/02/2025\n'+LINHA
        resultado = capturar_texto(texto, [])
        campos = resultado['opcoes'][0]['campos']
        self.assertEqual(campos['fornecedor']['valor'], 'Oficina Exemplo')
        self.assertEqual(campos['vencimento']['valor'], '2025-02-22')
        self.assertEqual(campos['numero_documento']['valor'], 'NF123')
        self.assertEqual(campos['emissao']['valor'], '2025-02-20')
        resultado = capturar_texto(texto.replace('150,00','999,00'), [])
        self.assertNotIn('valor_original', resultado['opcoes'][0]['campos'])
        self.assertTrue(any('Divergência' in a for a in resultado['opcoes'][0]['avisos']))

    def test_multiplas_cobrancas_nao_misturam_dados(self):
        r = capturar_texto('Beneficiário: NÃO MISTURAR\n'+LINHA, [pix_teste(), CODIGO])
        self.assertEqual(len(r['opcoes']), 2)
        self.assertTrue(r['avisos'])
        self.assertFalse(any(c.get('fornecedor',{}).get('valor')=='NÃO MISTURAR' for c in [o['campos'] for o in r['opcoes']]))

    def test_vazios_ambiguidade_e_limites(self):
        self.assertFalse(capturar_texto('Pagador: Não é fornecedor', [])['opcoes'])
        self.assertFalse(capturar_texto('Valor total: 10,00\nValor total: 20,00', [])['opcoes'])
        for texto,codigos in [('x'*80001, []), ('', ['x']*21), ('', 'nao-lista')]:
            with self.assertRaises(CapturaInvalida): capturar_texto(texto,codigos)
        r = capturar_codigo(CODIGO)
        self.assertIn('Código do banco',r['informacoes'])
        self.assertNotIn('fornecedor',r['campos'])


class CapturaEndpointTests(TestCase):
    setUp = test_financeiro.CadastroFinanceiroTests.setUp
    dados = test_financeiro.CadastroFinanceiroTests.dados

    def test_endpoint_sem_gravacao_e_persistencia_apos_conferencia(self):
        url = reverse('contas:capturar_cobranca')
        resposta = self.client.post(url, {'tipo':'pix','codigo':pix_teste()}, content_type='application/json')
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(ContaPagar.objects.count(),0)
        campos = resposta.json()['opcoes'][0]['campos']
        self.assertIn('forma_prevista',campos)
        dados = self.dados(**{k:v['valor'] for k,v in campos.items()})
        self.assertEqual(self.client.post(reverse('contas:nova'),dados).status_code,302)
        conta = ContaPagar.objects.get()
        self.assertEqual(conta.pix_copia_cola,pix_teste())
        self.assertEqual(conta.fornecedor,'FORNECEDOR TESTE')
        self.assertEqual(conta.valor,150)
        self.assertEqual(conta.valor_pago,0)
        self.assertContains(self.client.get(reverse('contas:editar',args=[conta.pk])),'captura-arquivo')

    def test_endpoint_permissoes_csrf_erros(self):
        url = reverse('contas:capturar_cobranca')
        self.assertEqual(self.client.get(url).status_code,405)
        for data in [{'codigo':'123'}, {'tipo':'invalido'}, {'tipo':'documento','texto':'x'*80001}, []]:
            self.assertEqual(self.client.post(url,data,content_type='application/json').status_code,400)
        client = Client(enforce_csrf_checks=True); client.force_login(self.usuario)
        self.assertEqual(client.post(url,{'codigo':CODIGO},content_type='application/json').status_code,403)
        self.client.force_login(get_user_model().objects.create_user('captura-sem-permissao'))
        self.assertEqual(self.client.post(url,{},content_type='application/json').status_code,403)

    def test_salvamento_valida_pix_novo_preserva_legado(self):
        form = ContaForm(self.dados(pix_copia_cola=pix_teste()[:-1]+'Z'))
        self.assertFalse(form.is_valid())
        self.assertIn('pix_copia_cola',form.errors)
        # Chaves antigas continuam aceitas; a captura exige Copia e Cola completo.
        self.assertTrue(ContaForm(self.dados(pix_copia_cola='chave-antiga')).is_valid())

    def test_arrecadacao_salva_e_edita(self):
        codigo, linha = arrecadacao_teste()
        dados = self.dados(codigo_boleto=linha)
        self.assertEqual(self.client.post(reverse('contas:nova'),dados).status_code,302)
        conta = ContaPagar.objects.get()
        self.assertEqual(conta.codigo_barras,codigo)
        self.assertEqual(conta.linha_digitavel,linha)
        self.assertEqual(self.client.post(reverse('contas:editar',args=[conta.pk]),dados).status_code,302)
