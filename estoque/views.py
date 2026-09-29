from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from core.auditoria import registrar
from .forms import PecaEdicaoForm
from .models import Peca


def pecas_filtradas(params):
    consulta = params.get("q", "").strip()[:200]
    status = params.get("status", "")
    pecas = Peca.objects.select_related("categoria", "veiculo_origem", "localizacao").prefetch_related("fotos")
    campos = ["codigo", "nome", "categoria__nome", "marca", "aplicacao", "motor", "posicao",
        "veiculo_origem__codigo", "veiculo_origem__marca", "veiculo_origem__modelo",
        "veiculo_origem__versao", "veiculo_origem__motor", "localizacao__codigo", "localizacao__nome"]
    for termo in consulta.split()[:12]:
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
    response = render(request, "impressao/etiqueta.html", {"peca": peca})
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@permission_required("estoque.view_peca", raise_exception=True)
def lista(request):
    pecas, consulta, status = pecas_filtradas(request.GET)
    pagina = Paginator(pecas, 20).get_page(request.GET.get("page"))
    return render(request, "estoque/lista.html", {
        "pagina": pagina, "q": consulta, "status": status, "status_opcoes": Peca.Status.choices,
    })


@login_required
@permission_required("estoque.view_peca", raise_exception=True)
def imprimir_pdf(request):
    from .pdf import gerar_pdf

    pecas, consulta, status = pecas_filtradas(request.GET)
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
