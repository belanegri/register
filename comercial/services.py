import uuid
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from caixa.services import exigir, caixa_aberto, dinheiro
from caixa.models import MovimentoCaixa
from core.auditoria import registrar
from vendas.models import FormaPagamento
from .models import Documento, ItemDocumento, ContaReceber, Recebimento


@transaction.atomic
def registrar_venda_os(usuario, pk):
    """Registra uma nova OS uma única vez, sem presumir recebimento."""
    exigir(usuario, 'comercial.add_documento')
    doc = Documento.objects.select_for_update().get(pk=pk)
    if doc.tipo != 'os' or doc.status in ['cancelada', 'convertido']:
        raise ValidationError('A ordem deve estar ativa para registrar a venda.')
    if doc.venda_id:
        return doc.venda
    from vendas.services import finalizar
    carrinho = {}
    for item in doc.itens.all():
        chave = str(item.peca_id) if item.peca_id else f's:{item.servico_id}'
        if chave in carrinho:
            raise ValidationError('Unifique os itens repetidos antes de salvar.')
        carrinho[chave] = {'quantidade': item.quantidade, 'preco': str(item.preco), 'preco_personalizado': True}
    venda = finalizar(usuario, uuid.uuid4(), carrinho, [], doc.desconto, doc.cliente_id,
                      pendente=doc.primeiro_vencimento or timezone.localdate())
    doc.venda = venda
    doc.save(update_fields=['venda', 'atualizado_em'])
    conta = venda.conta_receber
    conta.os = doc
    conta.origem = 'Ordem de serviço'
    conta.descricao = f'{doc.codigo} · {venda.codigo}'
    conta.save(update_fields=['os', 'origem', 'descricao'])
    registrar(usuario, 'os.venda_registrada', doc.codigo, venda=venda.codigo)
    return venda


@transaction.atomic
def converter(usuario, pk, destino, confirmado=False, pagamentos=None, vencimento=None, dados_nota=None):
    exigir(usuario, 'comercial.converter_documento')
    if not confirmado:
        raise ValidationError('Confirme explicitamente a conversão.')
    doc = Documento.objects.select_for_update().get(pk=pk)
    if doc.status in ['convertido','cancelada','recusado','vencido'] or doc.venda_id or Documento.objects.filter(origem=doc).exists():
        raise ValidationError('Documento já convertido ou indisponível para conversão.')
    if doc.tipo == 'orcamento' and doc.validade and doc.validade < timezone.localdate():
        raise ValidationError('Orçamento vencido. Revise sua validade antes de converter.')
    itens = list(doc.itens.select_related('peca','servico'))
    if not itens or doc.total <= 0:
        raise ValidationError('Adicione itens e confira o total antes da conversão.')
    if destino == 'os' and doc.tipo == 'orcamento':
        campos = ['cliente_id','veiculo','placa','ano','km','combustivel','observacoes','desconto','condicoes', 'forma_pagamento_id', 'condicao_pagamento', 'parcelas', 'primeiro_vencimento']
        novo = Documento.objects.create(tipo='os',status='aberta',origem=doc,criado_por=usuario,**{c:getattr(doc,c) for c in campos})
        ItemDocumento.objects.bulk_create([ItemDocumento(documento=novo,peca_id=i.peca_id,servico_id=i.servico_id,descricao=i.descricao,quantidade=i.quantidade,preco=i.preco) for i in itens])
        novo.venda = registrar_venda_os(usuario, novo.pk)
    elif destino == 'venda':
        from vendas.services import finalizar
        carrinho = {}
        for i in itens:
            chave = str(i.peca_id) if i.peca_id else f's:{i.servico_id}'
            if chave in carrinho:
                raise ValidationError('Unifique os itens repetidos antes de converter.')
            carrinho[chave] = {'quantidade':i.quantidade,'preco':str(i.preco),'preco_personalizado':True}
        novo = finalizar(usuario,uuid.uuid4(),carrinho,pagamentos or [],doc.desconto,doc.cliente_id,dados_nota,pendente=vencimento)
        doc.venda = novo
        if hasattr(novo,'conta_receber') and doc.tipo == 'os':
            novo.conta_receber.os = doc
            novo.conta_receber.save(update_fields=['os'])
    else:
        raise ValidationError('Conversão inválida.')
    doc.status = 'convertido'
    doc.save(update_fields=['status','venda','atualizado_em'])
    registrar(usuario,'documento.convertido',doc.codigo,destino=str(novo))
    return novo


@transaction.atomic
def receber(usuario, pk, valor, forma_id, chave):
    exigir(usuario,'comercial.receber_conta')
    caixa = caixa_aberto(usuario)
    conta = ContaReceber.objects.select_for_update().get(pk=pk)
    anterior = Recebimento.objects.filter(chave=chave).first()
    if anterior:
        if anterior.conta_id != conta.pk or anterior.operador_id != usuario.pk:
            raise PermissionDenied
        return anterior
    forma = FormaPagamento.objects.filter(pk=forma_id,ativa=True,promissoria=False).first()
    valor = dinheiro(valor)
    if conta.cancelada or not forma or valor <= 0 or valor > conta.saldo:
        raise ValidationError('Confira a situação da conta, o saldo e a forma de pagamento.')
    movimento = MovimentoCaixa.objects.create(sessao=caixa,operador=usuario,tipo='venda',valor=valor,afeta_saldo=forma.dinheiro,venda=conta.venda,descricao=f'Recebimento conta #{conta.pk} · {forma.nome}')
    resultado = Recebimento.objects.create(conta=conta,chave=chave,valor=valor,forma=forma,forma_nome=forma.nome,operador=usuario,movimento=movimento)
    registrar(usuario,'conta.recebida',str(conta.pk),valor=str(valor))
    return resultado
