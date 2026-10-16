from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from estoque.models import Peca
from vendas.models import Venda
from caixa.models import MovimentoCaixa
from django.utils import timezone


@login_required
def index(request):
    context = {}
    if request.user.has_perm("estoque.view_peca"):
        context = {
            "disponiveis": Peca.objects.filter(status=Peca.Status.DISPONIVEL).aggregate(n=Sum("quantidade"))["n"] or 0,
            "reservadas": Peca.objects.filter(status=Peca.Status.RESERVADA).aggregate(n=Sum("quantidade"))["n"] or 0,
            "cadastros": Peca.objects.count(),
            "recentes": Peca.objects.select_related("categoria", "localizacao").prefetch_related("fotos").order_by("-criado_em")[:5],
        }
    if request.user.has_perm("vendas.view_venda"):
        vendas = Venda.objects.exclude(status="cancelada")
        movimentos = MovimentoCaixa.objects.filter(tipo__in=["venda", "estorno"])
        if not request.user.has_perm("vendas.ver_todas_vendas"):
            vendas = vendas.filter(vendedor=request.user)
            movimentos = movimentos.filter(operador=request.user)
        hoje = timezone.localdate()
        context.update({"vendas_dia": vendas.filter(criado_em__date=hoje).count(),
            "vendas_mes": vendas.filter(criado_em__date__gte=hoje.replace(day=1), criado_em__date__lte=hoje).count(),
            "valor_dia": movimentos.filter(criado_em__date=hoje).aggregate(s=Sum("valor"))["s"] or 0,
            "valor_mes": movimentos.filter(criado_em__date__gte=hoje.replace(day=1), criado_em__date__lte=hoje).aggregate(s=Sum("valor"))["s"] or 0,
            "ultimas_vendas": vendas.select_related("vendedor")[:5]})
    return render(request, "dashboard/index.html", context)
