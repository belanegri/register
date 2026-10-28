from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from core.auditoria import registrar
from .models import Cliente
from .forms import ClienteForm


@login_required
@permission_required("clientes.view_cliente", raise_exception=True)
def lista(request):
    q = request.GET.get("q", "").strip()[:150]
    import re
    from django.db.models import F,Value
    from django.db.models.functions import Replace
    base=Cliente.objects.all()
    documento_busca=F("documento")
    for sinal in (".","/","-"," "):documento_busca=Replace(documento_busca,Value(sinal),Value(""))
    base=base.annotate(documento_busca=documento_busca)
    filtro_documento=Q()
    if q and re.fullmatch(r"[0-9.\s/()-]+",q):filtro_documento=Q(documento_busca__icontains=re.sub(r"[^0-9]","",q))
    clientes = base.filter(Q(nome__icontains=q) | Q(documento__icontains=q) | Q(telefone__icontains=q) | Q(nome_fantasia__icontains=q) | Q(contato__icontains=q) | filtro_documento)
    papel=request.GET.get('papel','')
    if papel in ('cliente','fornecedor','transportadora'):clientes=clientes.filter(**{'eh_'+papel:True})
    situacao=request.GET.get('situacao','ativos')
    if situacao=='ativos':clientes=clientes.filter(ativo=True)
    elif situacao=='inativos':clientes=clientes.filter(ativo=False)
    filtros=request.GET.copy();filtros.pop('page',None)
    return render(request, "clientes/lista.html", {"pagina": Paginator(clientes, 30).get_page(request.GET.get("page")), "q": q,"papel":papel,"situacao":situacao,"filtros_url":filtros.urlencode()})


@login_required
def editar(request, pk=None):
    from django.core.exceptions import PermissionDenied
    if not request.user.has_perm("clientes.change_cliente" if pk else "clientes.add_cliente"):
        raise PermissionDenied
    cliente = get_object_or_404(Cliente, pk=pk) if pk else None
    papel=request.GET.get('papel','')
    inicial={'eh_cliente':papel not in ('fornecedor','transportadora'),'eh_fornecedor':papel=='fornecedor','eh_transportadora':papel=='transportadora'} if cliente is None else {}
    form = ClienteForm(request.POST if request.method=='POST' else None, instance=cliente,initial=inicial)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            cliente = form.save()
            registrar(request.user, "cliente.alterado" if pk else "cliente.criado", f"Cliente {cliente.pk}", campos=form.changed_data)
        messages.success(request, "Cadastro salvo.")
        return redirect("clientes:detalhe", pk=cliente.pk)
    return render(request, "clientes/form.html", {"form": form, "cliente":cliente, "titulo": "Editar cadastro" if pk else "Nova pessoa ou empresa"})


@login_required
@permission_required("clientes.view_cliente", raise_exception=True)
def detalhe(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    vendas = cliente.vendas.select_related("vendedor")
    if not request.user.has_perm("vendas.ver_todas_vendas"):
        vendas = vendas.filter(vendedor=request.user)
    if not request.user.has_perm("vendas.view_venda"):
        vendas = vendas.none()
    from fiscal.models import DocumentoFiscal
    notas=DocumentoFiscal.objects.none()
    if request.user.has_perm('fiscal.consultar_fiscal'):
        vinculo=Q(snapshot__destinatario__cadastro_id=cliente.pk)|Q(snapshot__transporte__cadastro_id=cliente.pk)|Q(venda__cliente=cliente)|Q(ordem_servico__cliente=cliente)
        documento=cliente.dados_fiscais()['documento']
        if len(documento) in (11,14):vinculo|=Q(snapshot__destinatario__documento=documento)|Q(snapshot__transporte__documento=documento)
        notas=DocumentoFiscal.objects.filter(vinculo).distinct().order_by('-pk')[:20]
    return render(request, "clientes/detalhe.html", {"cliente": cliente, "vendas": vendas[:100],"notas":notas})


@login_required
@permission_required('clientes.view_cliente',raise_exception=True)
def dados_fiscais(request):
    from django.http import JsonResponse, Http404
    if request.method!='GET':return JsonResponse({'erro':'Use GET para consultar.'},status=405)
    papel=request.GET.get('papel','cliente')
    if papel not in ('cliente','fornecedor','transportadora'):return JsonResponse({'erro':'Perfil inválido.'},status=400)
    chave=request.GET.get('id','')
    if not chave.isascii() or not chave.isdigit() or len(chave)>18:raise Http404
    obj=get_object_or_404(Cliente,pk=int(chave),ativo=True,**{'eh_'+papel:True})
    return JsonResponse({'fiscal':obj.dados_fiscais(),'transporte':obj.dados_transporte(),'pendencias':obj.pendencias_fiscais})


@login_required
@permission_required('clientes.view_cliente',raise_exception=True)
def consultar_cep(request):
    from django.core.exceptions import PermissionDenied
    if not (request.user.has_perm('clientes.add_cliente') or request.user.has_perm('clientes.change_cliente')):raise PermissionDenied
    from django.http import JsonResponse
    from fiscal.enderecos import consultar_cep as buscar
    from fiscal.seguranca import ErroFiscal
    if request.method!='GET':return JsonResponse({'erro':'Use GET para consultar.'},status=405)
    try:return JsonResponse(buscar(request.GET.get('cep','')))
    except ErroFiscal as erro:return JsonResponse({'erro':str(erro)},status=400)
