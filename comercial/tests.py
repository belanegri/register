import uuid
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction, DatabaseError, close_old_connections
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from caixa.services import abrir
from caixa.models import MovimentoCaixa
from clientes.models import Cliente
from estoque.models import Peca, Categoria
from vendas.models import Venda, FormaPagamento
from vendas.services import finalizar, cancelar, devolver, corrigir
from core.models import ConfiguracaoEmpresa

from .models import (
    Servico,
    Documento,
    ItemDocumento,
    ContaReceber,
    Recebimento,
)
from .services import converter, receber
from .pdf import gerar_pdf


class ComercialTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            'comercial',
            'comercial@example.test',
            'test-password',
        )

        self.caixa = abrir(self.user, 0)

        self.cliente = Cliente.objects.create(
            nome='Cliente de teste',
            documento='123',
            telefone='1234',
        )

        self.peca = Peca.objects.create(
            nome='Peça de teste',
            categoria=Categoria.objects.first(),
            preco_venda=100,
            quantidade=10,
        )

        self.servico = Servico.objects.create(
            nome='Instalação',
            valor_padrao=50,
        )

        self.forma = FormaPagamento.objects.create(
            nome='Pagamento de teste',
            dinheiro=True,
        )

        self.client.force_login(self.user)

    def documento(self, tipo='orcamento'):
        doc = Documento.objects.create(
            tipo=tipo,
            status='aprovado' if tipo == 'orcamento' else 'aberta',
            cliente=self.cliente,
            criado_por=self.user,
            validade=timezone.localdate() + timedelta(days=7),
            veiculo='Veículo teste',
            desconto=10,
        )

        ItemDocumento.objects.create(
            documento=doc,
            peca=self.peca,
            descricao=self.peca.nome,
            quantidade=1,
            preco=100,
        )

        ItemDocumento.objects.create(
            documento=doc,
            servico=self.servico,
            descricao=self.servico.nome,
            quantidade=1,
            preco=50,
        )

        return doc

    def carrinho(self):
        return {
            str(self.peca.pk): {
                'quantidade': 1,
                'preco': '100',
            },
            f's:{self.servico.pk}': {
                'quantidade': 1,
                'preco': '50',
            },
        }

    def payload_os(self):
        return {'cliente': self.cliente.pk, 'status': 'aberta', 'desconto': '0',
                'condicao_pagamento': 'avista', 'parcelas': '1',
                'itens-TOTAL_FORMS': '1', 'itens-INITIAL_FORMS': '0',
                'itens-0-peca': self.peca.pk, 'itens-0-quantidade': '2', 'itens-0-preco': '100'}

    def test_nova_os_vende_sem_receber_e_nao_duplica(self):
        from .services import registrar_venda_os
        r = self.client.post(reverse('comercial:novo', args=['os']), self.payload_os())
        self.assertEqual(r.status_code, 302)
        doc = Documento.objects.get(tipo='os')
        self.assertEqual(doc.venda.total, 200)
        self.assertEqual(doc.venda.conta_receber.saldo, 200)
        self.assertEqual(registrar_venda_os(self.user, doc.pk).pk, doc.venda_id)
        self.assertEqual(Venda.objects.count(), 1)
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 8)
        self.assertFalse(MovimentoCaixa.objects.exists())
        self.assertNotContains(self.client.get(reverse('comercial:detalhe', args=[doc.pk])), 'Converter em venda')
        # Dados financeiros adulterados no POST não alteram a venda nem o estoque.
        payload = self.payload_os()
        payload.update(status='andamento', desconto='99', responsavel='Técnico')
        self.assertEqual(self.client.post(reverse('comercial:editar', args=[doc.pk]), payload).status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'andamento')
        self.assertEqual(doc.total, 200)
        self.assertEqual(doc.venda.total, 200)
        payload['status'] = 'cancelada'
        self.assertEqual(self.client.post(reverse('comercial:editar', args=[doc.pk]), payload).status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.venda.status, 'cancelada')
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 10)

    def test_os_sem_estoque_ou_caixa_nao_deixa_registros_parciais(self):
        payload = self.payload_os()
        payload['itens-0-quantidade'] = '11'
        response = self.client.post(reverse('comercial:novo', args=['os']), payload)
        self.assertContains(response, 'saldo insuficiente')
        self.assertFalse(Documento.objects.exists())
        self.assertFalse(Venda.objects.exists())
        self.caixa.fechado_em = timezone.now()
        self.caixa.save()
        response = self.client.post(reverse('comercial:novo', args=['os']), self.payload_os())
        self.assertContains(response, 'Abra seu caixa')
        self.assertFalse(Documento.objects.exists())

    def test_boleto_parcelado_os(self):
        forma = FormaPagamento.objects.get(nome='Boleto parcelado')
        payload = self.payload_os()
        payload.update(forma_pagamento=forma.pk, condicao_pagamento='parcelado', parcelas='3',
                       primeiro_vencimento=str(timezone.localdate() + timedelta(days=30)))
        response = self.client.post(reverse('comercial:novo', args=['os']), payload)
        self.assertEqual(response.status_code, 302)
        doc = Documento.objects.get()
        self.assertEqual(doc.forma_pagamento, forma)
        self.assertEqual(doc.parcelas, 3)
        self.assertEqual(doc.venda.conta_receber.vencimento, doc.primeiro_vencimento)
        self.assertFalse(doc.venda.pagamentos.exists())

    def test_venda_mista_servico_sem_estoque_cancelamento(self):
        venda = finalizar(
            self.user,
            uuid.uuid4(),
            self.carrinho(),
            [
                {
                    'forma': self.forma.pk,
                    'valor': 150,
                }
            ],
        )

        self.assertEqual(venda.itens.count(), 2)

        self.assertEqual(
            venda.itens.get(servico=self.servico).custo_unitario,
            0,
        )

        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 9)

        cancelar(
            self.user,
            venda.pk,
            'Teste',
        )

        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 10)

    def test_servico_sozinho_devolucao_e_correcao(self):
        cart = {
            f's:{self.servico.pk}': {
                'quantidade': 2,
                'preco': '50',
            }
        }

        v = finalizar(
            self.user,
            uuid.uuid4(),
            cart,
            [
                {
                    'forma': self.forma.pk,
                    'valor': 100,
                }
            ],
        )

        nova = corrigir(
            self.user,
            v.pk,
            uuid.uuid4(),
            cart,
            [
                {
                    'forma': self.forma.pk,
                    'valor': 100,
                }
            ],
            'Preço',
        )

        devolver(
            self.user,
            nova.pk,
            nova.itens.get().pk,
            1,
            self.forma.pk,
            'Devolução de serviço',
            uuid.uuid4(),
        )

        self.peca.refresh_from_db()

        self.assertEqual(
            self.peca.quantidade,
            10,
        )

        self.assertEqual(
            nova.itens.get().quantidade_restante,
            1,
        )

    def test_servico_inativo_e_preco_negociado(self):
        self.servico.ativo = False
        self.servico.save()

        with self.assertRaises(ValidationError):
            finalizar(
                self.user,
                uuid.uuid4(),
                self.carrinho(),
                [
                    {
                        'forma': self.forma.pk,
                        'valor': 150,
                    }
                ],
            )

        self.assertFalse(Venda.objects.exists())

        self.servico.ativo = True
        self.servico.save()

        cart = self.carrinho()

        cart[f's:{self.servico.pk}'].update(
            preco='40',
            preco_personalizado=True,
        )

        v = finalizar(
            self.user,
            uuid.uuid4(),
            cart,
            [
                {
                    'forma': self.forma.pk,
                    'valor': 140,
                }
            ],
        )

        self.assertEqual(v.total, 140)

    def test_orcamento_aprovado_nao_movimenta(self):
        doc = self.documento()

        self.assertEqual(doc.total, 140)
        self.assertFalse(Venda.objects.exists())
        self.assertFalse(ContaReceber.objects.exists())
        self.assertFalse(MovimentoCaixa.objects.exists())

        self.peca.refresh_from_db()

        self.assertEqual(
            self.peca.quantidade,
            10,
        )

        with self.assertRaises(ValidationError):
            converter(
                self.user,
                doc.pk,
                'venda',
            )

        self.assertFalse(Venda.objects.exists())

    def test_orcamento_venda_e_duplicidade(self):
        doc = self.documento()

        venda = converter(
            self.user,
            doc.pk,
            'venda',
            True,
            pagamentos=[
                {
                    'forma': self.forma.pk,
                    'valor': 140,
                }
            ],
        )

        doc.refresh_from_db()

        self.assertEqual(
            doc.venda,
            venda,
        )

        self.assertEqual(
            venda.cliente,
            self.cliente,
        )

        self.assertEqual(
            venda.desconto,
            10,
        )

        with self.assertRaises(ValidationError):
            converter(
                self.user,
                doc.pk,
                'venda',
                True,
            )

        with self.assertRaises(ValidationError):
            converter(
                self.user,
                doc.pk,
                'os',
                True,
            )

        self.assertEqual(
            Venda.objects.count(),
            1,
        )

    def test_orcamento_os_venda(self):
        orc = self.documento()
        os = converter(self.user, orc.pk, 'os', True)
        self.assertEqual(os.total, orc.total)
        self.assertEqual(os.origem, orc)
        self.assertEqual(os.venda.total, 140)
        self.assertEqual(os.venda.conta_receber.os, os)
        self.assertEqual(os.situacao, 'Aberta')
        self.assertFalse(MovimentoCaixa.objects.exists())
        for doc, destino in [(orc, 'os'), (os, 'venda')]:
            with self.assertRaises(ValidationError):
                converter(self.user, doc.pk, destino, True)
        self.assertEqual(Venda.objects.count(), 1)

    def test_os_direta_pendente_parcial_total(self):
        os = self.documento('os')

        v = converter(
            self.user,
            os.pk,
            'venda',
            True,
            vencimento=timezone.localdate(),
        )

        conta = v.conta_receber

        self.assertEqual(
            conta.os,
            os,
        )

        self.assertEqual(
            conta.saldo,
            140,
        )

        self.assertFalse(
            v.pagamentos.exists()
        )

        self.assertFalse(
            MovimentoCaixa.objects.exists()
        )

        chave = uuid.uuid4()

        r = receber(
            self.user,
            conta.pk,
            40,
            self.forma.pk,
            chave,
        )

        self.assertEqual(
            receber(
                self.user,
                conta.pk,
                40,
                self.forma.pk,
                chave,
            ),
            r,
        )

        self.assertEqual(
            conta.status,
            'Parcialmente recebida',
        )

        self.assertEqual(
            conta.saldo,
            100,
        )

        with self.assertRaises(ValidationError):
            receber(
                self.user,
                conta.pk,
                101,
                self.forma.pk,
                uuid.uuid4(),
            )

        receber(
            self.user,
            conta.pk,
            100,
            self.forma.pk,
            uuid.uuid4(),
        )

        self.assertEqual(
            conta.status,
            'Recebida',
        )

        self.assertEqual(
            conta.saldo,
            0,
        )

        self.assertEqual(
            Recebimento.objects.count(),
            2,
        )

        self.caixa.refresh_from_db()

        self.assertEqual(
            self.caixa.saldo_esperado,
            140,
        )

        with self.assertRaises(DatabaseError), transaction.atomic():
            Recebimento.objects.filter(
                pk=r.pk
            ).update(
                valor=1
            )

        with self.assertRaises(ValidationError):
            cancelar(
                self.user,
                v.pk,
                'Não pode perder recebimentos',
            )

    def test_conversao_atomica_sem_saldo(self):
        doc = self.documento()

        Peca.objects.filter(
            pk=self.peca.pk
        ).update(
            quantidade=0,
            status='vendida',
        )

        with self.assertRaises(ValidationError):
            converter(
                self.user,
                doc.pk,
                'venda',
                True,
                pagamentos=[
                    {
                        'forma': self.forma.pk,
                        'valor': 140,
                    }
                ],
            )

        doc.refresh_from_db()

        self.assertIsNone(
            doc.venda_id
        )

        self.assertEqual(
            doc.status,
            'aprovado',
        )

        self.assertFalse(
            Venda.objects.exists()
        )

        self.assertFalse(
            ContaReceber.objects.exists()
        )

    def test_venda_pendente_reenvio_e_cancelamento(self):
        chave = uuid.uuid4()

        v = finalizar(
            self.user,
            chave,
            self.carrinho(),
            [],
            cliente_id=self.cliente.pk,
            pendente=timezone.localdate(),
        )

        self.assertEqual(
            finalizar(
                self.user,
                chave,
                self.carrinho(),
                [],
                cliente_id=self.cliente.pk,
                pendente=timezone.localdate(),
            ),
            v,
        )

        self.assertEqual(
            ContaReceber.objects.count(),
            1,
        )

        cancelar(
            self.user,
            v.pk,
            'Cancelada',
        )

        self.assertTrue(
            ContaReceber.objects.get().cancelada
        )

        self.peca.refresh_from_db()

        self.assertEqual(
            self.peca.quantidade,
            10,
        )

    def test_conta_manual_e_filtros(self):
        c = ContaReceber.objects.create(
            cliente=self.cliente,
            descricao='Manual',
            valor_original=20,
            vencimento=timezone.localdate() - timedelta(days=1),
        )

        self.assertEqual(
            c.status,
            'Vencida',
        )

        for filtro in [
            '',
            'vencidas',
            'vencer',
            'recebidas',
            'parciais',
            'canceladas',
        ]:
            self.assertEqual(
                self.client.get(
                    reverse('comercial:contas'),
                    {'status': filtro},
                ).status_code,
                200,
            )

        receber(
            self.user,
            c.pk,
            20,
            self.forma.pk,
            uuid.uuid4(),
        )

        self.assertEqual(
            c.status,
            'Recebida',
        )

        self.assertEqual(
            self.client.get(
                reverse(
                    'comercial:conta',
                    args=[c.pk],
                )
            ).status_code,
            200,
        )

    def test_confirmacao_http_get_e_post(self):
        doc = self.documento()

        url = reverse(
            'comercial:converter',
            args=[
                doc.pk,
                'os',
            ],
        )

        self.assertContains(
            self.client.get(url),
            'confirmar',
        )

        self.assertFalse(
            Documento.objects.filter(
                origem=doc
            ).exists()
        )

        self.client.post(
            url,
            {},
        )

        self.assertFalse(
            Documento.objects.filter(
                origem=doc
            ).exists()
        )

        self.assertEqual(
            self.client.post(
                url,
                {'confirmar': 'sim'},
            ).status_code,
            302,
        )

        self.assertEqual(
            self.client.post(
                url,
                {'confirmar': 'sim'},
            ).status_code,
            200,
        )

        self.assertEqual(
            Documento.objects.filter(
                origem=doc
            ).count(),
            1,
        )

    def test_cadastro_documentos_e_servicos(self):
        for tipo in ['orcamento', 'os']:
            url = reverse(
                'comercial:novo',
                args=[tipo],
            )

            self.assertEqual(
                self.client.get(url).status_code,
                200,
            )

            dados = {
                'cliente': self.cliente.pk,
                'status': (
                    'rascunho'
                    if tipo == 'orcamento'
                    else 'aberta'
                ),
                'desconto': '0',
                'validade': str(
                    timezone.localdate()
                ),

                # Novos campos de condição de pagamento.
                'condicao_pagamento': 'avista',
                'parcelas': '1',

                'itens-TOTAL_FORMS': '1',
                'itens-INITIAL_FORMS': '0',
                'itens-MIN_NUM_FORMS': '1',
                'itens-MAX_NUM_FORMS': '100',

                'itens-0-servico': self.servico.pk,
                'itens-0-quantidade': '1',
                'itens-0-preco': '',
            }

            response = self.client.post(
                url,
                dados,
            )

            self.assertEqual(
                response.status_code,
                302,
                response.content.decode()[:500],
            )

            doc = Documento.objects.latest('pk')

            self.assertEqual(
                doc.total,
                50,
            )

            self.assertContains(
                self.client.get(
                    reverse(
                        'comercial:detalhe',
                        args=[doc.pk],
                    )
                ),
                doc.codigo,
            )

        self.assertEqual(
            self.client.get(
                reverse('comercial:servicos')
            ).status_code,
            200,
        )

        self.assertEqual(
            self.client.get(
                reverse('comercial:servico_novo')
            ).status_code,
            200,
        )

    def test_permissoes(self):
        user = get_user_model().objects.create_user(
            'sem-permissao',
            password='test',
        )

        self.client.force_login(user)

        self.assertEqual(
            self.client.get(
                reverse('comercial:contas')
            ).status_code,
            403,
        )

        with self.assertRaises(PermissionDenied):
            converter(
                user,
                self.documento().pk,
                'os',
                True,
            )

    def test_pdv_servico_quantidade_preco_e_retirada(self):
        url = reverse('vendas:carrinho')

        self.client.post(
            url,
            {
                'acao': 'adicionar',
                'peca': f's:{self.servico.pk}',
            },
        )

        self.client.post(
            url,
            {
                'acao': 'quantidade',
                'peca': f's:{self.servico.pk}',
                'quantidade': 2,
            },
        )

        self.client.post(
            url,
            {
                'acao': 'preco',
                'peca': f's:{self.servico.pk}',
                'preco': '40',
            },
        )

        self.assertContains(
            self.client.get(
                reverse('vendas:pdv')
            ),
            'Instalação',
        )

        self.assertEqual(
            self.client.session['carrinho'][
                f's:{self.servico.pk}'
            ]['quantidade'],
            2,
        )

        self.client.post(
            url,
            {
                'acao': 'remover',
                'peca': f's:{self.servico.pk}',
            },
        )

        self.assertFalse(
            self.client.session['carrinho']
        )

    def test_http_conversao_venda_e_pdv_pendente(self):
        doc = self.documento()

        payload = {
            'confirmar': 'sim',
            'chave': str(uuid.uuid4()),
            'cliente': self.cliente.pk,
            'desconto': '10',
            'a_prazo': 'on',
            'vencimento_conta': str(
                timezone.localdate()
            ),
        }

        r = self.client.post(
            reverse(
                'comercial:converter',
                args=[
                    doc.pk,
                    'venda',
                ],
            ),
            payload,
        )

        self.assertEqual(
            r.status_code,
            302,
        )

        doc.refresh_from_db()

        self.assertIsNotNone(
            doc.venda_id
        )

        self.assertEqual(
            doc.venda.total,
            140,
        )

        self.client.post(
            reverse('vendas:carrinho'),
            {
                'acao': 'adicionar',
                'peca': f's:{self.servico.pk}',
            },
        )

        payload.update(
            chave=self.client.session['checkout_chave'],
            desconto='0',
        )

        r = self.client.post(
            reverse('vendas:finalizar'),
            payload,
        )

        self.assertEqual(
            r.status_code,
            302,
        )

        self.assertEqual(
            ContaReceber.objects.count(),
            2,
        )

        self.assertEqual(
            self.client.get(
                reverse(
                    'vendas:detalhe',
                    args=[doc.venda_id],
                )
            ).status_code,
            200,
        )

        self.assertEqual(
            self.client.get(
                reverse(
                    'vendas:recibo',
                    args=[doc.venda_id],
                )
            ).status_code,
            200,
        )

    def test_edicao_convertido_bloqueada_e_validade(self):
        doc = self.documento()

        doc.validade = (
            timezone.localdate()
            - timedelta(days=1)
        )
        doc.save()

        with self.assertRaises(ValidationError):
            converter(
                self.user,
                doc.pk,
                'os',
                True,
            )

        doc.validade = timezone.localdate()
        doc.save()

        converter(
            self.user,
            doc.pk,
            'os',
            True,
        )

        self.assertEqual(
            self.client.post(
                reverse(
                    'comercial:editar',
                    args=[doc.pk],
                ),
                {
                    'status': 'rascunho',
                },
            ).status_code,
            302,
        )

        doc.refresh_from_db()

        self.assertEqual(
            doc.status,
            'convertido',
        )

    def test_itens_repetidos_e_preco_negativo(self):
        from .forms import ItensFormSet

        doc = self.documento()

        payload = {
            'itens-TOTAL_FORMS': '2',
            'itens-INITIAL_FORMS': '0',

            'itens-0-servico': self.servico.pk,
            'itens-0-quantidade': 1,
            'itens-0-preco': '50',

            'itens-1-servico': self.servico.pk,
            'itens-1-quantidade': 1,
            'itens-1-preco': '50',
        }

        fs = ItensFormSet(
            payload,
            instance=doc,
            prefix='itens',
        )

        self.assertFalse(
            fs.is_valid()
        )

        payload['itens-1-preco'] = '-1'

        self.assertFalse(
            ItensFormSet(
                payload,
                instance=doc,
                prefix='itens',
            ).is_valid()
        )

    def test_pdf_completo_com_oito_itens_cabe_em_uma_folha(self):
        from unittest.mock import patch
        from .pdf import Paginas

        doc = self.documento('os')

        doc.placa = 'ABC1D23'
        doc.ano = '2022'
        doc.km = 45000
        doc.combustivel = 'Meio tanque'

        doc.responsavel = 'Técnico de teste'
        doc.previsao = timezone.localdate()
        doc.conclusao = timezone.localdate()

        doc.relato = (
            'Cliente solicita revisão preventiva '
            'e avaliação dos freios.'
        )

        doc.diagnostico = (
            'Desgaste normal dos componentes. '
            'Substituição recomendada.'
        )

        doc.solicitado = (
            'Revisão, substituição de filtros '
            'e ajuste dos freios.'
        )

        doc.observacoes = (
            'Conferir o veículo na entrega.'
        )

        doc.condicoes = (
            'Pagamento na entrega.'
        )

        doc.save()

        self.cliente.endereco = (
            'Rua de teste, 100, Centro, São Paulo/SP'
        )

        self.cliente.email = (
            'cliente@example.test'
        )

        self.cliente.save()

        ConfiguracaoEmpresa.objects.create(
            nome_fantasia='Empresa de teste',
            razao_social='Empresa Comercial de Teste Ltda.',
            documento='12.345.678/0001-99',
            inscricao_estadual='123456',
            endereco='Avenida de teste',
            numero='1000',
            bairro='Centro',
            cidade='São Paulo',
            estado='SP',
            cep='01000-000',
            telefone='(11) 3333-4444',
            whatsapp='(11) 99999-8888',
            email='contato@example.test',
        )

        for n in range(6):
            ItemDocumento.objects.create(
                documento=doc,
                servico=self.servico,
                descricao=f'Serviço complementar {n + 1}',
                quantidade=1,
                preco=25,
            )

        for tipo in ['os', 'orcamento']:
            doc.tipo = tipo

            canvases = []

            def criar(*args, **kwargs):
                canvas = Paginas(
                    *args,
                    **kwargs,
                )

                canvases.append(canvas)

                return canvas

            with patch(
                'comercial.pdf.Paginas',
                side_effect=criar,
            ):
                pdf = gerar_pdf(doc)

            self.assertEqual(
                len(canvases[0].estados),
                1,
            )

            pasta = Path('.local/pdf-qa')

            pasta.mkdir(
                parents=True,
                exist_ok=True,
            )

            (
                pasta
                / f'{tipo}-compacto.pdf'
            ).write_bytes(pdf)

    def test_formularios_e_menu_padronizados(self):
        pasta = Path('.local/ui-qa')

        pasta.mkdir(
            parents=True,
            exist_ok=True,
        )

        for tipo in ['orcamento', 'os']:
            r = self.client.get(
                reverse(
                    'comercial:novo',
                    args=[tipo],
                )
            )

            self.assertContains(
                r,
                'Cliente e Veículo',
            )

            self.assertContains(
                r,
                'Produtos e Serviços',
            )

            self.assertContains(
                r,
                'Observações e Condições',
            )

            self.assertContains(
                r,
                'Resumo Financeiro',
            )

            self.assertContains(
                r,
                'Condição de Pagamento',
            )

            self.assertContains(
                r,
                'nav-icon',
            )

            self.assertNotContains(
                r,
                'Mão de obra',
            )

            (
                pasta
                / f'{tipo}.html'
            ).write_text(
                r.content.decode(),
                encoding='utf-8',
            )

        r = self.client.get(
            reverse(
                'comercial:servico_novo'
            )
        )

        self.assertContains(
            r,
            'Informações do serviço',
        )

        self.assertNotContains(
            r,
            'Mão de obra',
        )

        (
            pasta
            / 'servico.html'
        ).write_text(
            r.content.decode(),
            encoding='utf-8',
        )

    def test_pdf_logo_sem_logo_muitas_paginas_termico(self):
        pasta = Path('.local/pdf-qa')

        pasta.mkdir(
            parents=True,
            exist_ok=True,
        )

        doc = self.documento()

        sem = gerar_pdf(doc)

        self.assertTrue(
            sem.startswith(b'%PDF')
        )

        (
            pasta
            / 'orcamento-sem-logo.pdf'
        ).write_bytes(sem)

        imagem = BytesIO()

        Image.new(
            'RGB',
            (400, 100),
            'green',
        ).save(
            imagem,
            'PNG',
        )

        ConfiguracaoEmpresa.objects.create(
            nome_fantasia='Empresa de teste',
            razao_social='Razão social de teste',
            documento='123456',
            inscricao_estadual='987',
            endereco='Rua de teste',
            numero='12',
            telefone='112233',
            whatsapp='119999',
            email='teste@example.test',
            logo=SimpleUploadedFile(
                'logo.png',
                imagem.getvalue(),
                content_type='image/png',
            ),
        )

        for n in range(75):
            ItemDocumento.objects.create(
                documento=doc,
                servico=self.servico,
                descricao=(
                    f'Item {n + 1:03d} - '
                    'Descrição longa para testar '
                    'quebra automática de linhas '
                    'com segurança'
                ),
                quantidade=1,
                preco=50,
            )

        pdf = gerar_pdf(doc)

        self.assertTrue(
            pdf.startswith(b'%PDF')
        )

        self.assertGreater(
            len(pdf),
            len(sem),
        )

        (
            pasta
            / 'orcamento-multipagina.pdf'
        ).write_bytes(pdf)

        doc.tipo = 'os'

        doc.relato = (
            'Relato do cliente. ' * 30
        )

        doc.diagnostico = (
            'Diagnóstico de teste'
        )

        doc.responsavel = 'Técnico'

        doc.save()

        (
            pasta
            / 'os-a4.pdf'
        ).write_bytes(
            gerar_pdf(doc)
        )

        (
            pasta
            / 'os-58.pdf'
        ).write_bytes(
            gerar_pdf(
                doc,
                termico=True,
            )
        )

        for formato in ['a4', '58']:
            r = self.client.get(
                reverse(
                    'comercial:pdf',
                    args=[
                        doc.pk,
                        formato,
                    ],
                )
            )

            self.assertEqual(
                r.status_code,
                200,
            )

            self.assertEqual(
                r['Content-Type'],
                'application/pdf',
            )


class ConcorrenciaComercialTests(TransactionTestCase):
    def test_conversao_simultanea(self):
        from concurrent.futures import ThreadPoolExecutor

        user = get_user_model().objects.create_superuser(
            'concorrente',
            'c@example.test',
            'password',
        )

        abrir(
            user,
            0,
        )

        cliente = Cliente.objects.create(
            nome='Concorrência'
        )

        servico = Servico.objects.create(
            nome='Serviço concorrente',
            valor_padrao=10,
        )

        doc = Documento.objects.create(
            tipo='os',
            status='aberta',
            cliente=cliente,
            criado_por=user,
        )

        ItemDocumento.objects.create(
            documento=doc,
            servico=servico,
            descricao='Serviço',
            quantidade=1,
            preco=10,
        )

        def executar(_):
            close_old_connections()

            try:
                usuario = (
                    get_user_model()
                    .objects
                    .get(pk=user.pk)
                )

                converter(
                    usuario,
                    doc.pk,
                    'venda',
                    True,
                    vencimento=timezone.localdate(),
                )

                return 'ok'

            except ValidationError:
                return 'bloqueado'

            finally:
                close_old_connections()

        with ThreadPoolExecutor(
            max_workers=2
        ) as pool:
            resultados = list(
                pool.map(
                    executar,
                    range(2),
                )
            )

        self.assertCountEqual(
            resultados,
            [
                'ok',
                'bloqueado',
            ],
        )

        self.assertEqual(
            Venda.objects.count(),
            1,
        )

        self.assertEqual(
            ContaReceber.objects.count(),
            1,
        )

    def test_recebimentos_simultaneos_nao_excedem_saldo(self):
        from concurrent.futures import ThreadPoolExecutor

        cliente = Cliente.objects.create(
            nome='Concorrência recebimentos'
        )

        conta = ContaReceber.objects.create(
            cliente=cliente,
            descricao='Teste',
            valor_original=10,
            vencimento=timezone.localdate(),
        )

        forma = FormaPagamento.objects.create(
            nome='Dinheiro teste',
            dinheiro=True,
        )

        users = [
            get_user_model().objects.create_superuser(
                f'recebe{n}',
                f'r{n}@example.test',
                'password',
            )
            for n in range(2)
        ]

        for user in users:
            abrir(
                user,
                0,
            )

        def executar(uid):
            close_old_connections()

            try:
                receber(
                    get_user_model().objects.get(
                        pk=uid
                    ),
                    conta.pk,
                    10,
                    forma.pk,
                    uuid.uuid4(),
                )

                return 'ok'

            except ValidationError:
                return 'bloqueado'

            finally:
                close_old_connections()

        with ThreadPoolExecutor(
            max_workers=2
        ) as pool:
            resultados = list(
                pool.map(
                    executar,
                    [
                        user.pk
                        for user in users
                    ],
                )
            )

        self.assertCountEqual(
            resultados,
            [
                'ok',
                'bloqueado',
            ],
        )

        self.assertEqual(
            conta.saldo,
            0,
        )

        self.assertEqual(
            Recebimento.objects.count(),
            1,
        )
