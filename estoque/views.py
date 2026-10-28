import re

from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from core.auditoria import registrar
from .forms import IntervaloCodigoForm, PecaEdicaoForm
from .models import Peca


def pecas_filtradas(params, *, filtro_codigo=None):
    consulta = params.get("q", "").strip()[:200]
    status = params.get("status", "")
    pecas = Peca.objects.select_related("categoria", "veiculo_origem", "localizacao").prefetch_related("fotos").order_by("-criado_em", "-pk")
    if filtro_codigo is None:
        filtro_codigo = IntervaloCodigoForm(params)
    if filtro_codigo.is_valid():
        if inicio := filtro_codigo.cleaned_data["codigo_inicial"]:
            pecas = pecas.filter(codigo__gte=inicio)
        if fim := filtro_codigo.cleaned_data["codigo_final"]:
            pecas = pecas.filter(codigo__lte=fim)
    else:
        pecas = pecas.none()
    intervalo = re.fullmatch(r"REG(\d{6})\s*(?:a|até|ate|[-–—])\s*REG(\d{6})", consulta, re.IGNORECASE)
    if intervalo:
        inicio, fim = sorted(intervalo.groups())
        pecas = pecas.filter(codigo__gte=f"REG{inicio}", codigo__lte=f"REG{fim}")
    campos = ["codigo", "nome", "categoria__nome", "marca", "aplicacao", "motor", "posicao", "compativel",
        "veiculo_origem__codigo", "veiculo_origem__marca", "veiculo_origem__modelo",
        "veiculo_origem__versao", "veiculo_origem__motor", "localizacao__codigo", "localizacao__nome"]
    for termo in ([] if intervalo else consulta.split()[:12]):
        filtro = Q()
        for campo in campos:
            filtro |= Q(**{f"{campo}__icontains": termo})
        if termo.isdigit() and 1900 <= int(termo) <= 2100:
            ano = int(termo)
            filtro |= Q(ano_inicial__lte=ano, ano_final__gte=ano)
            filtro |= Q(ano_inicial=ano, ano_final__isnull=True) | Q(ano_final=ano, ano_inicial__isnull=True)
            filtro |= Q(veiculo_origem__ano_modelo=ano) | Q(veiculo_origem__ano_fabricacao=ano)
        pecas = pecas.filter(filtro)
    if status in Peca.Status.values:
        pecas = pecas.filter(status=status)
    else:
        status = ""
    return pecas, consulta, status


@login_required
@permission_required("estoque.view_peca", raise_exception=True)
def etiqueta(request, pk):
    peca = get_object_or_404(Peca.objects.select_related("categoria", "localizacao"), pk=pk)
    modelo = request.GET.get("modelo", "padrao")
    if modelo not in {"padrao", "online"}:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("Modelo de etiqueta inválido.")
    if request.GET.get("formato") != "pdf":
        from base64 import b64encode, urlsafe_b64encode
        from .codigo_barras import gerar_svg
        from .etiqueta_pdf import gerar_etiqueta_pdf
        barras = gerar_svg(peca.codigo).replace(
            'preserveAspectRatio="xMinYMin meet"', 'preserveAspectRatio="none"')
        response = render(request, "impressao/etiqueta.html", {
            "peca": peca, "modelo_etiqueta": modelo, "codigo_barras_etiqueta": b64encode(barras.encode()).decode(),
            "etiqueta_direta": urlsafe_b64encode(gerar_etiqueta_pdf(peca, modelo=modelo)).decode().rstrip('='),
        })
        response["Cache-Control"] = "private, no-store"
        return response
    from django.http import HttpResponse
    from .etiqueta_pdf import gerar_etiqueta_pdf
    response = HttpResponse(gerar_etiqueta_pdf(peca, modelo=modelo), content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="etiqueta.pdf"'
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@permission_required("estoque.view_peca", raise_exception=True)
def lista(request):
    filtro_codigo = IntervaloCodigoForm(request.GET)
    pecas, consulta, status = pecas_filtradas(request.GET, filtro_codigo=filtro_codigo)
    pagina = Paginator(pecas, 20).get_page(request.GET.get("page"))
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return render(request, "estoque/lista.html", {
        "pagina": pagina, "q": consulta, "status": status, "status_opcoes": Peca.Status.choices,
        "filtro_codigo": filtro_codigo, "filtros_url": parametros.urlencode(),
        "tem_filtros": bool(consulta or status or request.GET.get("codigo_inicial") or request.GET.get("codigo_final")),
    })


@login_required
@permission_required("estoque.view_peca", raise_exception=True)
def imprimir_pdf(request):
    from .pdf import gerar_pdf

    filtro_codigo = IntervaloCodigoForm(request.GET)
    if not filtro_codigo.is_valid():
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("Revise o intervalo de códigos antes de imprimir.")
    pecas, consulta, status = pecas_filtradas(request.GET, filtro_codigo=filtro_codigo)
    inicio, fim = (filtro_codigo.cleaned_data[campo] for campo in ("codigo_inicial", "codigo_final"))
    if inicio or fim:
        descricao = f"Códigos: {inicio or 'início'} até {fim or 'último cadastro'}"
        consulta = f"{consulta} | {descricao}" if consulta else descricao
    return gerar_pdf(pecas, consulta=consulta, status=status)


@login_required
@permission_required("estoque.change_peca", raise_exception=True)
@transaction.atomic
def editar(request, pk):
    peca = get_object_or_404(Peca, pk=pk)
    # Captura antes da validação, que atualiza a instância do ModelForm.
    campos = [f.name for f in Peca._meta.concrete_fields if f.name not in ["criado_em", "atualizado_em"]]
    antes = {campo: str(getattr(peca, campo)) for campo in campos}
    form = PecaEdicaoForm(request.POST if request.method == "POST" else None, instance=peca)
    if request.method == "POST" and form.is_valid():
        peca = form.save()
        registrar(request.user, "peca.alterada", peca.codigo, antes=antes,
            depois={campo: str(getattr(peca, campo)) for campo in campos},
            motivo=form.cleaned_data.get("motivo", ""))
        messages.success(request, f"{peca.codigo} atualizada. Quantidade em estoque: {peca.quantidade}.")
        return redirect("estoque:lista")
    return render(request, "estoque/editar.html", {"form": form, "peca": peca})


@login_required
@permission_required("estoque.view_peca", raise_exception=True)
def detalhe(request, pk):
    peca = get_object_or_404(Peca.objects.select_related("categoria", "veiculo_origem", "localizacao").prefetch_related("fotos"), pk=pk)
    return render(request, "estoque/detalhe.html", {"peca": peca})


@login_required
@permission_required("estoque.view_peca", raise_exception=True)
def codigo_barras(request, pk):
    from django.http import HttpResponse
    from .codigo_barras import gerar_svg
    peca = get_object_or_404(Peca, pk=pk)
    try:
        response = HttpResponse(gerar_svg(peca.codigo), content_type="image/svg+xml")
    except ValueError:
        return HttpResponse("Código incompatível com Code 128.", status=400, content_type="text/plain")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
