from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

from . import services
from .forms import ConfiguracaoForm, SolicitacaoForm, JustificativaForm, InutilizacaoForm, ProdutoForm, ProdutoPadraoForm, ServicoForm, SequenciaForm
from .models import ConfiguracaoFiscal, DocumentoFiscal, EventoFiscal, ParametroProduto, ParametroServico, SequenciaFiscal, Status, Operacao
from .seguranca import ErroFiscal


def contexto(**dados):
    config=ConfiguracaoFiscal.objects.filter(pk=1).first()
    return {'fiscal_habilitado':bool(settings.FISCAL_ENABLED and config and config.ativa),'fiscal_ambiente':config.ambiente if config else '', 'fiscal_uf':config.uf if config else '', **dados}


@login_required
@permission_required('fiscal.consultar_fiscal',raise_exception=True)
def lista(request, modelo=None, secao=None):
    qs=DocumentoFiscal.objects.select_related('venda','ordem_servico').all()
    from .models import RascunhoFiscal
    rascunhos=RascunhoFiscal.objects.filter(usuario=request.user,documento__isnull=True)
    rascunhos_total=rascunhos.count()
    from .painel import FiltroFiscalForm,resumo_painel
    painel=resumo_painel(qs)
    aba=request.GET.get('aba') or ('pendentes' if secao=='pendentes' else 'todas')
    if aba not in ('todas','preparacao','autorizadas','pendentes'):aba='todas'
    if aba=='preparacao':qs=qs.none()
    elif aba=='autorizadas':qs=qs.filter(status=Status.AUTORIZADA);rascunhos=rascunhos.none()
    elif aba=='pendentes':
        qs=qs.exclude(status__in=[Status.AUTORIZADA,Status.CANCELADA]);rascunhos=rascunhos.none()
    dados=request.GET.copy()
    if modelo and not dados.get('modelo'):dados['modelo']=modelo
    filtro=FiltroFiscalForm(dados)
    qs=filtro.aplicar(qs)
    rascunhos=filtro.aplicar_rascunhos(rascunhos)
    filtros=request.GET.copy();filtros.pop('page',None)
    abas=request.GET.copy()
    for campo in ('aba','page','rascunhos_page'):abas.pop(campo,None)
    drafts=Paginator(rascunhos,20).get_page(request.GET.get('rascunhos_page'))
    return render(request,'fiscal/lista.html',contexto(pagina=Paginator(qs,30).get_page(request.GET.get('page')),secao=secao,modelo=modelo,
        aba=aba,filtros_avancados=any(request.GET.get(k) for k in ('status','operacao','ambiente','modelo','data_inicio','data_fim')),abas_url=abas.urlencode(),filtro=filtro,painel=painel,rascunhos=drafts.object_list,rascunhos_pagina=drafts,rascunhos_total=rascunhos_total,filtros_url=filtros.urlencode()))


@login_required
@permission_required('fiscal.consultar_fiscal',raise_exception=True)
def detalhe(request, pk):
    doc=get_object_or_404(DocumentoFiscal.objects.select_related('venda','ordem_servico','configuracao'),pk=pk)
    from .painel import conferencia
    return render(request,'fiscal/detalhe.html',contexto(documento=doc,transmissao_liberada=bool(settings.FISCAL_ENABLED and doc.configuracao.ativa and (doc.ambiente=='homologacao' or (doc.modelo in ('55','nfse') and settings.FISCAL_ALLOW_PRODUCTION and doc.configuracao.homologacao_validada and doc.configuracao.producao_validada))),**conferencia(doc)))


@login_required
@permission_required('fiscal.emitir_fiscal',raise_exception=True)
def transporte(request,pk):
    from .transporte import TransporteForm,dados_iniciais,pode_editar_transporte,atualizar_transporte
    doc=get_object_or_404(DocumentoFiscal,pk=pk)
    if not pode_editar_transporte(doc):
        messages.error(request,'O transporte só pode ser editado antes da primeira transmissão da NF-e.')
        return redirect('fiscal:detalhe',pk=pk)
    form=TransporteForm(request.POST if request.method=='POST' else None,initial=dados_iniciais(doc),usuario=request.user)
    if request.method=='POST' and form.is_valid():
        try:
            atualizar_transporte(request.user,pk,form.cleaned_data['transporte'])
            messages.success(request,'Transporte salvo. O total e a numeração da nota foram preservados; nenhuma transmissão foi realizada.')
            return redirect('fiscal:detalhe',pk=pk)
        except ErroFiscal as erro:form.add_error(None,str(erro))
    return render(request,'fiscal/transporte_form.html',contexto(form=form,documento=doc))


@login_required
@permission_required('fiscal.emitir_fiscal',raise_exception=True)
def solicitar(request):
    from .rascunhos import carregar_dados, salvar_previa, vincular_documento
    dados=carregar_dados(request)
    operacao=dados.get('operacao') if dados else request.GET.get('operacao',Operacao.SAIDA)
    operacao=operacao or Operacao.SAIDA
    if operacao not in Operacao.values:raise Http404
    config=ConfiguracaoFiscal.objects.filter(pk=1).first()
    serie_padrao=config.serie_padrao if config else 1
    if operacao==Operacao.ENTRADA:
        from .entradas import EntradaForm, EntradaItensFormSet, NovaPecaEntradaForm, solicitar_entrada, previsualizar_entrada
        from django.core.exceptions import PermissionDenied
        if not request.user.has_perm('estoque.view_peca'):raise PermissionDenied
        form=EntradaForm(dados or None,initial={'serie':serie_padrao},usuario=request.user)
        itens=EntradaItensFormSet(dados or None,prefix='itens')
        if request.method=='POST' and request.POST.get('acao') in ('conferir','rascunho'):
            from .rascunhos import salvar_preparacao_entrada
            try:
                salvar_preparacao_entrada(request,form,itens,config)
                if request.POST.get('acao')=='rascunho':
                    messages.success(request,'Preparação de entrada salva. Retome o rascunho na Central fiscal.')
                    return redirect('fiscal:lista')
                if not form.is_valid() or not itens.is_valid():messages.warning(request,'Preparação salva como rascunho. Corrija os campos indicados para conferir a prévia.')
            except ErroFiscal as erro:form.add_error(None,str(erro))
        if request.method=='POST' and request.POST.get('acao')!='editar':
            form_valido=form.is_valid();itens_validos=itens.is_valid()
            if form_valido and itens_validos:
                try:
                    d=form.cleaned_data
                    previa=request.POST.get('acao')=='conferir'
                    funcao=previsualizar_entrada if previa else solicitar_entrada
                    doc=funcao(request.user,chave=d['chave'],fornecedor=form.fornecedor(),
                        itens=[f.cleaned_data for f in itens if f.cleaned_data and not f.cleaned_data.get('DELETE')],
                        serie=d['serie'],referencia=d['referencia'],natureza_operacao=d['natureza_operacao'],cfop=d['cfop'],ind_final=d.get('consumidor_final') or '0',valor_frete=d['valor_frete'],transporte=d.get('transporte'),observacao_final=d.get('observacao_final',''))
                    if previa:
                        rascunho=salvar_previa(request,doc,form,itens)
                        from .painel import conferencia
                        return render(request,'fiscal/detalhe.html',contexto(documento=doc,previsualizacao=True,rascunho=rascunho,form=form,itens_formset=itens,**conferencia(doc)))
                    vincular_documento(request,form,doc)
                    messages.success(request,'Nota salva na Central fiscal. Confira e confirme a transmissão para solicitar autorização da SEFAZ.')
                    return redirect('fiscal:detalhe',pk=doc.pk)
                except ErroFiscal as erro:form.add_error(None,str(erro))
        return render(request,'fiscal/entrada.html',contexto(form=form,itens=itens,nova_peca_form=NovaPecaEntradaForm(prefix='nova'),operacao=operacao,titulo='Preparar NF-e de entrada'))
    form=SolicitacaoForm(dados or None,usuario=request.user,modelo_padrao=config.modelo_mercadorias if config else '55',initial={'serie':serie_padrao,'venda':request.GET.get('venda'),'ordem_servico':request.GET.get('os')})
    if request.method=='POST' and request.POST.get('acao') in ('conferir','rascunho'):
        from .rascunhos import salvar_preparacao
        try:
            rascunho=salvar_preparacao(request,form,config)
            if request.POST.get('acao')=='rascunho':
                messages.success(request,'Preparação salva. Retome o rascunho na Central fiscal para completar e conferir os valores.')
                return redirect('fiscal:lista')
            if form.errors:
                messages.warning(request,'Preparação salva como rascunho. Corrija os campos indicados para conferir a prévia.')
        except ErroFiscal as erro:form.add_error(None,str(erro))
    if request.method=='POST' and request.POST.get('acao')!='editar' and form.is_valid():
        try:
            d=form.cleaned_data
            previa=request.POST.get('acao')=='conferir'
            from .preparacao import previsualizar_saida
            funcao=previsualizar_saida if previa else services.solicitar
            doc=funcao(request.user,venda_id=d.get('venda'),os_id=d.get('ordem_servico'),modelo=d.get('modelo') or None,
                serie=d['serie'],destinatario=d.get('destinatario'),cfop=d['cfop'],natureza_operacao=d['natureza_operacao'],aliquota_icms=d['aliquota_icms'],ind_final=d.get('consumidor_final') or '1',valor_frete=d['valor_frete'],difal=d.get('difal'),transporte=d.get('transporte'),observacao_final=d.get('observacao_final',''))
            if previa:
                rascunho=salvar_previa(request,doc,form)
                from .painel import conferencia
                return render(request,'fiscal/detalhe.html',contexto(documento=doc,previsualizacao=True,rascunho=rascunho,form=form,**conferencia(doc)))
            vincular_documento(request,form,doc)
            messages.success(request,'Nota salva na Central fiscal. Confira e confirme a transmissão para solicitar autorização da SEFAZ.')
            return redirect('fiscal:detalhe',pk=doc.pk)
        except ErroFiscal as erro:
            form.add_error(None,str(erro))
            if request.POST.get('acao')=='conferir':messages.warning(request,'A prévia não pôde ser calculada. O preenchimento permanece salvo no rascunho.')
        except Exception as erro:
            from vendas.models import Venda
            from comercial.models import Documento
            if isinstance(erro,(Venda.DoesNotExist,Documento.DoesNotExist)):form.add_error(None,'Venda/OS não encontrada.')
            else:raise
    return render(request,'fiscal/form.html',contexto(form=form,operacao=operacao,preparacao=True,after_first_section_template='fiscal/origem_conferencia.html',titulo='Preparar nota fiscal de saída'))


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
    ev=get_object_or_404(EventoFiscal,pk=pk)
    permissao={'cancelamento':'cancelar_fiscal','correcao':'emitir_fiscal','inutilizacao':'inutilizar_fiscal'}.get(ev.tipo)
    pode_transmitir=bool(permissao and request.user.has_perm('fiscal.'+permissao) and ev.status in (Status.PENDENTE,Status.REJEITADA) and ev.codigo_resposta not in ('136','573'))
    return render(request,'fiscal/evento.html',contexto(evento=ev,pode_transmitir_evento=pode_transmitir))


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


@never_cache
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
@require_POST
def testar_conexao_sefaz(request):
    from .sefaz_sp import testar_conexao
    config=ConfiguracaoFiscal.objects.filter(pk=1).first()
    resultado=testar_conexao(config,request.POST.get('modelo','55'))
    nivel=messages.SUCCESS if resultado.status=='conectado' else messages.ERROR
    messages.add_message(request,nivel,resultado.mensagem)
    return redirect('fiscal:configuracao')


@login_required
@permission_required('fiscal.configurar_fiscal',raise_exception=True)
def parametros(request,tipo,pk=None):
    if tipo not in ('produtos','servicos'):raise Http404
    model,form_class=(ParametroProduto,ProdutoForm) if tipo=='produtos' else (ParametroServico,ServicoForm)
    instance=get_object_or_404(model,pk=pk) if pk else None
    peca_selecionada=None
    if tipo=='produtos' and pk is None and request.GET.get('individual')=='1' and request.GET.get('peca'):
        from estoque.models import Peca
        codigo=request.GET['peca']
        if not codigo.isascii() or not codigo.isdigit() or len(codigo)>18:raise Http404
        peca_selecionada=get_object_or_404(Peca,pk=int(codigo))
        instance=ParametroProduto.objects.filter(peca=peca_selecionada,operacao=request.GET.get('operacao',Operacao.SAIDA)).first()
    padrao = tipo == 'produtos' and ((instance is not None and instance.peca_id is None)
        or (pk is None and request.GET.get('individual') != '1'))
    operacao = (instance.operacao if instance else request.GET.get('operacao', Operacao.SAIDA)) if tipo == 'produtos' else Operacao.SAIDA
    if operacao not in Operacao.values:raise Http404
    if padrao:
        instance = instance or ParametroProduto.objects.filter(peca__isnull=True, operacao=operacao).first()
        form_class = ProdutoPadraoForm
    if tipo == 'produtos' and instance is None:
        padrao_existente=ParametroProduto.objects.filter(peca__isnull=True,operacao=operacao).first()
        valores={campo.name:getattr(padrao_existente,campo.name) for campo in ParametroProduto._meta.fields
            if campo.name not in ('id','peca','criado_em','atualizado_em','operacao','classificacao_conferida')} if padrao_existente else {}
        instance = ParametroProduto(operacao=operacao,peca=peca_selecionada,**valores)
    config=ConfiguracaoFiscal.objects.filter(pk=1).first() if tipo=='produtos' else None
    extras={'crt':config.crt if config else None} if tipo=='produtos' else {}
    form=form_class(request.POST or None,instance=instance,**extras)
    if request.method=='POST' and form.is_valid():
        form.save();messages.success(request,'Parâmetros fiscais salvos. O cadastro comercial foi preservado.')
        if tipo == 'produtos':
            from django.urls import reverse
            return redirect(reverse('fiscal:parametros',args=[tipo])+'?operacao='+operacao)
        return redirect('fiscal:parametros',tipo=tipo)
    registros = model.objects.filter(operacao=operacao) if tipo == 'produtos' else model.objects.all()
    return render(request,'fiscal/parametros.html',contexto(form=form,tipo=tipo,padrao=padrao,classificacao_individual=config.exigir_classificacao_individual if config else False,operacao=operacao,operacao_rotulo=Operacao(operacao).label,parametros=registros))


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
    try:
        dados=gerar_auxiliar(doc)
    except ErroFiscal as erro:
        messages.error(request,str(erro));return redirect('fiscal:detalhe',pk=pk)
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
    response['Content-Disposition']=f'inline; filename="danfe-{doc.serie}-{doc.numero}.pdf"' if doc.modelo=='55' else f'inline; filename="documento-fiscal-{doc.pk}.pdf"'
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


@never_cache
@login_required
@permission_required('fiscal.consultar_fiscal',raise_exception=True)
def compras(request):
    from .importacao import ImportacaoCompraForm, importar_compra
    from .models import NotaCompraImportada
    form=ImportacaoCompraForm(request.POST if request.method=='POST' else None, request.FILES if request.method=='POST' else None)
    if request.method=='POST':
        services.exigir(request.user,'emitir_fiscal')
        if form.is_valid():
            try:
                nota,criado=importar_compra(request.user,form.cleaned_data['arquivo'].read(5*1024*1024+1))
                messages.success(request,'XML de compra registrado.' if criado else 'Este XML já estava registrado. Nenhuma duplicação foi criada.')
                return redirect('fiscal:compra_detalhe',pk=nota.pk)
            except ErroFiscal as erro:form.add_error(None,str(erro))
    pagina=Paginator(NotaCompraImportada.objects.all(),30).get_page(request.GET.get('page'))
    return render(request,'fiscal/compras.html',contexto(form=form,pagina=pagina,operacao='0'))


@never_cache
@login_required
@permission_required('fiscal.consultar_fiscal',raise_exception=True)
def compra_detalhe(request,pk):
    from .models import NotaCompraImportada
    nota=get_object_or_404(NotaCompraImportada,pk=pk)
    return render(request,'fiscal/compra_detalhe.html',contexto(nota=nota))


@login_required
@permission_required('fiscal.consultar_fiscal',raise_exception=True)
def compra_xml(request,pk):
    from .models import NotaCompraImportada
    nota=get_object_or_404(NotaCompraImportada,pk=pk)
    response=HttpResponse(nota.xml,content_type='application/xml; charset=utf-8')
    response['Content-Disposition']=f'attachment; filename="compra-{nota.chave}.xml"'
    response['Cache-Control']='private, no-store'
    return response


@never_cache
@login_required
@permission_required('fiscal.emitir_fiscal',raise_exception=True)
def dados_origem(request):
    from django.http import JsonResponse
    from .preparacao import carregar_origem
    if request.method!='GET':return JsonResponse({'erro':'Use a consulta de origem.'},status=405)
    try:dados=carregar_origem(request.user,venda_id=request.GET.get('venda'),os_id=request.GET.get('os'))
    except ValueError as erro:return JsonResponse({'erro':str(erro)},status=400)
    return JsonResponse(dados)


@never_cache
@login_required
@permission_required('fiscal.configurar_fiscal',raise_exception=True)
def classificacao(request):
    from estoque.models import Peca
    from django.db.models import OuterRef,Subquery,Value,BooleanField,Q,Case,When,F
    from django.db.models.functions import Coalesce
    operacao=request.GET.get('operacao',Operacao.SAIDA)
    if operacao not in Operacao.values:raise Http404
    parametros=ParametroProduto.objects.filter(peca_id=OuterRef('pk'),operacao=operacao)
    cadastro=Q(classificacao_fiscal_no_estoque=True)|~Q(ncm='')|~Q(origem_fiscal='')|~Q(cest='')|Q(classificacao_fiscal_conferida=True)
    qs=Peca.objects.annotate(fiscal_pk=Subquery(parametros.values('pk')[:1]),
        ncm_fiscal=Case(When(cadastro,then=F('ncm')),default=Subquery(parametros.values('ncm')[:1])),
        origem_fiscal_lista=Case(When(cadastro,then=F('origem_fiscal')),default=Subquery(parametros.values('origem')[:1])),
        cest_fiscal=Case(When(cadastro,then=F('cest')),default=Subquery(parametros.values('cest')[:1])),
        fiscal_conferida=Case(When(cadastro,then=F('classificacao_fiscal_conferida')),default=Coalesce(Subquery(parametros.values('classificacao_conferida')[:1]),Value(False),output_field=BooleanField()))).order_by('-criado_em','-pk')
    q=request.GET.get('q','').strip()[:100]
    if q:qs=qs.filter(Q(codigo__icontains=q)|Q(nome__icontains=q))
    situacao=request.GET.get('situacao','pendentes')
    if situacao=='pendentes':qs=qs.filter(Q(fiscal_conferida=False)|Q(ncm_fiscal='')|Q(origem_fiscal_lista=''))
    elif situacao=='conferidas':qs=qs.filter(fiscal_conferida=True).exclude(ncm_fiscal='').exclude(origem_fiscal_lista='')
    filtros=request.GET.copy();filtros.pop('page',None)
    return render(request,'fiscal/classificacao.html',contexto(pagina=Paginator(qs,30).get_page(request.GET.get('page')),
        operacao=operacao,operacao_rotulo=Operacao(operacao).label,q=q,situacao=situacao,filtros_url=filtros.urlencode()))
@login_required
def consultar_cep(request):
    from django.core.exceptions import PermissionDenied
    from django.http import JsonResponse
    if not (request.user.has_perm('fiscal.emitir_fiscal') or request.user.has_perm('fiscal.configurar_fiscal')):raise PermissionDenied
    if request.method!='GET':return JsonResponse({'erro':'Use a consulta por GET.'},status=405)
    from .enderecos import consultar_cep as buscar
    try:return JsonResponse(buscar(request.GET.get('cep','')))
    except ErroFiscal as erro:return JsonResponse({'erro':str(erro)},status=400)
@login_required
@permission_required('fiscal.emitir_fiscal',raise_exception=True)
def carta_correcao(request,pk):
    from .forms import CartaCorrecaoForm
    doc=get_object_or_404(DocumentoFiscal,pk=pk)
    form=CartaCorrecaoForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        try:
            ev=services.solicitar_correcao(request.user,pk,form.cleaned_data['texto'],form.cleaned_data['chave'])
            return redirect('fiscal:evento',pk=ev.pk)
        except ErroFiscal as erro:form.add_error(None,str(erro))
    return render(request,'fiscal/form.html',contexto(form=form,titulo='Carta de Correção Eletrônica · '+str(doc)))


@login_required
@permission_required('fiscal.consultar_fiscal',raise_exception=True)
def evento_xml(request,pk):
    ev=get_object_or_404(EventoFiscal,pk=pk)
    xml=ev.xml_autorizado or ev.xml
    if not xml:raise Http404
    resposta=HttpResponse(xml,content_type='application/xml; charset=utf-8')
    resposta['Content-Disposition']=f'attachment; filename="evento-fiscal-{ev.pk}.xml"'
    resposta['Cache-Control']='private, no-store'
    return resposta


@login_required
@permission_required(('fiscal.emitir_fiscal', 'estoque.add_peca', 'estoque.view_peca'), raise_exception=True)
@require_POST
@transaction.atomic
def nova_peca_entrada(request):
    from django.http import JsonResponse
    from .entradas import NovaPecaEntradaForm
    from core.auditoria import registrar
    form = NovaPecaEntradaForm(request.POST, prefix='nova')
    if not form.is_valid():
        return JsonResponse({'erros': form.errors.get_json_data()}, status=400)
    peca = form.save()
    registrar(request.user, 'peca.cadastrada_entrada', peca.codigo, quantidade=0)
    return JsonResponse({'id': peca.pk, 'rotulo': str(peca)}, status=201)


@login_required
@permission_required(('fiscal.emitir_fiscal', 'estoque.view_peca'), raise_exception=True)
def editar_entrada(request, pk):
    from .edicao import pode_editar_entrada, dados_iniciais_entrada, montar_correcao_entrada, corrigir_entrada
    from .entradas import EntradaForm, EntradaItensFormSet, NovaPecaEntradaForm
    doc = get_object_or_404(DocumentoFiscal.objects.select_related('configuracao'), pk=pk)
    if not pode_editar_entrada(doc):
        messages.error(request, 'Esta nota não está disponível para edição. Confira sua situação antes de corrigir.')
        return redirect('fiscal:detalhe', pk=pk)
    inicial, linhas = dados_iniciais_entrada(doc)
    form = EntradaForm(request.POST if request.method == 'POST' else None, initial=inicial,usuario=request.user)
    form.fields.pop('rascunho')
    form.fields['versao'].required = True
    form.fields['serie'].disabled = True
    form.fields['chave'].disabled = True
    itens = EntradaItensFormSet(request.POST if request.method == 'POST' else None, initial=linhas, prefix='itens')
    previa = None
    if request.method == 'POST':
        form_valido = form.is_valid(); itens_validos = itens.is_valid()
        if form_valido and itens_validos:
            try:
                d = form.cleaned_data
                dados = dict(versao=d['versao'], fornecedor=form.fornecedor(),
                    itens=[f.cleaned_data for f in itens if f.cleaned_data and not f.cleaned_data.get('DELETE')],
                    referencia=d['referencia'], natureza_operacao=d['natureza_operacao'], cfop=d['cfop'],
                    ind_final=d.get('consumidor_final') or '0', valor_frete=d['valor_frete'], transporte=d.get('transporte'),observacao_final=d.get('observacao_final',''))
                if request.POST.get('acao') == 'salvar':
                    corrigir_entrada(request.user, pk, **dados)
                    messages.success(request, 'Alterações salvas. Série e número preservados. Confira os dados antes de reenviar à SEFAZ.')
                    return redirect('fiscal:detalhe', pk=pk)
                if request.POST.get('acao') == 'conferir':
                    snapshot, total = montar_correcao_entrada(doc, **dados)
                    previa = dict(snapshot=snapshot, total=total)
                else:
                    form.add_error(None, 'Escolha conferir ou salvar as alterações.')
            except ErroFiscal as erro:
                form.add_error(None, str(erro))
    return render(request, 'fiscal/entrada.html', contexto(form=form, itens=itens,
        nova_peca_form=NovaPecaEntradaForm(prefix='nova'), operacao='0', edicao=True,
        documento=doc, previa_edicao=previa, ultima_rejeicao=doc.tentativas.filter(operacao='emitir').exclude(codigo='').order_by('-pk').first(), titulo='Editar NF-e de entrada'))


@login_required
@permission_required('fiscal.emitir_fiscal', raise_exception=True)
def observacao(request, pk):
    from .observacoes import ObservacaoForm, pode_editar_observacao, atualizar_observacao
    doc = get_object_or_404(DocumentoFiscal, pk=pk)
    if not pode_editar_observacao(doc):
        messages.error(request, 'A observação desta nota não está disponível para edição.')
        return redirect('fiscal:detalhe', pk=pk)
    form = ObservacaoForm(request.POST if request.method == 'POST' else None,
        initial={'observacao_final': doc.snapshot.get('observacao_final',''), 'versao': doc.atualizado_em.isoformat()})
    if request.method == 'POST' and form.is_valid():
        try:
            atualizar_observacao(request.user, pk, form.cleaned_data['observacao_final'], form.cleaned_data['versao'])
            messages.success(request, 'Observação final salva. Nenhuma transmissão foi realizada.')
            return redirect('fiscal:detalhe', pk=pk)
        except ErroFiscal as erro:
            form.add_error('observacao_final', str(erro))
    return render(request, 'fiscal/form.html', contexto(form=form, titulo='Observação final · '+str(doc)))


@login_required
@permission_required('fiscal.configurar_fiscal',raise_exception=True)
def ajustes(request):
    return render(request,'fiscal/ajustes.html',contexto(config=ConfiguracaoFiscal.objects.filter(pk=1).first()))


@login_required
@permission_required('fiscal.emitir_fiscal',raise_exception=True)
def preparar(request):
    return render(request,'fiscal/preparar.html',contexto())
