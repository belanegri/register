from datetime import date
from decimal import Decimal
from django.test import TestCase
from . import test_financeiro as base


class ParcelamentoFlexivelTests(TestCase):
    setUp = base.CadastroFinanceiroTests.setUp
    dados = base.CadastroFinanceiroTests.dados
    criar = base.CadastroFinanceiroTests.criar
    def test_entrada_parcelas_e_frequencia(self):
        contas,_ = self.criar(modo='parcelada', quantidade_lancamentos='2', entrada='20',
            data_entrada='2027-01-10', frequencia='quinzenal')
        self.assertEqual(list(contas.values_list('valor',flat=True)), [Decimal('20'),Decimal('40'),Decimal('40')])
        self.assertEqual(list(contas.values_list('vencimento',flat=True)),[date(2027,1,10),date(2027,1,31),date(2027,2,15)])

    def test_personalizado_valores_ajustes_e_formas(self):
        contas,_ = self.criar(modo='parcelada', quantidade_lancamentos='2', desconto='10',
            plano_personalizado=f'2027-01-31;30;{self.forma.pk}\n2027-03-01;60;{self.forma.pk}')
        self.assertEqual(sum(c.valor_original for c in contas),100)
        self.assertEqual(sum(c.desconto for c in contas),10)
        self.assertEqual(list(contas.values_list('valor',flat=True)),[Decimal('30'),Decimal('60')])

    def test_recorrencia_intervalo_dias(self):
        contas,_ = self.criar(modo='recorrente', quantidade_lancamentos='2', frequencia='dias',intervalo_dias='10')
        self.assertEqual(contas[1].vencimento,date(2027,2,10))
        self.assertEqual(sum(c.valor for c in contas),200)

    def test_menu_previa_e_acoes(self):
        self.criar()
        from django.urls import reverse
        response = self.client.get(reverse('contas:lista'))
        self.assertContains(response,'Visualização rápida')
        self.assertContains(response,'Confirmar Pagamento')
        self.assertContains(response,'modal-dialog')
