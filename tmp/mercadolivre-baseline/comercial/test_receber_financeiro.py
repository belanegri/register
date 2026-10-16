import uuid
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from caixa.models import MovimentoCaixa
from caixa.services import abrir
from clientes.models import Cliente
from core.parcelamento import planejar, data_parcela
from vendas.models import FormaPagamento
from .models import ContaReceber, Documento
from .forms import ContaForm
from .services import criar_conta_receber, salvar_plano_receber, receber


class ReceberFinanceiroTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('receber-financeiro')
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(nome='Cliente financeiro')
        self.forma = FormaPagamento.objects.get(nome='PIX')

    def dados(self, **extras):
        dados = dict(cliente=self.cliente.pk, descricao='Cobrança teste', valor_original='100.00',
            vencimento='2027-01-31', observacoes='', chave=str(uuid.uuid4()),
            quantidade_lancamentos='3', frequencia='mensal', forma_prevista=self.forma.pk)
        return dict(dados, **extras)

    def criar(self, **extras):
        form = ContaForm(self.dados(**extras))
        self.assertTrue(form.is_valid(), form.errors)
        return criar_conta_receber(self.user, form.cleaned_data), form.cleaned_data

    def test_centavos_plano_nao_movimenta_caixa(self):
        conta, _ = self.criar()
        self.assertEqual([p['valor'] for p in conta.plano_recebimento], [Decimal('33.34'), Decimal('33.33'), Decimal('33.33')])
        self.assertEqual([p['vencimento'] for p in conta.plano_recebimento], [date(2027,1,31),date(2027,2,28),date(2027,3,31)])
        self.assertFalse(MovimentoCaixa.objects.exists())

    def test_entrada_e_intervalo(self):
        conta, _ = self.criar(entrada='20', data_entrada='2027-01-15', frequencia='dias', intervalo_dias='10', quantidade_lancamentos='2')
        self.assertEqual([p['valor'] for p in conta.plano_recebimento], [Decimal('20'),Decimal('40'),Decimal('40')])
        self.assertEqual(conta.vencimento, date(2027,1,15))
        self.assertEqual(conta.plano_recebimento[-1]['vencimento'], date(2027,2,10))

    def test_recebimento_atualiza_proxima_parcela_e_nao_duplica(self):
        conta, _ = self.criar()
        abrir(self.user, 0)
        chave = uuid.uuid4()
        primeiro = receber(self.user, conta.pk, Decimal('40'), self.forma.pk, chave)
        self.assertEqual(receber(self.user, conta.pk, Decimal('40'), self.forma.pk, chave).pk, primeiro.pk)
        conta.refresh_from_db()
        self.assertEqual(conta.vencimento, date(2027,2,28))
        self.assertEqual(conta.saldo, Decimal('60'))
        self.assertEqual(conta.plano_recebimento[1]['saldo'], Decimal('26.67'))
        self.assertEqual(MovimentoCaixa.objects.count(), 1)
        receber(self.user, conta.pk, Decimal('60'), self.forma.pk, uuid.uuid4())
        conta.refresh_from_db()
        self.assertEqual(conta.status, 'Recebida')
        self.assertTrue(all(p['saldo'] == 0 for p in conta.plano_recebimento))

    def test_reenvio_cadastro(self):
        conta, dados = self.criar()
        self.assertEqual(criar_conta_receber(self.user, dados).pk, conta.pk)
        self.assertEqual(ContaReceber.objects.count(), 1)
        self.assertEqual(conta.parcelas_financeiras.count(), 3)

    def test_personalizado_combina_formas(self):
        outra = FormaPagamento.objects.create(nome='Transferência financeira teste', ativa=True)
        conta, _ = self.criar(plano_personalizado=f'2027-01-15;20;{outra.pk}\n2027-02-20;80;{self.forma.pk}')
        self.assertEqual(list(conta.parcelas_financeiras.values_list('forma_prevista_id',flat=True)), [outra.pk,self.forma.pk])

    def test_personalizado_invalido_nao_salva(self):
        for plano in ['2027-01-15;99', '2027-02-01;50\n2027-01-01;50', '2027-01-15;100;999999', '2027-01-15;-1', 'inválido']:
            response = self.client.post(reverse('comercial:conta_nova'), self.dados(plano_personalizado=plano))
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.context['form'].errors)
        self.assertFalse(ContaReceber.objects.exists())

    def test_plano_os_preserva_vinculo(self):
        os = Documento.objects.create(tipo='os',status='aberta',cliente=self.cliente,criado_por=self.user)
        conta = ContaReceber.objects.create(cliente=self.cliente,descricao='OS',os=os,valor_original=100,vencimento=date(2027,1,1))
        salvar_plano_receber(self.user,conta,planejar(100,date(2027,1,1),2))
        conta.refresh_from_db(); os.refresh_from_db()
        self.assertEqual(conta.os_id,os.pk)
        self.assertEqual(os.status,'aberta')
        self.assertFalse(MovimentoCaixa.objects.exists())
        response = self.client.post(reverse('comercial:conta_excluir',args=[conta.pk]), {'confirmar':'sim'})
        self.assertEqual(response.status_code,302)
        self.assertTrue(ContaReceber.objects.filter(pk=conta.pk).exists())

    def test_historico_bloqueia_exclusao_e_alteracao_plano(self):
        conta, _ = self.criar()
        abrir(self.user,0)
        receber(self.user,conta.pk,10,self.forma.pk,uuid.uuid4())
        with self.assertRaises(ValidationError):
            salvar_plano_receber(self.user,conta,planejar(100,date(2027,1,1),2))
        self.client.post(reverse('comercial:conta_excluir',args=[conta.pk]), {'confirmar':'sim'})
        self.assertTrue(ContaReceber.objects.filter(pk=conta.pk).exists())
        self.assertEqual(conta.recebimentos.count(),1)

    def test_exclusao_exige_confirmacao_e_get_nao_muta(self):
        conta, _ = self.criar()
        url = reverse('comercial:conta_excluir',args=[conta.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        self.client.post(url,{})
        self.assertTrue(ContaReceber.objects.filter(pk=conta.pk).exists())
        self.client.post(url,{'confirmar':'sim'})
        self.assertFalse(ContaReceber.objects.filter(pk=conta.pk).exists())

    def test_lista_previa_impressao_e_filtros(self):
        conta, _ = self.criar()
        lista = self.client.get(reverse('comercial:contas'), {'q':'Cliente financeiro'})
        self.assertContains(lista,'Visualização rápida')
        self.assertContains(lista,'Confirmar Pagamento')
        self.assertEqual(lista.context['pendente'],100)
        self.assertContains(self.client.get(reverse('comercial:conta_imprimir',args=[conta.pk])),conta.codigo)
        self.assertContains(self.client.get(reverse('comercial:conta',args=[conta.pk])),'Parcelamento')
        self.assertContains(self.client.get(reverse('comercial:conta_parcelamento',args=[conta.pk])),'Salvar cobrança')
        self.assertFalse(MovimentoCaixa.objects.exists())

    def test_permissoes_acoes(self):
        conta,_ = self.criar()
        self.client.force_login(get_user_model().objects.create_user('sem-permissao'))
        for nome in ['conta_excluir','conta_parcelamento','conta_imprimir']:
            self.assertEqual(self.client.get(reverse('comercial:'+nome,args=[conta.pk])).status_code,403)

    def test_calendario_e_validacoes(self):
        self.assertEqual(data_parcela(date(2028,1,31),1,'mensal'),date(2028,2,29))
        self.assertEqual(data_parcela(date(2028,1,31),2,'mensal'),date(2028,3,31))
        self.assertEqual(data_parcela(date(2027,1,1),1,'quinzenal'),date(2027,1,16))
        for total, quantidade in [('NaN',2),('1.001',2),('0.01',2),('100',121)]:
            with self.assertRaises(ValidationError):
                planejar(total,date(2027,1,1),quantidade)

    def test_os_registrada_aplica_condicao_parcelada_sem_receber(self):
        from .models import Servico, ItemDocumento
        from .services import registrar_venda_os
        abrir(self.user,0)
        servico = Servico.objects.create(nome='Serviço parcelado',valor_padrao=100)
        os = Documento.objects.create(tipo='os',status='aberta',cliente=self.cliente,criado_por=self.user,
            condicao_pagamento='parcelado',parcelas=3,primeiro_vencimento=date(2027,1,31))
        ItemDocumento.objects.create(documento=os,servico=servico,descricao=servico.nome,quantidade=1,preco=100)
        venda = registrar_venda_os(self.user,os.pk)
        conta = venda.conta_receber
        self.assertEqual(conta.parcelas_financeiras.count(),3)
        self.assertEqual(conta.os_id,os.pk)
        self.assertEqual(conta.saldo,100)
        self.assertEqual(registrar_venda_os(self.user,os.pk).pk,venda.pk)
        self.assertEqual(conta.parcelas_financeiras.count(),3)
        self.assertFalse(MovimentoCaixa.objects.exists())

    def test_csrf_protege_exclusao(self):
        from django.test import Client
        conta,_ = self.criar()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(reverse('comercial:conta_excluir',args=[conta.pk]),{'confirmar':'sim'})
        self.assertEqual(response.status_code,403)
        self.assertTrue(ContaReceber.objects.filter(pk=conta.pk).exists())

    def test_promissorias_sincronizam_saldo_sem_duplicar_contas(self):
        from vendas.models import Venda, Pagamento, NotaPromissoria
        from vendas.services import receber_nota
        caixa = abrir(self.user,0)
        forma = FormaPagamento.objects.create(nome='Promissória financeira teste',promissoria=True)
        venda = Venda.objects.create(vendedor=self.user,cliente=self.cliente,caixa=caixa,subtotal=100,total=100)
        pagamento = Pagamento.objects.create(venda=venda,forma=forma,forma_nome=forma.nome,
            promissoria=True,dinheiro=False,valor=100,recebido=0)
        nota = NotaPromissoria.objects.create(pagamento=pagamento,emitida_em=timezone.localdate(),
            vencimento=date(2027,1,31),emitente=self.cliente.nome,documento='123',beneficiario='Empresa teste',
            local_emissao='São Paulo',local_pagamento='São Paulo')
        response = self.client.get(reverse('comercial:contas'))
        self.assertContains(response,nota.codigo)
        self.assertEqual(response.context['saldo_promissorias'],100)
        receber_nota(self.user,nota.pk,40,self.forma.pk,uuid.uuid4())
        response = self.client.get(reverse('comercial:contas'), {'status':'parciais'})
        self.assertEqual(response.context['saldo_promissorias'],60)
        self.assertContains(response,nota.codigo)
        self.assertFalse(ContaReceber.objects.exists())
        self.assertEqual(MovimentoCaixa.objects.count(),1)

    def test_promissorias_respeitam_visibilidade_das_vendas(self):
        from django.contrib.auth.models import Permission
        from .financeiro_consultas import contexto_promissorias
        from django.http import QueryDict
        usuario = get_user_model().objects.create_user('consulta-restrita')
        usuario.user_permissions.add(Permission.objects.get(content_type__app_label='vendas',codename='view_venda'))
        from vendas.models import Venda, Pagamento, NotaPromissoria
        caixa = abrir(self.user,0)
        forma = FormaPagamento.objects.create(nome='Promissória restrita teste',promissoria=True)
        venda = Venda.objects.create(vendedor=self.user,cliente=self.cliente,caixa=caixa,subtotal=100,total=100)
        pagamento = Pagamento.objects.create(venda=venda,forma=forma,forma_nome=forma.nome,promissoria=True,
            dinheiro=False,valor=100,recebido=0)
        NotaPromissoria.objects.create(pagamento=pagamento,emitida_em=timezone.localdate(),vencimento=date(2027,1,31),
            emitente='Cliente restrito',documento='123',beneficiario='Teste',local_emissao='SP',local_pagamento='SP')
        context = contexto_promissorias(usuario,QueryDict())
        self.assertEqual(context['pagina_promissorias'].paginator.count,0)
