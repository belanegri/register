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
        campos = ['cliente_id','veiculo','placa','ano','km','combustivel','observacoes','desconto','condicoes']
        novo = Documento.objects.create(tipo='os',status='aberta',origem=doc,criado_por=usuario,**{c:getattr(doc,c) for c in campos})
        ItemDocumento.objects.bulk_create([ItemDocumento(documento=novo,peca_id=i.peca_id,servico_id=i.servico_id,descricao=i.descricao,quantidade=i.quantidade,preco=i.preco) for i in itens])
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
