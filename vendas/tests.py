import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.management import call_command
from django.db import DatabaseError, transaction, close_old_connections, connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from caixa.models import SessaoCaixa, MovimentoCaixa
from caixa.services import abrir, fechar, movimentar
from clientes.models import Cliente
from core.models import Evento
from estoque.models import Peca, Categoria
from .models import Venda, Pagamento, FormaPagamento, Devolucao
from .services import finalizar, cancelar, devolver


class OperacaoTests(TestCase):
    def test_recibo_historico_e_permissoes(self):
        venda = self.vender()
        self.client.force_login(self.user)
        url = reverse("vendas:recibo", args=[venda.pk])
        Peca.objects.filter(pk=self.peca.pk).update(nome="Nome alterado", preco_venda=900)
        response = self.client.get(url)
        self.assertContains(response, "Farol de teste")
        self.assertContains(response, "100,00")
        self.assertNotContains(response, "Nome alterado")
        self.assertContains(response, "NÃO FISCAL")
        cancelar(self.user, venda.pk, "Desistência")
        self.assertContains(self.client.get(url), "VENDA CANCELADA")
        from django.contrib.auth.models import Permission
        outro = get_user_model().objects.create_user("leitor_recibo")
        outro.user_permissions.add(Permission.objects.get(codename="view_venda"))
        self.client.force_login(outro)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("operador_teste", password="senha-segura-teste")
        cls.categoria = Categoria.objects.first()
        cls.peca = Peca.objects.create(nome="Farol de teste", categoria=cls.categoria, preco_venda="100.00", quantidade=5)
        cls.dinheiro = FormaPagamento.objects.get(nome="Dinheiro")
        cls.pix = FormaPagamento.objects.get(nome="PIX")
        cls.caixa = abrir(cls.user, "50.00")

    def vender(self, quantidade=1, pagamentos=None, **kwargs):
        return finalizar(self.user, kwargs.pop("chave", uuid.uuid4()),
            {str(self.peca.pk): {"quantidade": quantidade, "preco": "100.00"}},
            pagamentos or [{"forma": self.dinheiro.pk, "valor": str(quantidade * 100)}], **kwargs)

    def test_preco_negociado_no_carrinho_preserva_catalogo(self):
        self.client.force_login(self.user)
        url=reverse("vendas:carrinho")
        self.client.post(url,{"acao":"adicionar","peca":self.peca.pk})
        self.client.post(url,{"acao":"preco","peca":self.peca.pk,"preco":"85,50"})
        self.client.post(url,{"acao":"quantidade","peca":self.peca.pk,"quantidade":2})
        carrinho=self.client.session["carrinho"]
        self.assertTrue(carrinho[str(self.peca.pk)]["preco_personalizado"])
        venda=finalizar(self.user,uuid.uuid4(),carrinho,[{"forma":self.dinheiro.pk,"valor":200}])
        self.assertEqual(venda.total,Decimal("171"))
        self.assertEqual(venda.pagamentos.get().troco,Decimal("29"))
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.preco_venda,Decimal("100"))
        self.assertEqual(venda.itens.get().preco_unitario,Decimal("85.50"))

    def test_venda_baixa_estoque_pagamentos_divididos_e_troco(self):
        venda = self.vender(pagamentos=[{"forma": self.pix.pk, "valor": "40"}, {"forma": self.dinheiro.pk, "valor": "80"}])
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 4)
        self.assertEqual(venda.total, Decimal("100"))
        self.assertEqual(venda.pagamentos.get(dinheiro=True).troco, Decimal("20"))
        self.assertEqual(self.caixa.saldo_esperado, Decimal("110"))
        self.assertTrue(Evento.objects.filter(acao="venda.finalizada", objeto=venda.codigo).exists())

    def test_envio_duplicado_nao_duplica_venda(self):
        chave = uuid.uuid4()
        a, b = self.vender(chave=chave), self.vender(chave=chave)
        self.assertEqual(a.pk, b.pk)
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 4)

    def test_saldo_insuficiente_reverte_tudo(self):
        with self.assertRaises(ValidationError):
            self.vender(quantidade=6)
        self.assertFalse(Venda.objects.exists())
        self.assertFalse(MovimentoCaixa.objects.exists())
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 5)

    def test_pagamento_insuficiente_e_pix_com_troco_rejeitados(self):
        for valor in ["99.99", "110"]:
            with self.assertRaises(ValidationError):
                self.vender(pagamentos=[{"forma": self.pix.pk, "valor": valor}])
        self.assertFalse(Venda.objects.exists())

    def test_preco_alterado_exige_revisar_carrinho(self):
        Peca.objects.filter(pk=self.peca.pk).update(preco_venda=110)
        with self.assertRaises(ValidationError):
            self.vender()

    def test_peca_reservada_nao_vende(self):
        Peca.objects.filter(pk=self.peca.pk).update(status="reservada")
        with self.assertRaises(ValidationError):
            self.vender()

    def test_venda_esgota_e_cancelamento_repoe_uma_vez(self):
        venda = self.vender(quantidade=5)
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.status, "vendida")
        cancelar(self.user, venda.pk, "Cliente desistiu")
        cancelar(self.user, venda.pk, "Envio repetido")
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 5)
        self.assertEqual(self.peca.status, "disponivel")
        self.assertEqual(self.caixa.saldo_esperado, Decimal("50"))
        self.assertEqual(Venda.objects.count(), 1)

    def test_devolucao_parcial_rateia_desconto_sem_perder_centavos(self):
        venda = self.vender(quantidade=3, desconto="0.01", pagamentos=[{"forma": self.pix.pk, "valor": "299.99"}])
        item = venda.itens.get()
        chave = uuid.uuid4()
        primeira = devolver(self.user, venda.pk, item.pk, 1, self.pix.pk, "Devolução", chave)
        repetida = devolver(self.user, venda.pk, item.pk, 1, self.pix.pk, "Reenvio", chave)
        self.assertEqual(primeira.pk, repetida.pk)
        venda.refresh_from_db()
        self.assertEqual(venda.status, "parcial")
        devolver(self.user, venda.pk, item.pk, 2, self.pix.pk, "Restante", uuid.uuid4())
        venda.refresh_from_db()
        self.assertEqual(venda.status, "devolvida")
        self.assertEqual(sum(d.valor for d in Devolucao.objects.all()), Decimal("299.99"))
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 5)
        with self.assertRaises(ValidationError):
            devolver(self.user, venda.pk, item.pk, 1, self.pix.pk, "Excesso", uuid.uuid4())

    def test_caixa_fecha_e_recusa_novas_operacoes(self):
        movimentar(self.user, "suprimento", "10", "Troco")
        movimentar(self.user, "sangria", "5", "Retirada")
        caixa = fechar(self.user, "54", "Faltou um real")
        self.assertEqual(caixa.saldo_esperado_fechamento, Decimal("55"))
        self.assertEqual(caixa.diferenca, Decimal("-1"))
        with self.assertRaises(ValidationError):
            self.vender()
        with self.assertRaises(ValidationError):
            movimentar(self.user, "suprimento", "10", "Teste")

    def test_nao_abre_dois_caixas_e_nao_retira_saldo_inexistente(self):
        with self.assertRaises(ValidationError):
            abrir(self.user, 0)
        with self.assertRaises(ValidationError):
            movimentar(self.user, "sangria", 51, "Teste")

    def test_banco_impede_exclusao_financeira_e_alteracao_de_auditoria(self):
        venda = self.vender()
        for acao in [lambda: Pagamento.objects.filter(venda=venda).delete(),
                     lambda: Pagamento.objects.filter(venda=venda).update(valor=1),
                     lambda: Evento.objects.all().update(acao="apagado")]:
            with self.assertRaises(DatabaseError), transaction.atomic():
                acao()

    def test_sem_permissao_nao_opera_nem_acessa_relatorios(self):
        user = get_user_model().objects.create_user("sem_permissao")
        with self.assertRaises(PermissionDenied):
            abrir(user, 0)
        self.client.force_login(user)
        for url in ["vendas:pdv", "vendas:relatorios", "caixa:painel", "clientes:lista"]:
            self.assertEqual(self.client.get(reverse(url)).status_code, 403)

    def test_paginas_e_fluxo_http_checkout(self):
        self.client.force_login(self.user)
        cliente = Cliente.objects.create(nome="Cliente de teste")
        for url in ["vendas:pdv", "vendas:lista", "vendas:relatorios", "caixa:painel", "clientes:lista", "clientes:novo"]:
            self.assertEqual(self.client.get(reverse(url)).status_code, 200)
        self.assertEqual(self.client.get(reverse("clientes:detalhe", args=[cliente.pk])).status_code, 200)
        self.client.post(reverse("vendas:carrinho"), {"acao": "adicionar", "peca": self.peca.pk})
        chave = self.client.session["checkout_chave"]
        response = self.client.post(reverse("vendas:finalizar"), {"chave": chave, "cliente": cliente.pk, "desconto": "0",
            "pag-TOTAL_FORMS": "1", "pag-INITIAL_FORMS": "0", "pag-MIN_NUM_FORMS": "1", "pag-MAX_NUM_FORMS": "8",
            "pag-0-forma": self.dinheiro.pk, "pag-0-valor": "100"})
        self.assertEqual(response.status_code, 302)
        venda = Venda.objects.get()
        self.assertEqual(self.client.get(reverse("vendas:detalhe", args=[venda.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("caixa:detalhe", args=[self.caixa.pk])).status_code, 200)
        self.assertFalse(self.client.session["carrinho"])

    def test_vendedor_nao_enxerga_venda_alheia(self):
        from django.contrib.auth.models import Group
        call_command("configurar_operacao", verbosity=0)
        outro = get_user_model().objects.create_user("outro")
        outro.groups.add(Group.objects.get(name="Vendedor"))
        venda = self.vender()
        self.client.force_login(outro)
        self.assertEqual(self.client.get(reverse("vendas:detalhe", args=[venda.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("caixa:detalhe", args=[self.caixa.pk])).status_code, 404)
        outro.is_staff = True
        outro.save()
        self.assertNotContains(self.client.get(reverse("admin:vendas_venda_changelist")), venda.codigo)
        self.assertNotContains(self.client.get(reverse("admin:caixa_sessaocaixa_changelist")), self.caixa.codigo)

    def test_movimento_repetido_nao_duplica_sangria(self):
        chave = uuid.uuid4()
        a = movimentar(self.user, "sangria", 10, "Retirada", chave)
        b = movimentar(self.user, "sangria", 10, "Retirada", chave)
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(self.caixa.saldo_esperado, Decimal("40"))

    def test_cancelamento_apos_fechar_caixa_usa_nova_sessao(self):
        venda = self.vender(pagamentos=[{"forma": self.pix.pk, "valor": "100"}])
        fechar(self.user, 50)
        novo = abrir(self.user, 0)
        cancelar(self.user, venda.pk, "Cancelamento posterior")
        self.assertEqual(self.caixa.movimentos.count(), 1)
        self.assertEqual(novo.movimentos.get().valor, Decimal("-100"))

    def test_formulario_antigo_nao_sobrescreve_baixa_do_pdv(self):
        from estoque.forms import PecaAdminForm
        antiga = self.peca.atualizado_em.isoformat()
        self.vender()
        self.peca.refresh_from_db()
        form = PecaAdminForm(instance=self.peca, data={"nome": self.peca.nome, "marca": "", "aplicacao": "",
            "versao_estoque": antiga, "categoria": self.categoria.pk, "preco_venda": "100", "custo": "0",
            "quantidade": "5", "condicao": "usada", "status": "disponivel"})
        self.assertFalse(form.is_valid())
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 4)

    def test_admin_altera_preco_e_registra_antes_depois(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("admin:estoque_peca_change", args=[self.peca.pk]), {
            "nome": self.peca.nome, "marca": "", "aplicacao": "", "categoria": self.categoria.pk,
            "versao_estoque": self.peca.atualizado_em.isoformat(), "preco_venda": "110.00", "custo": "0",
            "quantidade": "5", "condicao": "usada", "status": "disponivel",
            "fotos-TOTAL_FORMS": "0", "fotos-INITIAL_FORMS": "0", "fotos-MIN_NUM_FORMS": "0", "fotos-MAX_NUM_FORMS": "1000",
        })
        self.assertEqual(response.status_code, 302)
        evento = Evento.objects.get(acao="peca.alterada", objeto=self.peca.codigo)
        self.assertEqual(evento.dados["antes"]["preco_venda"], "100.00")
        self.assertEqual(evento.dados["depois"]["preco_venda"], "110.00")

    def test_pagamento_de_um_centavo_e_valido(self):
        from .forms import PagamentoForm
        form = PagamentoForm(data={"forma": self.pix.pk, "valor": "0,01"})
        self.assertTrue(form.is_valid(), form.errors)

    def test_cliente_sem_documento_e_dados_de_venda_historicos(self):
        cliente = Cliente.objects.create(nome="Nome original")
        venda = self.vender(cliente_id=cliente.pk)
        cliente.nome = "Nome atualizado"
        cliente.save()
        self.dinheiro.nome = "Dinheiro renomeado"
        self.dinheiro.save()
        venda.refresh_from_db()
        self.assertEqual(venda.cliente_nome, "Nome original")
        self.assertEqual(venda.pagamentos.get().forma_nome, "Dinheiro")


    def emitir_nota(self, quantidade=1):
        from django.utils import timezone
        cliente = Cliente.objects.create(nome="Cliente Promissória", documento="12345678901", endereco="Rua de teste, 10")
        forma = FormaPagamento.objects.get(nome="Nota promissória")
        return self.vender(quantidade=quantidade, pagamentos=[{"forma": forma.pk, "valor": quantidade*100}], cliente_id=cliente.pk,
            dados_nota={"vencimento": timezone.localdate(), "beneficiario": "PontoCar Comércio de Peças", "local_emissao": "São Paulo/SP", "local_pagamento": "São Paulo/SP"})

    def test_promissoria_impressao_saldo_e_recebimento_idempotente(self):
        from .services import receber_nota
        venda = self.emitir_nota()
        nota = venda.pagamentos.get().nota
        self.assertEqual(venda.pagamentos.get().recebido, 0)
        self.assertEqual(nota.saldo, 100)
        self.assertFalse(MovimentoCaixa.objects.exists())
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("vendas:detalhe", args=[venda.pk])), "Imprimir promissória 58 mm")
        response = self.client.get(reverse("vendas:promissoria", args=[nota.pk]))
        for texto in ["Assinatura do emitente", "Cliente Promissória", "São Paulo/SP", "100,00", "termica.css"]:
            self.assertContains(response, texto)
        chave = uuid.uuid4()
        a = receber_nota(self.user, nota.pk, 40, self.dinheiro.pk, chave)
        b = receber_nota(self.user, nota.pk, 40, self.dinheiro.pk, chave)
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(nota.saldo, 60)
        self.assertEqual(self.caixa.saldo_esperado, 90)
        with self.assertRaises(ValidationError):
            receber_nota(self.user, nota.pk, 61, self.pix.pk, uuid.uuid4())
        for acao in [lambda: type(nota).objects.filter(pk=nota.pk).update(emitente="Outro"),
                     lambda: type(a).objects.filter(pk=a.pk).delete()]:
            with self.assertRaises(DatabaseError), transaction.atomic():
                acao()

    def test_promissoria_exige_documento_e_vencimento(self):
        from django.utils import timezone
        forma = FormaPagamento.objects.get(nome="Nota promissória")
        for cliente in [None, Cliente.objects.create(nome="Sem documento")]:
            with self.assertRaises(ValidationError):
                self.vender(pagamentos=[{"forma": forma.pk, "valor":100}], cliente_id=cliente.pk if cliente else None,
                    dados_nota={"vencimento": timezone.localdate()})
        self.assertFalse(Venda.objects.exists())
        cliente = Cliente.objects.create(nome="Com documento", documento="12345678901")
        with self.assertRaises(ValidationError):
            self.vender(pagamentos=[{"forma": forma.pk, "valor":100}], cliente_id=cliente.pk)

    def test_cancelamento_promissoria_estorna_so_recebido(self):
        from .services import receber_nota
        venda = self.emitir_nota()
        nota = venda.pagamentos.get().nota
        receber_nota(self.user, nota.pk, 30, self.dinheiro.pk, uuid.uuid4())
        cancelar(self.user, venda.pk, "Desistência")
        self.assertEqual(nota.saldo, 0)
        self.assertEqual(self.caixa.saldo_esperado, 50)
        self.assertEqual(MovimentoCaixa.objects.get(tipo="estorno").valor, -30)
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.quantidade, 5)

    def test_devolucao_abate_divida_e_reembolsa_apenas_diferenca(self):
        from .services import receber_nota
        venda = self.emitir_nota(2)
        nota = venda.pagamentos.get().nota
        receber_nota(self.user, nota.pk, 50, self.dinheiro.pk, uuid.uuid4())
        item = venda.itens.get()
        a = devolver(self.user, venda.pk, item.pk, 1, self.dinheiro.pk, "Retorno", uuid.uuid4())
        self.assertEqual(a.abatimento_promissoria, 100)
        self.assertEqual(a.reembolsado, 0)
        self.assertEqual(nota.saldo, 50)
        b = devolver(self.user, venda.pk, item.pk, 1, self.dinheiro.pk, "Retorno", uuid.uuid4())
        self.assertEqual(b.abatimento_promissoria, 50)
        self.assertEqual(b.reembolsado, 50)
        self.assertEqual(nota.saldo, 0)
        self.assertEqual(self.caixa.saldo_esperado, 50)

    def test_edicao_atomica_recalcula_estoque_e_preserva_original(self):
        from .services import corrigir
        venda = self.vender()
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("vendas:editar", args=[venda.pk])), "Salvar correção")
        chave = uuid.uuid4()
        dados = {str(self.peca.pk): {"quantidade": 2, "preco": "90"}}
        nova = corrigir(self.user, venda.pk, chave, dados, [{"forma":self.pix.pk, "valor":180}], "Quantidade e preço corrigidos")
        self.assertEqual(corrigir(self.user, venda.pk, chave, dados, [], "Reenvio").pk, nova.pk)
        venda.refresh_from_db()
        self.peca.refresh_from_db()
        self.assertEqual(venda.status, "cancelada")
        self.assertEqual(venda.itens.get().preco_unitario, 100)
        self.assertEqual(nova.substitui_id, venda.pk)
        self.assertEqual(nova.total, 180)
        self.assertEqual(self.peca.quantidade, 3)
        self.assertEqual(self.caixa.saldo_esperado, 50)
        self.assertContains(self.client.get(reverse("vendas:detalhe", args=[nova.pk])), "Correção da venda")

    def test_edicao_invalida_reverte_cancelamento(self):
        from .services import corrigir
        venda = self.vender()
        with self.assertRaises(ValidationError):
            corrigir(self.user, venda.pk, uuid.uuid4(), {str(self.peca.pk): {"quantidade":6,"preco":"100"}},
                [{"forma":self.pix.pk,"valor":600}], "Correção inválida")
        venda.refresh_from_db()
        self.peca.refresh_from_db()
        self.assertEqual(venda.status, "concluida")
        self.assertEqual(self.peca.quantidade, 4)
        self.assertEqual(MovimentoCaixa.objects.count(), 1)

    def test_edicao_http_e_opcoes_de_pagamento(self):
        self.client.force_login(self.user)
        venda = self.vender()
        response = self.client.get(reverse("vendas:pdv"))
        self.assertContains(response, 'data-dinheiro="1"')
        self.assertContains(response, 'data-promissoria="1"')
        response = self.client.post(reverse("vendas:editar", args=[venda.pk]), {
            "chave":str(uuid.uuid4()), "desconto":"0", "motivo":"Preço corrigido",
            "itens-TOTAL_FORMS":"1", "itens-INITIAL_FORMS":"1", "itens-0-peca":self.peca.pk,
            "itens-0-quantidade":"1", "itens-0-preco":"95,50",
            "pag-TOTAL_FORMS":"1", "pag-INITIAL_FORMS":"1", "pag-0-forma":self.dinheiro.pk, "pag-0-valor":"100"})
        self.assertEqual(response.status_code, 302)
        nova = Venda.objects.get(substitui=venda)
        self.assertEqual(nova.total, Decimal("95.50"))
        self.assertEqual(nova.pagamentos.get().troco, Decimal("4.50"))

    def test_promissoria_escopo_acesso(self):
        from django.contrib.auth.models import Group
        call_command("configurar_operacao", verbosity=0)
        venda = self.emitir_nota()
        outro = get_user_model().objects.create_user("leitor_nota")
        outro.groups.add(Group.objects.get(name="Vendedor"))
        self.client.force_login(outro)
        for nome in ["vendas:promissoria", "vendas:receber_promissoria"]:
            self.assertEqual(self.client.get(reverse(nome, args=[venda.pagamentos.get().nota.pk])).status_code, 404)


class ConcorrenciaTests(TransactionTestCase):
    def test_dois_operadores_disputam_ultima_peca(self):
        categoria = Categoria.objects.create(nome="Concorrência")
        peca = Peca.objects.create(nome="Única", categoria=categoria, quantidade=1, preco_venda=10)
        forma = FormaPagamento.objects.create(nome="Teste PIX")
        usuarios = [get_user_model().objects.create_superuser(f"concorrente{i}") for i in range(2)]
        for usuario in usuarios:
            abrir(usuario, 0)
        def executar(user_id):
            close_old_connections()
            try:
                usuario = get_user_model().objects.get(pk=user_id)
                finalizar(usuario, uuid.uuid4(), {str(peca.pk): {"quantidade": 1, "preco": "10"}}, [{"forma": forma.pk, "valor": "10"}])
                return "ok"
            except ValidationError:
                return "sem_saldo"
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(executar, [u.pk for u in usuarios]))
        self.assertCountEqual(resultados, ["ok", "sem_saldo"])
        peca.refresh_from_db()
        self.assertEqual(peca.quantidade, 0)
        self.assertEqual(Venda.objects.count(), 1)
