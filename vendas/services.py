from decimal import Decimal, ROUND_DOWN
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from datetime import date
from estoque.models import Peca
from clientes.models import Cliente
from caixa.models import MovimentoCaixa
from caixa.services import caixa_aberto, exigir, dinheiro
from core.auditoria import registrar
from core.documentos import empresa_atual
from .models import Venda, ItemVenda, Pagamento, FormaPagamento, Devolucao, NotaPromissoria, MovimentoPromissoria


def quantidade_inteira(valor):
    try:
        valor = int(str(valor))
        if valor <= 0 or valor > 1000000:
            raise ValueError
        return valor
    except (ValueError, TypeError):
        raise ValidationError("Informe uma quantidade inteira positiva.")


@transaction.atomic
def finalizar(usuario, chave, carrinho, pagamentos, desconto=0, cliente_id=None, dados_nota=None, precos_correcao=None):
    exigir(usuario, "vendas.usar_pdv")
    if precos_correcao is not None:
        exigir(usuario, "vendas.editar_venda")
    caixa = caixa_aberto(usuario)  # serializa finalizações/reenvios do mesmo operador
    existente = Venda.objects.filter(chave=chave).first()
    if existente:
        if existente.vendedor_id != usuario.pk:
            raise PermissionDenied
        return existente
    if not carrinho or len(carrinho) > 100:
        raise ValidationError("Adicione entre 1 e 100 peças ao carrinho.")
    desconto = dinheiro(desconto)
    if desconto < 0:
        raise ValidationError("O desconto não pode ser negativo.")
    if desconto:
        exigir(usuario, "vendas.dar_desconto")
    cliente = None
    if cliente_id:
        cliente = Cliente.objects.filter(pk=cliente_id, ativo=True).first()
        if not cliente:
            raise ValidationError("Cliente não encontrado ou inativo.")
    pecas = list(Peca.objects.select_for_update().filter(pk__in=carrinho.keys()).order_by("pk"))
    if len(pecas) != len(carrinho):
        raise ValidationError("Uma peça não está mais disponível. Revise o carrinho.")
    linhas = []
    subtotal = Decimal("0.00")
    for peca in pecas:
        dados = carrinho[str(peca.pk)]
        qtd = quantidade_inteira(dados["quantidade"])
        if peca.status != Peca.Status.DISPONIVEL or peca.quantidade < qtd:
            raise ValidationError(f"{peca.codigo}: saldo insuficiente ou peça indisponível.")
        preco = dinheiro(precos_correcao[str(peca.pk)]) if precos_correcao is not None else peca.preco_venda
        if precos_correcao is None and dados.get("preco_personalizado"):
            preco = dinheiro(dados["preco"])
            if preco <= 0:
                raise ValidationError("O preço negociado deve ser positivo.")
        if preco < 0:
            raise ValidationError("Preço unitário inválido.")
        if precos_correcao is None and not dados.get("preco_personalizado") and dinheiro(dados["preco"]) != peca.preco_venda:
            raise ValidationError(f"O preço de {peca.codigo} mudou. Remova a peça e adicione novamente.")
        bruto = preco * qtd
        subtotal += bruto
        linhas.append((peca, qtd, bruto))
    total = subtotal - desconto
    if total <= 0 or subtotal > Decimal("9999999999.99") or total > Decimal("9999999999.99"):
        raise ValidationError("O total deve ser positivo e estar dentro do limite permitido.")
    recebimentos = []
    if not pagamentos or len(pagamentos) > 8:
        raise ValidationError("Informe de 1 a 8 pagamentos.")
    for dados in pagamentos:
        forma = FormaPagamento.objects.filter(pk=dados["forma"], ativa=True).first()
        valor = dinheiro(dados["valor"])
        if not forma or valor <= 0:
            raise ValidationError("Informe uma forma de pagamento ativa e um valor positivo.")
        recebimentos.append([forma, valor, valor, Decimal("0.00")])
    tem_nota = any(p[0].promissoria for p in recebimentos)
    if tem_nota:
        dados_nota = dados_nota or {}
        if not cliente or not cliente.documento.strip():
            raise ValidationError("Para emitir a promissória, selecione um cliente com CPF/CNPJ cadastrado.")
        if not isinstance(dados_nota.get("vencimento"), date) or dados_nota["vencimento"] < timezone.localdate():
            raise ValidationError("Informe um vencimento a partir de hoje para a promissória.")
        for campo in ["beneficiario", "local_emissao", "local_pagamento"]:
            if not str(dados_nota.get(campo, "")).strip():
                raise ValidationError("Preencha beneficiário, local de emissão e local de pagamento da promissória.")
    recebido = sum(p[1] for p in recebimentos)
    if recebido < total:
        raise ValidationError("Os pagamentos não cobrem o total da venda.")
    troco = recebido - total
    if troco:
        em_dinheiro = [p for p in recebimentos if p[0].dinheiro]
        if not em_dinheiro or troco >= sum(p[1] for p in em_dinheiro):
            raise ValidationError("Excedentes só podem ser devolvidos como troco de pagamento em dinheiro.")
        restante = troco
        for p in reversed(em_dinheiro):
            usado = min(restante, p[1])
            p[1] -= usado
            p[3] = usado
            restante -= usado
    if any(p[1] <= 0 for p in recebimentos):
        raise ValidationError("Remova pagamentos integralmente excedentes e ajuste os valores.")
    venda = Venda.objects.create(empresa_emissao=empresa_atual(), chave=chave, vendedor=usuario, caixa=caixa, cliente=cliente,
        cliente_nome=cliente.nome if cliente else "Consumidor não identificado", subtotal=subtotal, desconto=desconto, total=total)
    # Rateio em centavos pelo método dos maiores restos; soma exata do desconto.
    quotas = [desconto * bruto / subtotal for _, _, bruto in linhas]
    rateios = [q.quantize(Decimal(".01"), rounding=ROUND_DOWN) for q in quotas]
    centavos = int((desconto - sum(rateios)) * 100)
    for i in sorted(range(len(linhas)), key=lambda i: quotas[i] - rateios[i], reverse=True)[:centavos]:
        rateios[i] += Decimal(".01")
    for (peca, qtd, bruto), rateio in zip(linhas, rateios):
        ItemVenda.objects.create(venda=venda, peca=peca, descricao=f"{peca.codigo} · {peca.nome}",
            quantidade=qtd, preco_unitario=bruto/qtd, custo_unitario=peca.custo,
            desconto=rateio, total=bruto-rateio)
        peca.quantidade -= qtd
        if peca.quantidade == 0:
            peca.status = Peca.Status.VENDIDA
        peca.save(update_fields=["quantidade", "status", "atualizado_em"])
    for forma, valor, recebido_linha, troco_linha in recebimentos:
        pagamento = Pagamento.objects.create(venda=venda, forma=forma, forma_nome=forma.nome, dinheiro=forma.dinheiro,
            promissoria=forma.promissoria, valor=valor, recebido=0 if forma.promissoria else recebido_linha, troco=troco_linha)
        if forma.promissoria:
            nota = NotaPromissoria.objects.create(pagamento=pagamento, emitida_em=timezone.localdate(),
                vencimento=dados_nota["vencimento"], emitente=cliente.nome, documento=cliente.documento,
                endereco=cliente.endereco, beneficiario=dados_nota["beneficiario"],
                documento_beneficiario=dados_nota.get("documento_beneficiario", ""),
                local_emissao=dados_nota["local_emissao"], local_pagamento=dados_nota["local_pagamento"])
            registrar(usuario, "promissoria.emitida", venda.codigo, nota=nota.codigo, valor=str(valor))
        else:
            MovimentoCaixa.objects.create(sessao=caixa, operador=usuario, tipo="venda", valor=valor,
                afeta_saldo=forma.dinheiro, venda=venda, descricao=f"{venda.codigo} · {forma.nome}")
    registrar(usuario, "venda.finalizada", venda.codigo, total=str(total), desconto=str(desconto),
        itens=[{"peca": p.codigo, "quantidade": q, "preco_catalogo": str(p.preco_venda), "preco_vendido": str(bruto/q)} for p, q, bruto in linhas])
    return venda


@transaction.atomic
def cancelar(usuario, venda_id, motivo):
    exigir(usuario, "vendas.cancelar_venda")
    caixa = caixa_aberto(usuario)
    venda = Venda.objects.select_for_update().get(pk=venda_id)
    if venda.status == "cancelada":
        return venda
    if venda.status != "concluida" or not motivo.strip():
        raise ValidationError("Informe o motivo. Vendas com devolução não podem ser canceladas; devolva os itens restantes.")
    pagamentos = list(venda.pagamentos.all())
    notas = list(NotaPromissoria.objects.select_for_update().filter(pagamento__venda=venda).order_by("pk"))
    recebidos_notas = list(MovimentoPromissoria.objects.filter(nota__in=notas, tipo="recebido"))
    dinheiro_estornado = sum(p.valor for p in pagamentos if p.dinheiro) + sum(m.valor for m in recebidos_notas if m.dinheiro)
    if dinheiro_estornado > caixa.saldo_esperado:
        raise ValidationError("Dinheiro insuficiente no caixa para o estorno. Registre um suprimento se necessário.")
    itens = list(venda.itens.order_by("peca_id"))
    pecas = {p.pk: p for p in Peca.objects.select_for_update().filter(pk__in=[i.peca_id for i in itens]).order_by("pk")}
    for item in itens:
        peca = pecas[item.peca_id]
        peca.quantidade += item.quantidade
        if peca.status == Peca.Status.VENDIDA:
            peca.status = Peca.Status.DISPONIVEL
        peca.save(update_fields=["quantidade", "status", "atualizado_em"])
    for pagamento in pagamentos:
        if pagamento.promissoria:
            continue
        MovimentoCaixa.objects.create(sessao=caixa, operador=usuario, tipo="estorno", venda=venda,
            valor=-pagamento.valor, afeta_saldo=pagamento.dinheiro,
            descricao=f"Cancelamento {venda.codigo} · {pagamento.forma_nome}")
    for nota in notas:
        if nota.saldo > 0:
            MovimentoPromissoria.objects.create(nota=nota, operador=usuario, caixa=caixa, tipo="abatido", valor=nota.saldo, motivo="Cancelamento da venda")
    for movimento in recebidos_notas:
        MovimentoCaixa.objects.create(sessao=caixa, operador=usuario, tipo="estorno", venda=venda,
            valor=-movimento.valor, afeta_saldo=movimento.dinheiro,
            descricao=f"Cancelamento {venda.codigo} · Recebimento {movimento.nota.codigo}")
    venda.status = "cancelada"
    venda.motivo_cancelamento = motivo.strip()
    venda.save(update_fields=["status", "motivo_cancelamento"])
    registrar(usuario, "venda.cancelada", venda.codigo, motivo=motivo, total=str(venda.total))
    return venda


@transaction.atomic
def devolver(usuario, venda_id, item_id, quantidade, forma_id, motivo, chave):
    exigir(usuario, "vendas.devolver_venda")
    caixa = caixa_aberto(usuario)
    venda = Venda.objects.select_for_update().get(pk=venda_id)
    existente = Devolucao.objects.filter(chave=chave).first()
    if existente:
        if existente.item.venda_id != venda.pk or existente.operador_id != usuario.pk:
            raise PermissionDenied
        return existente
    if venda.status not in ["concluida", "parcial"] or not motivo.strip():
        raise ValidationError("Informe o motivo para uma venda com itens a devolver.")
    item = venda.itens.filter(pk=item_id).first()
    if not item:
        raise ValidationError("Item inválido.")
    qtd = quantidade_inteira(quantidade)
    anteriores = list(item.devolucoes.all())
    quantidade_antes = sum(d.quantidade for d in anteriores)
    if qtd > item.quantidade - quantidade_antes:
        raise ValidationError("Quantidade maior que o saldo disponível para devolução.")
    forma = FormaPagamento.objects.filter(pk=forma_id, ativa=True).first()
    if not forma or forma.promissoria:
        raise ValidationError("Selecione uma forma de estorno ativa.")
    # Última devolução absorve eventual centavo de arredondamento.
    valor = (item.total * qtd / item.quantidade).quantize(Decimal(".01"), rounding=ROUND_DOWN)
    if quantidade_antes + qtd == item.quantidade:
        valor = item.total - sum(d.valor for d in anteriores)
    notas = list(NotaPromissoria.objects.select_for_update().filter(pagamento__venda=venda).order_by("pk"))
    restante = valor
    abatimentos = []
    for nota in notas:
        abater = min(nota.saldo, restante)
        if abater > 0:
            abatimentos.append((nota, abater))
            restante -= abater
    if forma.dinheiro and restante > caixa.saldo_esperado:
        raise ValidationError("Dinheiro insuficiente no caixa para esta devolução.")
    peca = Peca.objects.select_for_update().get(pk=item.peca_id)
    peca.quantidade += qtd
    if peca.status == Peca.Status.VENDIDA:
        peca.status = Peca.Status.DISPONIVEL
    peca.save(update_fields=["quantidade", "status", "atualizado_em"])
    devolucao = Devolucao.objects.create(chave=chave, item=item, operador=usuario, quantidade=qtd,
        valor=valor, abatimento_promissoria=valor-restante, motivo=motivo.strip(), forma=forma, forma_nome=forma.nome, dinheiro=forma.dinheiro, caixa=caixa)
    for nota, abater in abatimentos:
        MovimentoPromissoria.objects.create(nota=nota, operador=usuario, caixa=caixa, tipo="abatido", valor=abater, motivo=f"Devolução {devolucao.pk}")
    if restante:
        MovimentoCaixa.objects.create(sessao=caixa, operador=usuario, tipo="estorno", venda=venda,
            valor=-restante, afeta_saldo=forma.dinheiro, descricao=f"Devolução {venda.codigo} · {forma.nome}")
    venda.status = "devolvida" if all(i.quantidade_restante == 0 for i in venda.itens.prefetch_related("devolucoes")) else "parcial"
    venda.save(update_fields=["status"])
    registrar(usuario, "venda.devolucao", venda.codigo, item=item.pk, quantidade=qtd, valor=str(valor), motivo=motivo)
    return devolucao


@transaction.atomic
def receber_nota(usuario, nota_id, valor, forma_id, chave):
    exigir(usuario, "vendas.receber_promissoria")
    caixa = caixa_aberto(usuario)
    referencia = NotaPromissoria.objects.get(pk=nota_id)
    venda = Venda.objects.select_for_update().get(pk=referencia.pagamento.venda_id)
    nota = NotaPromissoria.objects.select_for_update().get(pk=nota_id)
    anterior = MovimentoPromissoria.objects.filter(chave=chave).first()
    if anterior:
        if anterior.nota_id != nota.pk or anterior.operador_id != usuario.pk:
            raise PermissionDenied
        return anterior
    forma = FormaPagamento.objects.filter(pk=forma_id, ativa=True, promissoria=False).first()
    valor = dinheiro(valor)
    if venda.status in ["cancelada", "devolvida"] or not forma or valor <= 0 or valor > nota.saldo:
        raise ValidationError("Confira o saldo da nota e a forma de recebimento. O valor não pode exceder o saldo a receber.")
    movimento = MovimentoPromissoria.objects.create(chave=chave, nota=nota, caixa=caixa, operador=usuario,
        tipo="recebido", valor=valor, forma=forma, forma_nome=forma.nome, dinheiro=forma.dinheiro)
    MovimentoCaixa.objects.create(sessao=caixa, operador=usuario, tipo="venda", venda=venda, valor=valor,
        afeta_saldo=forma.dinheiro, descricao=f"Recebimento {nota.codigo} · {forma.nome}")
    registrar(usuario, "promissoria.recebida", venda.codigo, nota=nota.codigo, valor=str(valor))
    return movimento


@transaction.atomic
def corrigir(usuario, venda_id, chave, carrinho, pagamentos, motivo, desconto=0, cliente_id=None, dados_nota=None):
    exigir(usuario, "vendas.editar_venda")
    caixa_aberto(usuario)
    original = Venda.objects.select_for_update().get(pk=venda_id)
    existente = Venda.objects.filter(chave=chave, substitui=original).first()
    if existente:
        if existente.vendedor_id != usuario.pk:
            raise PermissionDenied
        return existente
    if original.status != "concluida" or not motivo.strip():
        raise ValidationError("Somente vendas concluídas sem devoluções podem ser editadas. Informe o motivo.")
    if Venda.objects.filter(chave=chave).exists():
        raise ValidationError("Identificador já utilizado. Reabra a edição da venda.")
    ids = set(original.itens.values_list("peca_id", flat=True)) | {int(pk) for pk in carrinho}
    list(Peca.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    cancelar(usuario, original.pk, f"Edição: {motivo}")
    nova = finalizar(usuario, chave, carrinho, pagamentos, desconto, cliente_id, dados_nota,
        precos_correcao={pk: dados["preco"] for pk, dados in carrinho.items()})
    nova.substitui = original
    nova.save(update_fields=["substitui"])
    registrar(usuario, "venda.corrigida", original.codigo, nova=nova.codigo, motivo=motivo)
    registrar(usuario, "venda.substituicao", nova.codigo, anterior=original.codigo, motivo=motivo)
    return nova
