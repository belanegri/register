from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, F
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from core.auditoria import registrar
from caixa.services import caixa_aberto, movimentar
from .models import ContaPagar, AnexoConta
from .forms import ContaForm, PagamentoForm, CancelamentoForm, AnexoForm, FiltroContaForm, EditarAnexoForm
from django.http import FileResponse, Http404
from django.views.decorators.http import require_POST
from .services import criar_contas, registrar_pagamento, adicionar_anexo


def contexto_formulario(form, conta=None):
    secoes = [
        ('identificacao', 'Identificação', 'expense', 'Dados para localizar e organizar esta despesa.',
         ['descricao', 'fornecedor', 'categoria', 'subcategoria', 'tipo_conta', 'centro_custo', 'numero_documento', 'competencia']),
        ('valores', 'Valores', 'wallet', 'O total é calculado pelos valores informados. Nenhum pagamento é registrado aqui.',
         ['valor_original', 'desconto', 'juros', 'multa', 'acrescimos']),
        ('datas', 'Datas', 'quote', 'Vencimento e programação são independentes da data em que o pagamento será realizado.',
         ['emissao', 'vencimento', 'data_programada']),
        ('pagamento', 'Pagamento', 'income', 'Defina a forma prevista. A baixa será feita em Registrar pagamento.',
         ['forma_prevista', 'pix_copia_cola']),
        ('recorrencia', 'Recorrência / Parcelamento', 'grid', 'Parcelamento divide o valor total. Recorrência repete o valor em cada lançamento.',
         ['modo', 'frequencia', 'quantidade_lancamentos']),
        ('documentos', 'Documentos', 'quote', 'Anexe boletos, faturas, notas fiscais ou contratos. Comprovantes são anexados ao registrar o pagamento.',
         ['documentos', 'link_acesso']),
        ('observacoes', 'Observações', 'quote', 'Informações complementares para o controle interno.', ['observacoes']),
    ]
    return {'form': form, 'conta': conta, 'titulo': f'Editar {conta.codigo}' if conta else 'Nova conta a pagar',
            'secoes': [{'id': ident, 'titulo': titulo, 'icone': icone, 'ajuda': ajuda,
                        'campos': [form[campo] for campo in campos]} for ident, titulo, icone, ajuda, campos in secoes]}

def filtrar_contas(params):
    dados = params.copy()
    dados.setdefault("status", "pendente")
    dados.setdefault("data_referencia", "vencimento")
    form = FiltroContaForm(dados)
    qs = ContaPagar.objects.select_related("forma_prevista")
    if not form.is_valid():
        return form, qs.none()
    d = form.cleaned_data
    if d["status"] == "atrasada":
        qs = qs.filter(status__in=['pendente', 'parcial'], vencimento__lt=timezone.localdate())
    elif d['status'] == 'pendente':
        qs = qs.filter(status__in=['pendente', 'parcial'])
    elif d['status'] in ['aguardando', 'programada']:
        qs = qs.filter(status='pendente', vencimento__gte=timezone.localdate(),
                       data_programada__isnull=d['status'] == 'aguardando')
    elif d["status"] != "todas":
        qs = qs.filter(status=d["status"])
    if d["tipo_conta"]:
        qs = qs.filter(tipo_conta=d["tipo_conta"])
    for campo, lookup in [("inicio", "gte"), ("fim", "lte")]:
        if d[campo]:
            qs = qs.filter(**{d["data_referencia"]+"__"+lookup: d[campo]})
    return form, qs


def salvar_anexo(request, conta, form, tipo=None):
    arquivo = form.cleaned_data.get("comprovante")
    link = form.cleaned_data.get("link_acesso", "")
    adicionar_anexo(request.user, conta, arquivo, link, tipo=tipo or form.cleaned_data.get('tipo') or 'cobranca')
    for documento in form.cleaned_data.get('documentos', []):
        adicionar_anexo(request.user, conta, arquivo=documento, tipo='cobranca')


@login_required
@permission_required("contas.view_contapagar", raise_exception=True)
def lista(request):
    form, qs = filtrar_contas(request.GET)
    pendentes = qs.filter(status__in=['pendente', 'parcial'])
    params = request.GET.copy()
    for chave in list(params):
        if chave not in form.fields:
            params.pop(chave, None)
    return render(request, "contas/lista.html", {"pagina": Paginator(qs,30).get_page(request.GET.get("page")), "filtros":form, "parametros":params.urlencode(),
        "total_filtrado":qs.aggregate(v=Sum("valor"))["v"] or 0,
        "pendente":pendentes.aggregate(v=Sum(F('valor')-F('valor_pago')))["v"] or 0,
        "atrasado":pendentes.filter(vencimento__lt=timezone.localdate()).aggregate(v=Sum(F('valor')-F('valor_pago')))["v"] or 0})

@login_required
@permission_required("contas.add_contapagar", raise_exception=True)
def nova(request):
    form = ContaForm(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            contas, criado = criar_contas(request.user, form.cleaned_data)
            messages.success(request, f'{len(contas)} lançamento(s) salvo(s).' if criado else 'Este cadastro já foi salvo; nenhum lançamento duplicado.')
            if request.POST.get('acao') == 'outra':
                return redirect('contas:nova')
            return redirect('contas:detalhe', pk=contas[0].pk)
        except ValidationError as exc:
            form.add_error(None, ' '.join(exc.messages))
    return render(request, 'contas/formulario.html', contexto_formulario(form))

@login_required
@permission_required("contas.view_contapagar", raise_exception=True)
def detalhe(request,pk):
    return render(request,"contas/detalhe.html",{"conta":get_object_or_404(ContaPagar.objects.prefetch_related("anexos", 'pagamentos__anexos'),pk=pk), "anexo_form":AnexoForm()})

@login_required
@permission_required("contas.change_contapagar", raise_exception=True)
@transaction.atomic
def editar(request,pk):
    conta = get_object_or_404(ContaPagar.objects.select_for_update(),pk=pk)
    if not conta.em_aberto:
        messages.error(request,"Somente contas em aberto podem ser editadas.")
        return redirect("contas:detalhe",pk=pk)
    antes = {f: str(getattr(conta,f)) for f in ContaForm.Meta.fields}
    form = ContaForm(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None,instance=conta)
    if request.method == "POST" and form.is_valid():
        form.save()
        salvar_anexo(request,conta,form)
        registrar(request.user,"conta.editada",conta.codigo,antes=antes,depois={f:str(getattr(conta,f)) for f in ContaForm.Meta.fields})
        if request.POST.get('acao') == 'outra':
            return redirect('contas:nova')
        return redirect("contas:detalhe",pk=pk)
    return render(request, 'contas/formulario.html', contexto_formulario(form, conta))

@login_required
@permission_required("contas.change_contapagar", raise_exception=True)
def pagar(request,pk):
    conta = get_object_or_404(ContaPagar,pk=pk)
    form = PagamentoForm(request.POST if request.method == "POST" else None, request.FILES if request.method == 'POST' else None,
                         initial={"forma": conta.forma_prevista_id, 'valor': conta.saldo, 'origem': 'externo'})
    if request.method == "POST" and form.is_valid():
        try:
            _, criado = registrar_pagamento(request.user, pk, form.cleaned_data)
            messages.success(request, 'Pagamento registrado.' if criado else 'Este pagamento já foi registrado; nenhuma duplicação.')
            return redirect("contas:detalhe",pk=pk)
        except ValidationError as exc:
            form.add_error(None,exc)
    return render(request,"core/form.html",{"form":form,"titulo":f"Registrar pagamento de {conta.codigo} — saldo R$ {conta.saldo:.2f}"})

@login_required
@permission_required("contas.change_contapagar", raise_exception=True)
@transaction.atomic
def cancelar(request,pk):
    conta = get_object_or_404(ContaPagar.objects.select_for_update(),pk=pk)
    form = CancelamentoForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        if conta.status != "pendente" or conta.valor_pago:
            form.add_error(None,"Somente contas sem pagamentos podem ser canceladas. Preserve o histórico dos pagamentos já realizados.")
        else:
            conta.status = "cancelada"
            conta.motivo_cancelamento = form.cleaned_data["motivo"]
            conta.save()
            registrar(request.user,"conta.cancelada",conta.codigo,motivo=conta.motivo_cancelamento)
            return redirect("contas:detalhe",pk=pk)
    return render(request,"core/form.html",{"form":form,"titulo":f"Cancelar {conta.codigo}"})


@login_required
@permission_required('contas.delete_contapagar', raise_exception=True)
@transaction.atomic
def excluir(request, pk):
    conta = get_object_or_404(ContaPagar.objects.select_for_update(), pk=pk)
    permitido = not (conta.valor_pago or conta.pagamentos.exists() or conta.movimento_id or conta.status == 'paga')
    if request.method == 'POST':
        if not permitido:
            messages.error(request, 'Contas com pagamentos não podem ser excluídas. O histórico financeiro será preservado.')
            return redirect('contas:detalhe', pk=pk)
        if request.POST.get('confirmar') == 'sim':
            arquivos = [(a.arquivo.storage, a.arquivo.name) for a in conta.anexos.all() if a.arquivo]
            registrar(request.user, 'conta.excluida', conta.codigo, valor=str(conta.valor), fornecedor=conta.fornecedor)
            conta.anexos.all().delete()
            conta.delete()
            for storage, nome in arquivos:
                apagar_arquivo_apos_commit(storage, nome)
            messages.success(request, 'Conta excluída. Os demais lançamentos da série foram mantidos.')
            return redirect('contas:lista')
    return render(request, 'contas/excluir.html', {'conta': conta, 'permitido': permitido})


@login_required
@permission_required("contas.change_contapagar", raise_exception=True)
@require_POST
def anexar(request, pk):
    conta = get_object_or_404(ContaPagar,pk=pk)
    form = AnexoForm(request.POST, request.FILES)
    if form.is_valid():
        with transaction.atomic():
            salvar_anexo(request,conta,form)
        messages.success(request,"Comprovante/link adicionado à conta.")
        return redirect("contas:detalhe",pk=pk)
    return render(request,"contas/detalhe.html",{"conta":conta,"anexo_form":form},status=400)


@login_required
@permission_required("contas.view_contapagar", raise_exception=True)
def baixar_anexo(request, pk):
    anexo = get_object_or_404(AnexoConta,pk=pk)
    if not anexo.arquivo:
        raise Http404
    from django.conf import settings
    if settings.STORAGE_MODE == "r2":
        from django.utils.http import content_disposition_header
        url = anexo.arquivo.storage.url(anexo.arquivo.name, expire=60, parameters={
            "ResponseContentDisposition": content_disposition_header(True, anexo.nome_arquivo),
        })
        response = redirect(url)
        response["Cache-Control"] = "private, no-store"
        return response
    try:
        arquivo = anexo.arquivo.open("rb")
    except FileNotFoundError:
        raise Http404
    response = FileResponse(arquivo,as_attachment=True,filename=anexo.nome_arquivo)
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@permission_required("contas.view_contapagar", raise_exception=True)
def pdf_individual(request, pk):
    from .pdf import gerar_pdf
    conta = get_object_or_404(ContaPagar.objects.select_related("forma_prevista","pago_por").prefetch_related("anexos"),pk=pk)
    return gerar_pdf([conta],individual=True)


@login_required
@permission_required("contas.view_contapagar", raise_exception=True)
def pdf_relatorio(request):
    from .pdf import gerar_pdf
    form, qs = filtrar_contas(request.GET)
    if not form.is_valid():
        return render(request,"core/form.html",{"form":form,"titulo":"Confira os filtros antes de gerar o PDF"},status=400)
    rotulos = []
    for nome, valor in form.cleaned_data.items():
        if valor:
            campo = form.fields[nome]
            if hasattr(campo,"choices") and nome != "forma":
                valor = dict(campo.choices).get(valor,valor)
            if hasattr(valor,"strftime"):
                valor = valor.strftime("%d/%m/%Y")
            rotulos.append(f"{campo.label}: {valor}")
    return gerar_pdf(qs,filtros=rotulos)


def apagar_arquivo_apos_commit(storage, nome):
    if nome:
        transaction.on_commit(lambda: storage.delete(nome), robust=True)


@login_required
@permission_required("contas.change_contapagar", raise_exception=True)
@transaction.atomic
def editar_anexo(request, pk):
    anexo = get_object_or_404(AnexoConta.objects.select_for_update().select_related("conta"),pk=pk)
    form = EditarAnexoForm(request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None, anexo=anexo, initial={"link_acesso":anexo.link})
    if request.method == "POST" and form.is_valid():
        from pathlib import Path
        antigo = anexo.arquivo.name
        storage = anexo.arquivo.storage
        antes = {"arquivo":anexo.nome_arquivo, "link":anexo.link}
        novo = form.cleaned_data.get("comprovante")
        if novo:
            anexo.arquivo = novo
            anexo.nome_arquivo = Path(novo.name).name[:255]
        elif form.cleaned_data.get("remover_arquivo"):
            anexo.arquivo = ""
            anexo.nome_arquivo = ""
        anexo.link = form.cleaned_data.get("link_acesso", "")
        anexo.save()
        registrar(request.user,"conta.anexo_editado",anexo.conta.codigo,anexo=anexo.pk,antes=antes,
            depois={"arquivo":anexo.nome_arquivo,"link":anexo.link})
        if antigo and antigo != anexo.arquivo.name:
            apagar_arquivo_apos_commit(storage,antigo)
        messages.success(request,"Anexo atualizado.")
        return redirect("contas:detalhe",pk=anexo.conta_id)
    return render(request,"contas/editar_anexo.html",{"form":form,"anexo":anexo})


@login_required
@permission_required("contas.change_contapagar", raise_exception=True)
@transaction.atomic
def excluir_anexo(request, pk):
    anexo = get_object_or_404(AnexoConta.objects.select_for_update().select_related("conta"),pk=pk)
    if request.method == "POST":
        conta_id = anexo.conta_id
        storage, nome = anexo.arquivo.storage, anexo.arquivo.name
        registrar(request.user,"conta.anexo_excluido",anexo.conta.codigo,anexo=anexo.pk,
            arquivo=anexo.nome_arquivo,link=anexo.link)
        anexo.delete()
        apagar_arquivo_apos_commit(storage,nome)
        messages.success(request,"Anexo excluído.")
        return redirect("contas:detalhe",pk=conta_id)
    return render(request,"contas/excluir_anexo.html",{"anexo":anexo})
