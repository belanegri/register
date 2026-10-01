"""Lançamentos e pagamentos atômicos; cadastrar nunca movimenta o caixa."""
import calendar
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from caixa.services import exigir, dinheiro, caixa_aberto, movimentar
from core.auditoria import registrar
from vendas.models import FormaPagamento
from .models import ContaPagar, PagamentoConta, AnexoConta
from .boleto import processar_boleto, BoletoInvalido


def avancar_data(data, numero, frequencia):
    if data is None:
        return None
    if frequencia == 'semanal':
        return data + timedelta(weeks=numero)
    meses = {'mensal': 1, 'bimestral': 2, 'trimestral': 3, 'semestral': 6, 'anual': 12}[frequencia] * numero
    ano, mes = divmod(data.year * 12 + data.month - 1 + meses, 12)
    try:
        return data.replace(year=ano, month=mes + 1, day=min(data.day, calendar.monthrange(ano, mes + 1)[1]))
    except (ValueError, OverflowError):
        raise ValidationError('A série ultrapassa o limite de datas permitido. Revise a data inicial ou a quantidade.')


def dividir(valor, quantidade):
    centavos = int(valor * 100)
    base, resto = divmod(centavos, quantidade)
    return [Decimal(base + (i < resto)) / 100 for i in range(quantidade)]


def adicionar_anexo(usuario, conta, arquivo=None, link='', tipo='cobranca', pagamento=None):
    if not arquivo and not link:
        return None
    anexo = AnexoConta.objects.create(conta=conta, arquivo=arquivo or '', link=link, tipo=tipo,
        pagamento=pagamento, nome_arquivo=Path(arquivo.name).name[:255] if arquivo else '', criado_por=usuario)
    registrar(usuario, 'conta.anexo', conta.codigo, anexo=anexo.pk, tipo=tipo)
    return anexo


@transaction.atomic
def criar_contas(usuario, dados):
    exigir(usuario, 'contas.add_contapagar')
    # A mesma chave de formulário nunca cria uma segunda série, mesmo com reenvios simultâneos.
    get_user_model().objects.select_for_update().get(pk=usuario.pk)
    existentes = ContaPagar.objects.filter(lote=dados['chave']).order_by('parcela')
    if existentes.exists():
        if existentes.first().criado_por_id != usuario.pk:
            raise PermissionDenied
        return list(existentes), False
    dados = dados.copy()
    codigo = dados.get('codigo_boleto') or dados.get('linha_digitavel') or dados.get('codigo_barras')
    dados['codigo_barras'] = dados['linha_digitavel'] = ''
    if codigo:
        try:
            boleto = processar_boleto(codigo, dados.get('ciclo_boleto') or 'atual')
        except BoletoInvalido as exc:
            raise ValidationError(str(exc)) from exc
        if dados['modo'] == 'parcelada':
            raise ValidationError('Informe o boleto de cada parcela na edição, após gerar as parcelas.')
        for campo in ['codigo_barras', 'linha_digitavel']:
            dados[campo] = boleto[campo]
    modo = dados['modo']
    quantidade = dados.get('quantidade_lancamentos') if modo != 'unica' else 1
    if not quantidade or not 1 <= quantidade <= 120:
        raise ValidationError('Informe até 120 lançamentos.')
    frequencia = dados.get('frequencia') if modo == 'recorrente' else 'mensal'
    campos = [
    'descricao',
    'fornecedor',
    'tipo_conta',
    'categoria',
    'subcategoria',
    'centro_custo',
    'numero_documento',
    'competencia',
    'emissao',
    'forma_prevista',
    'pix_copia_cola',
    'linha_digitavel',
    'codigo_barras',
    'observacoes',
]
    valores = {nome: dinheiro(dados.get(nome) or 0) for nome in ['valor_original', 'desconto', 'juros', 'multa', 'acrescimos']}
    if valores['valor_original'] <= 0 or any(v < 0 for v in valores.values()):
        raise ValidationError('Confira os valores do lançamento.')
    partes = {nome: dividir(valor, quantidade) if modo == 'parcelada' else [valor] * quantidade for nome, valor in valores.items()}
    contas = []
    for i in range(quantidade):
        conta = ContaPagar(criado_por=usuario, lote=dados['chave'], parcela=i+1, total_parcelas=quantidade,
            modo=modo, frequencia=frequencia if modo == 'recorrente' else '',
            vencimento=avancar_data(dados['vencimento'], i, frequencia),
            data_programada=avancar_data(dados.get('data_programada'), i, frequencia),
            **{c: dados.get(c) for c in campos}, **{nome: itens[i] for nome, itens in partes.items()})
        if i:
            conta.codigo_barras = conta.linha_digitavel = ''
        conta.valor = conta.valor_original - conta.desconto + conta.juros + conta.multa + conta.acrescimos
        if conta.valor <= 0 or conta.valor_original <= 0:
            raise ValidationError('Os ajustes geram uma parcela sem valor. Reduza a quantidade de parcelas ou revise os valores.')
        conta.full_clean()
        conta.save()
        contas.append(conta)
    primeira = contas[0]
    for arquivo in dados.get('documentos', []):
        adicionar_anexo(usuario, primeira, arquivo=arquivo)
    adicionar_anexo(usuario, primeira, arquivo=dados.get('comprovante'), link=dados.get('link_acesso', ''))
    registrar(usuario, 'conta.criada', primeira.codigo, quantidade=quantidade, modo=modo,
              valor=str(sum(c.valor for c in contas)), lote=str(dados['chave']))
    return contas, True


@transaction.atomic
def registrar_pagamento(usuario, pk, dados):
    exigir(usuario, 'contas.change_contapagar')
    if dados['origem'] == 'caixa':
        caixa_aberto(usuario)
    conta = ContaPagar.objects.select_for_update().get(pk=pk)
    anterior = PagamentoConta.objects.filter(chave=dados['chave']).first()
    if anterior:
        if anterior.conta_id != conta.pk or anterior.operador_id != usuario.pk:
            raise PermissionDenied
        return anterior, False
    if not conta.em_aberto:
        raise ValidationError('Esta conta já foi paga ou cancelada.')
    forma = FormaPagamento.objects.filter(pk=dados['forma'].pk, ativa=True, promissoria=False).first()
    if not forma or dados['data'] > timezone.localdate():
        raise ValidationError('Confira a forma e a data do pagamento.')
    valor, juros, desconto = [dinheiro(dados.get(campo) or 0) for campo in ['valor', 'juros', 'desconto']]
    novo_total = conta.valor + juros - desconto
    if valor <= 0 or juros < 0 or desconto < 0 or valor > novo_total - conta.valor_pago:
        raise ValidationError('O valor pago deve ser positivo e não pode ultrapassar o saldo após os ajustes.')
    conta.juros += juros
    conta.desconto += desconto
    conta.valor = novo_total
    conta.valor_pago += valor
    conta.status = 'paga' if conta.valor_pago == novo_total else 'parcial'
    conta.pago_em = dados['data']
    conta.pago_por = usuario
    conta.forma_nome = forma.nome
    movimento = None
    if dados['origem'] == 'caixa':
        if not forma.dinheiro or dados['data'] != timezone.localdate():
            raise ValidationError('Retirada do caixa exige dinheiro e a data de hoje.')
        movimento = movimentar(usuario, 'sangria', valor, f'Pagamento {conta.codigo} · {conta.titulo}')
        if not conta.movimento_id:
            conta.movimento = movimento
    conta.full_clean()
    conta.save()
    pagamento = PagamentoConta.objects.create(conta=conta, chave=dados['chave'], data=dados['data'], valor=valor,
        juros=juros, desconto=desconto, forma=forma, forma_nome=forma.nome, origem=dados['origem'],
        observacao=dados.get('observacao', ''), operador=usuario, movimento=movimento)
    adicionar_anexo(usuario, conta, arquivo=dados.get('comprovante'), tipo='comprovante', pagamento=pagamento)
    registrar(usuario, 'conta.paga' if conta.status == 'paga' else 'conta.pagamento_parcial', conta.codigo,
        pagamento=pagamento.pk, valor=str(valor), saldo=str(conta.saldo), origem=dados['origem'], forma=forma.nome)
    return pagamento, True
