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
    iniciar_parcelamento_os(conta, doc)
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
            iniciar_parcelamento_os(novo.conta_receber, doc)
    else:
        raise ValidationError('Conversão inválida.')
    doc.status = 'convertido'
    doc.save(update_fields=['status','venda','atualizado_em'])
    registrar(usuario,'documento.convertido',doc.codigo,destino=str(novo))
    return novo


def iniciar_parcelamento_os(conta, documento):
    """Utiliza a condição aprovada da OS, dentro da transação comercial existente."""
    if documento.condicao_pagamento != 'parcelado' or documento.parcelas < 2:
        return
    from core.parcelamento import planejar
    from .models import ParcelaReceber
    plano = planejar(conta.valor_original, conta.vencimento, documento.parcelas)
    forma = documento.forma_pagamento
    forma_id = forma.pk if forma and forma.ativa and not forma.promissoria else None
    ParcelaReceber.objects.bulk_create([ParcelaReceber(conta=conta, numero=i+1,
        vencimento=p['vencimento'], valor=p['valor'], forma_prevista_id=forma_id) for i,p in enumerate(plano)])


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
    proxima = next((p for p in conta.plano_recebimento if p['saldo'] > 0), None)
    if proxima:
        conta.vencimento = proxima['vencimento']
        conta.save(update_fields=['vencimento'])
    registrar(usuario,'conta.recebida',str(conta.pk),valor=str(valor))
    return resultado


@transaction.atomic
def salvar_plano_receber(usuario, conta, plano):
    from .models import ParcelaReceber
    from core.forms_parcelamento import validar_formas
    exigir(usuario, 'comercial.change_contareceber')
    conta = ContaReceber.objects.select_for_update().get(pk=conta.pk)
    if conta.cancelada or conta.recebimentos.exists():
        raise ValidationError('Contas canceladas ou com recebimentos mantêm o plano e o histórico financeiro.')
    if not plano or len(plano) > 120 or sum(p['valor'] for p in plano) != conta.valor_original:
        raise ValidationError('O plano deve fechar exatamente o valor original da conta.')
    validar_formas(plano)
    conta.parcelas_financeiras.all().delete()
    ParcelaReceber.objects.bulk_create([ParcelaReceber(conta=conta, numero=i+1,
        vencimento=p['vencimento'], valor=p['valor'], forma_prevista_id=p['forma_id']) for i, p in enumerate(plano)])
    conta.vencimento = plano[0]['vencimento']
    conta.save(update_fields=['vencimento'])
    registrar(usuario, 'conta.plano_receber', conta.codigo, parcelas=len(plano))
    return conta


@transaction.atomic
def criar_conta_receber(usuario, dados):
    from django.contrib.auth import get_user_model
    from .models import ParcelaReceber
    exigir(usuario, 'comercial.add_contareceber')
    get_user_model().objects.select_for_update().get(pk=usuario.pk)
    anterior = ContaReceber.objects.filter(lancamento_chave=dados['chave']).first()
    if anterior:
        if anterior.criado_por_id != usuario.pk:
            raise PermissionDenied
        return anterior
    conta = ContaReceber.objects.create(criado_por=usuario, lancamento_chave=dados['chave'],
        **{c: dados[c] for c in ['cliente', 'descricao', 'valor_original', 'vencimento', 'observacoes']})
    plano = dados['plano']
    from core.forms_parcelamento import validar_formas
    validar_formas(plano)
    if sum(p['valor'] for p in plano) != conta.valor_original:
        raise ValidationError('Confira o total do parcelamento.')
    ParcelaReceber.objects.bulk_create([ParcelaReceber(conta=conta, numero=i+1,
        vencimento=p['vencimento'], valor=p['valor'], forma_prevista_id=p['forma_id']) for i,p in enumerate(plano)])
    conta.vencimento = plano[0]['vencimento']
    conta.save(update_fields=['vencimento'])
    registrar(usuario, 'conta.receber_criada', conta.codigo, parcelas=len(plano), valor=str(conta.valor_original))
    return conta
