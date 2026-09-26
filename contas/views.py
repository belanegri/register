from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from core.auditoria import registrar
from caixa.services import caixa_aberto, movimentar
from .models import ContaPagar, AnexoConta
from .forms import ContaForm, PagamentoForm, CancelamentoForm, AnexoForm, FiltroContaForm, EditarAnexoForm
from django.http import FileResponse, Http404
from django.views.decorators.http import require_POST

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
        qs = qs.filter(status="pendente", vencimento__lt=timezone.localdate())
    elif d["status"] != "todas":
        qs = qs.filter(status=d["status"])
    if d["tipo_conta"]:
        qs = qs.filter(tipo_conta=d["tipo_conta"])
    for campo, lookup in [("inicio", "gte"), ("fim", "lte")]:
        if d[campo]:
            qs = qs.filter(**{d["data_referencia"]+"__"+lookup: d[campo]})
    return form, qs


def salvar_anexo(request, conta, form):
    arquivo = form.cleaned_data.get("comprovante")
    link = form.cleaned_data.get("link_acesso", "")
    if arquivo or link:
        from pathlib import Path
        anexo = AnexoConta.objects.create(conta=conta, arquivo=arquivo or "", link=link,
            nome_arquivo=Path(arquivo.name).name[:255] if arquivo else "", criado_por=request.user)
        registrar(request.user,"conta.anexo",conta.codigo,anexo=anexo.pk)


@login_required
@permission_required("contas.view_contapagar", raise_exception=True)
def lista(request):
    form, qs = filtrar_contas(request.GET)
    pendentes = qs.filter(status="pendente")
    params = request.GET.copy()
    for chave in list(params):
        if chave not in form.fields:
            params.pop(chave, None)
    return render(request, "contas/lista.html", {"pagina": Paginator(qs,30).get_page(request.GET.get("page")), "filtros":form, "parametros":params.urlencode(),
        "total_filtrado":qs.aggregate(v=Sum("valor"))["v"] or 0,
        "pendente":pendentes.aggregate(v=Sum("valor"))["v"] or 0,
        "atrasado":pendentes.filter(vencimento__lt=timezone.localdate()).aggregate(v=Sum("valor"))["v"] or 0})

@login_required
@permission_required("contas.add_contapagar", raise_exception=True)
def nova(request):
    form = ContaForm(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            conta = form.save(commit=False)
            conta.criado_por = request.user
            conta.save()
            salvar_anexo(request,conta,form)
            registrar(request.user,"conta.criada",conta.codigo,valor=str(conta.valor))
        return redirect("contas:detalhe",pk=conta.pk)
    return render(request,"core/form.html",{"form":form,"titulo":"Nova conta a pagar"})

@login_required
@permission_required("contas.view_contapagar", raise_exception=True)
def detalhe(request,pk):
    return render(request,"contas/detalhe.html",{"conta":get_object_or_404(ContaPagar.objects.prefetch_related("anexos"),pk=pk), "anexo_form":AnexoForm()})

@login_required
@permission_required("contas.change_contapagar", raise_exception=True)
@transaction.atomic
def editar(request,pk):
    conta = get_object_or_404(ContaPagar.objects.select_for_update(),pk=pk)
    if conta.status != "pendente":
        messages.error(request,"Somente contas pendentes podem ser editadas.")
        return redirect("contas:detalhe",pk=pk)
    antes = {f: str(getattr(conta,f)) for f in ContaForm.Meta.fields}
    form = ContaForm(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None,instance=conta)
    if request.method == "POST" and form.is_valid():
        form.save()
        salvar_anexo(request,conta,form)
        registrar(request.user,"conta.editada",conta.codigo,antes=antes,depois={f:str(getattr(conta,f)) for f in ContaForm.Meta.fields})
        return redirect("contas:detalhe",pk=pk)
    return render(request,"core/form.html",{"form":form,"titulo":f"Editar {conta.codigo}"})

@login_required
@permission_required("contas.change_contapagar", raise_exception=True)
def pagar(request,pk):
    conta = get_object_or_404(ContaPagar,pk=pk)
    form = PagamentoForm(request.POST if request.method == "POST" else None, initial={"forma": conta.forma_prevista_id})
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                if form.cleaned_data["origem"] == "caixa":
                    caixa_aberto(request.user)
                conta = get_object_or_404(ContaPagar.objects.select_for_update(),pk=pk)
                if conta.status != "pendente":
                    raise ValidationError("Esta conta já foi paga ou cancelada.")
                if form.cleaned_data["origem"] == "caixa":
                    conta.movimento = movimentar(request.user,"sangria",conta.valor,f"Pagamento {conta.codigo} · {conta.titulo}")
                conta.status = "paga"
                conta.pago_em = form.cleaned_data["data"]
                conta.pago_por = request.user
                conta.forma_nome = form.cleaned_data["forma"].nome
                conta.save()
                registrar(request.user,"conta.paga",conta.codigo,valor=str(conta.valor),origem=form.cleaned_data["origem"],forma=conta.forma_nome)
            messages.success(request,"Pagamento registrado.")
            return redirect("contas:detalhe",pk=pk)
        except ValidationError as exc:
            form.add_error(None,exc)
    return render(request,"core/form.html",{"form":form,"titulo":f"Registrar pagamento de {conta.codigo} — R$ {conta.valor:.2f}"})

@login_required
@permission_required("contas.change_contapagar", raise_exception=True)
@transaction.atomic
def cancelar(request,pk):
    conta = get_object_or_404(ContaPagar.objects.select_for_update(),pk=pk)
    form = CancelamentoForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        if conta.status != "pendente":
            form.add_error(None,"Somente contas pendentes podem ser canceladas.")
        else:
            conta.status = "cancelada"
            conta.motivo_cancelamento = form.cleaned_data["motivo"]
            conta.save()
            registrar(request.user,"conta.cancelada",conta.codigo,motivo=conta.motivo_cancelamento)
            return redirect("contas:detalhe",pk=pk)
    return render(request,"core/form.html",{"form":form,"titulo":f"Cancelar {conta.codigo}"})


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
