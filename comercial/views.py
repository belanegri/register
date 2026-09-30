import uuid
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Sum, Value, DecimalField, F
from django.db.models.functions import Coalesce
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .models import Servico, Documento, ContaReceber
from .forms import ServicoForm, DocumentoForm, ItensFormSet, ContaForm
from .services import converter, receber
from vendas.forms import CheckoutForm, PagamentosFormSet, ReceberNotaForm
from vendas.views import dados_promissoria


@login_required
@permission_required('comercial.view_servico',raise_exception=True)
def servicos(request):
    q = request.GET.get('q','')[:160]
    return render(request,'comercial/servicos.html',{'servicos':Servico.objects.filter(nome__icontains=q),'q':q})


@login_required
def servico_editar(request,pk=None):
    from caixa.services import exigir
    exigir(request.user,'comercial.change_servico' if pk else 'comercial.add_servico')
    instance = get_object_or_404(Servico,pk=pk) if pk else None
    form = ServicoForm(request.POST if request.method == "POST" else None,instance=instance)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('comercial:servicos')
    return render(request,'core/form.html',{'form':form,'titulo':'Serviço / Mão de obra'})


@login_required
@permission_required('comercial.view_documento',raise_exception=True)
def documentos(request,tipo):
    if tipo not in ['orcamento','os']: raise Http404
    qs = Documento.objects.filter(tipo=tipo).select_related('cliente')
    status = request.GET.get('status','')
    if status: qs = qs.filter(status=status)
    q = request.GET.get('q','')[:160]
    if q: qs = qs.filter(cliente__nome__icontains=q)
    return render(request,'comercial/lista.html',{'pagina':Paginator(qs,30).get_page(request.GET.get('page')),'tipo':tipo,'titulo':'Orçamentos' if tipo=='orcamento' else 'Ordens de serviço','q':q,'status':status,'estados':Documento.STATUS})


@login_required
@transaction.atomic
def documento_editar(request,tipo=None,pk=None):
    from caixa.services import exigir
    exigir(request.user,'comercial.change_documento' if pk else 'comercial.add_documento')
    doc = get_object_or_404(Documento.objects.select_for_update(),pk=pk) if pk else Documento(tipo=tipo,criado_por=request.user,status='rascunho' if tipo=='orcamento' else 'aberta')
    if doc.tipo not in ['orcamento','os']: raise Http404
    if doc.status == 'convertido':
        messages.error(request,'Documento convertido não pode ser editado.')
        return redirect('comercial:detalhe',pk=doc.pk)
    form = DocumentoForm(request.POST if request.method == "POST" else None,instance=doc)
    itens = ItensFormSet(request.POST if request.method == "POST" else None,instance=doc,prefix='itens')
    if request.method == 'POST':
        valido = form.is_valid()
        if valido and itens.is_valid():
            form.save()
            itens.save()
            return redirect('comercial:detalhe',pk=doc.pk)
    from estoque.models import Peca
    return render(request,'comercial/editar.html',{'form':form,'itens':itens,'doc':doc,'precos':{'peca':{str(p.pk):str(p.preco_venda) for p in Peca.objects.all()},'servico':{str(s.pk):str(s.valor_padrao) for s in Servico.objects.all()}}})


@login_required
@permission_required('comercial.view_documento',raise_exception=True)
def detalhe(request,pk):
    doc = get_object_or_404(Documento.objects.select_related('cliente','venda','origem').prefetch_related('itens'),pk=pk)
    return render(request,'comercial/detalhe.html',{'doc':doc,'ordem':Documento.objects.filter(origem=doc).first()})


@login_required
@permission_required('comercial.converter_documento',raise_exception=True)
def conversao(request,pk,destino):
    if destino not in ['venda','os']: raise Http404
    doc = get_object_or_404(Documento,pk=pk)
    form = CheckoutForm(request.POST if request.method == "POST" else None,initial={'chave':uuid.uuid4(),'cliente':doc.cliente_id,'desconto':doc.desconto})
    pagamentos = PagamentosFormSet(request.POST if request.method == "POST" else None,prefix='pag')
    if request.method == 'POST':
        try:
            if request.POST.get('confirmar') != 'sim':
                raise ValidationError('Marque a confirmação para converter.')
            if destino == 'os':
                novo = converter(request.user,pk,destino,True)
                return redirect('comercial:detalhe',pk=novo.pk)
            if form.is_valid() and (form.cleaned_data['a_prazo'] or pagamentos.is_valid()):
                valores = [] if form.cleaned_data['a_prazo'] else [{'forma':f.cleaned_data['forma'].pk,'valor':f.cleaned_data['valor']} for f in pagamentos if f.cleaned_data]
                novo = converter(request.user,pk,destino,True,pagamentos=valores,vencimento=form.cleaned_data['vencimento_conta'] if form.cleaned_data['a_prazo'] else None,dados_nota=dados_promissoria(form))
                return redirect('vendas:detalhe',pk=novo.pk)
        except ValidationError as e:
            form.add_error(None,e)
    return render(request,'comercial/converter.html',{'doc':doc,'destino':destino,'form':form,'pagamentos':pagamentos})


@login_required
@permission_required('comercial.view_documento',raise_exception=True)
def imprimir(request,pk,formato):
    from .pdf import gerar_pdf
    if formato not in ['a4','58']: raise Http404
    doc = get_object_or_404(Documento.objects.select_related('cliente').prefetch_related('itens'),pk=pk)
    response = HttpResponse(gerar_pdf(doc,termico=formato=='58'),content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{doc.codigo}-{formato}.pdf"'
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@permission_required('comercial.view_contareceber',raise_exception=True)
def contas(request):
    hoje = timezone.localdate()
    qs = ContaReceber.objects.select_related('cliente','venda','os').annotate(recebido=Coalesce(Sum('recebimentos__valor'),Value(Decimal('0')),output_field=DecimalField(max_digits=12,decimal_places=2)))
    status = request.GET.get('status','')
    if status == 'vencidas': qs=qs.filter(cancelada=False,vencimento__lt=hoje,recebido__lt=F('valor_original'))
    elif status == 'vencer': qs=qs.filter(cancelada=False,vencimento__gte=hoje,recebido__lt=F('valor_original'))
    elif status == 'recebidas': qs=qs.filter(cancelada=False,recebido=F('valor_original'))
    elif status == 'parciais': qs=qs.filter(cancelada=False,recebido__gt=0,recebido__lt=F('valor_original'))
    elif status == 'canceladas': qs=qs.filter(cancelada=True)
    from datetime import date
    for key,lookup in [('inicio','vencimento__gte'),('fim','vencimento__lte')]:
        try:
            if request.GET.get(key): qs=qs.filter(**{lookup:date.fromisoformat(request.GET[key])})
        except ValueError: messages.error(request,'Data inválida no filtro.')
    return render(request,'comercial/contas.html',{'pagina':Paginator(qs.order_by('vencimento','pk').prefetch_related('recebimentos'),30).get_page(request.GET.get('page')),'status':status,'recebidos':qs.aggregate(s=Sum('recebido'))['s'] or 0})


@login_required
@permission_required('comercial.add_contareceber',raise_exception=True)
def conta_nova(request):
    form = ContaForm(request.POST if request.method == "POST" else None)
    if request.method=='POST' and form.is_valid():
        conta=form.save()
        return redirect('comercial:conta',pk=conta.pk)
    return render(request,'core/form.html',{'form':form,'titulo':'Nova conta a receber'})


@login_required
@permission_required('comercial.view_contareceber',raise_exception=True)
def conta(request,pk):
    conta=get_object_or_404(ContaReceber.objects.select_related('cliente','venda','os').prefetch_related('recebimentos'),pk=pk)
    form=ReceberNotaForm(request.POST if request.method == "POST" else None,initial={'chave':uuid.uuid4(),'valor':conta.saldo})
    if request.method=='POST' and form.is_valid():
        try:
            receber(request.user,pk,form.cleaned_data['valor'],form.cleaned_data['forma'].pk,form.cleaned_data['chave'])
            return redirect('comercial:conta',pk=pk)
        except ValidationError as e: form.add_error(None,e)
    return render(request,'comercial/conta.html',{'conta':conta,'form':form})


@login_required
@permission_required('comercial.change_contareceber',raise_exception=True)
@transaction.atomic
def conta_cancelar(request,pk):
    from django.views.decorators.http import require_POST
    if request.method!='POST': return HttpResponse(status=405)
    conta=get_object_or_404(ContaReceber.objects.select_for_update(),pk=pk)
    if conta.venda_id or conta.valor_recebido:
        messages.error(request,'Conta vinculada à venda ou com recebimentos: preserve o histórico. Para venda sem recebimentos, use o cancelamento da venda.')
    elif request.POST.get('confirmar')=='sim':
        conta.cancelada=True
        conta.save(update_fields=['cancelada'])
    return redirect('comercial:conta',pk=pk)
