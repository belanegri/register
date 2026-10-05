from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from . import services
from .forms import ConfiguracaoForm, SolicitacaoForm, JustificativaForm, InutilizacaoForm, ProdutoForm, ServicoForm, SequenciaForm
from .models import ConfiguracaoFiscal, DocumentoFiscal, EventoFiscal, ParametroProduto, ParametroServico, SequenciaFiscal, Status
from .seguranca import ErroFiscal


def contexto(**dados):
    return {'fiscal_habilitado':settings.FISCAL_ENABLED, **dados}


@login_required
@permission_required('fiscal.consultar_fiscal',raise_exception=True)
def lista(request, modelo=None, secao=None):
    qs=DocumentoFiscal.objects.select_related('venda','ordem_servico').all()
    if modelo:qs=qs.filter(modelo=modelo)
    if secao=='pendentes':qs=qs.exclude(status__in=[Status.AUTORIZADA,Status.CANCELADA])
    if request.GET.get('status') in Status.values:qs=qs.filter(status=request.GET['status'])
    return render(request,'fiscal/lista.html',contexto(pagina=Paginator(qs,30).get_page(request.GET.get('page')),secao=secao,modelo=modelo,status_opcoes=Status.choices))


@login_required
@permission_required('fiscal.consultar_fiscal',raise_exception=True)
def detalhe(request, pk):
    doc=get_object_or_404(DocumentoFiscal.objects.select_related('venda','ordem_servico','configuracao'),pk=pk)
    return render(request,'fiscal/detalhe.html',contexto(documento=doc,itens=doc.snapshot.get('itens',[])))


@login_required
@permission_required('fiscal.emitir_fiscal',raise_exception=True)
def solicitar(request):
    form=SolicitacaoForm(request.POST or None,initial={'venda':request.GET.get('venda'),'ordem_servico':request.GET.get('os')})
    if request.method=='POST' and form.is_valid():
        try:
            d=form.cleaned_data
            doc=services.solicitar(request.user,venda_id=d.get('venda'),os_id=d.get('ordem_servico'),modelo=d.get('modelo') or None,serie=d['serie'],destinatario=d.get('destinatario'))
            return redirect('fiscal:detalhe',pk=doc.pk)
        except ErroFiscal as erro:form.add_error(None,str(erro))
        except Exception as erro:
            from vendas.models import Venda
            from comercial.models import Documento
            if isinstance(erro,(Venda.DoesNotExist,Documento.DoesNotExist)):form.add_error(None,'Venda/OS não encontrada.')
            else:raise
    return render(request,'fiscal/form.html',contexto(form=form,titulo='Solicitar documento fiscal'))


@login_required
@require_POST
def acao(request, pk, operacao):
    get_object_or_404(DocumentoFiscal,pk=pk)
    try:
        if operacao=='transmitir':services.transmitir(request.user,pk)
        elif operacao=='consultar':services.consultar(request.user,pk)
        elif operacao=='atualizar':services.atualizar_parametros(request.user,pk)
        else:raise Http404
    except ErroFiscal as erro:messages.error(request,str(erro))
    return redirect('fiscal:detalhe',pk=pk)


@login_required
@permission_required('fiscal.cancelar_fiscal',raise_exception=True)
def cancelar(request,pk):
    get_object_or_404(DocumentoFiscal,pk=pk)
    form=JustificativaForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        try:
            ev=services.solicitar_cancelamento(request.user,pk,form.cleaned_data['justificativa'])
            return redirect('fiscal:evento',pk=ev.pk)
        except ErroFiscal as erro:form.add_error(None,str(erro))
    return render(request,'fiscal/form.html',contexto(form=form,titulo='Solicitar cancelamento fiscal'))


@login_required
@permission_required('fiscal.inutilizar_fiscal',raise_exception=True)
def inutilizar(request):
    form=InutilizacaoForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        try:
            d=form.cleaned_data
            ev=services.solicitar_inutilizacao(request.user,d['modelo'],d['serie'],d['numero_inicial'],d['numero_final'],d['ano'],d['justificativa'])
            return redirect('fiscal:evento',pk=ev.pk)
        except ErroFiscal as erro:form.add_error(None,str(erro))
    return render(request,'fiscal/form.html',contexto(form=form,titulo='Inutilizar numeração fiscal'))


@login_required
@permission_required('fiscal.consultar_fiscal',raise_exception=True)
def eventos(request):
    return render(request,'fiscal/eventos.html',contexto(pagina=Paginator(EventoFiscal.objects.select_related('documento'),30).get_page(request.GET.get('page'))))


@login_required
@permission_required('fiscal.consultar_fiscal',raise_exception=True)
def evento(request,pk):
    return render(request,'fiscal/evento.html',contexto(evento=get_object_or_404(EventoFiscal,pk=pk)))


@login_required
@require_POST
def transmitir_evento(request,pk):
    get_object_or_404(EventoFiscal,pk=pk)
    try:services.transmitir_evento(request.user,pk)
    except ErroFiscal as erro:messages.error(request,str(erro))
    return redirect('fiscal:evento',pk=pk)


@login_required
@require_POST
def consultar_evento(request,pk):
    get_object_or_404(EventoFiscal,pk=pk)
    try:services.consultar_evento(request.user,pk)
    except ErroFiscal as erro:messages.error(request,str(erro))
    return redirect('fiscal:evento',pk=pk)


@sensitive_post_parameters('senha_a1','csc','certificado_a1')
@login_required
@permission_required('fiscal.configurar_fiscal',raise_exception=True)
def configuracao(request):
    config=ConfiguracaoFiscal.objects.filter(pk=1).first() or ConfiguracaoFiscal()
    form=ConfiguracaoForm(request.POST or None,request.FILES or None,instance=config)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            form.save()
        messages.success(request,'Configuração fiscal salva nesta instalação.')
        return redirect('fiscal:configuracao')
    return render(request,'fiscal/configuracao.html',contexto(form=form,config=config,sequencias=SequenciaFiscal.objects.all()))


@login_required
@permission_required('fiscal.configurar_fiscal',raise_exception=True)
def parametros(request,tipo,pk=None):
    if tipo not in ('produtos','servicos'):raise Http404
    model,form_class=(ParametroProduto,ProdutoForm) if tipo=='produtos' else (ParametroServico,ServicoForm)
    instance=get_object_or_404(model,pk=pk) if pk else None
    form=form_class(request.POST or None,instance=instance)
    if request.method=='POST' and form.is_valid():
        form.save();messages.success(request,'Parâmetros fiscais salvos. O cadastro comercial foi preservado.')
        return redirect('fiscal:parametros',tipo=tipo)
    return render(request,'fiscal/parametros.html',contexto(form=form,tipo=tipo,parametros=model.objects.all()))


@login_required
@permission_required('fiscal.configurar_fiscal',raise_exception=True)
def sequencia(request):
    get_object_or_404(ConfiguracaoFiscal,pk=1)
    form=SequenciaForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        try:form.save();return redirect('fiscal:configuracao')
        except ErroFiscal as erro:form.add_error(None,str(erro))
    return render(request,'fiscal/form.html',contexto(form=form,titulo='Série e numeração fiscal'))


@login_required
@permission_required('fiscal.consultar_fiscal',raise_exception=True)
def xml(request,pk):
    doc=get_object_or_404(DocumentoFiscal,pk=pk)
    dados=doc.xml_autorizado or doc.xml_assinado
    if not dados:raise Http404('XML ainda não preparado.')
    response=HttpResponse(dados,content_type='application/xml; charset=utf-8')
    response['Content-Disposition']=f'attachment; filename="fiscal-{doc.modelo}-{doc.serie}-{doc.numero}.xml"'
    response['Cache-Control']='private, no-store'
    return response


@login_required
@permission_required('fiscal.consultar_fiscal',raise_exception=True)
def auxiliar(request,pk):
    from .documentos import gerar_auxiliar
    doc=get_object_or_404(DocumentoFiscal,pk=pk)
    dados=gerar_auxiliar(doc)
    endpoint=doc.configuracao.endpoints.get(doc.ambiente,{}).get('nfse',{}).get('danfse') if doc.modelo=='nfse' else None
    if endpoint and doc.status==Status.AUTORIZADA:
        from .provedores import requisitar
        try:
            services.habilitado(doc.configuracao,doc.ambiente)
            dados=requisitar(doc.configuracao,doc.ambiente,endpoint.rstrip('/')+'/'+doc.chave_acesso,binario=True)
            if not dados.startswith(b'%PDF'):raise ErroFiscal('DANFSe oficial ainda não disponível.')
        except ErroFiscal as erro:
            messages.error(request,str(erro));return redirect('fiscal:detalhe',pk=pk)
    response=HttpResponse(dados,content_type='application/pdf')
    response['Content-Disposition']=f'inline; filename="documento-fiscal-{doc.pk}.pdf"'
    response['Cache-Control']='private, no-store'
    return response


@login_required
@permission_required('fiscal.emitir_fiscal',raise_exception=True)
def contingencia(request,pk):
    get_object_or_404(DocumentoFiscal,pk=pk)
    form=JustificativaForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        try:
            services.ativar_contingencia(request.user,pk,form.cleaned_data['justificativa'])
            return redirect('fiscal:detalhe',pk=pk)
        except ErroFiscal as erro:form.add_error(None,str(erro))
    return render(request,'fiscal/form.html',contexto(form=form,titulo='Preparar contingência offline NFC-e'))
