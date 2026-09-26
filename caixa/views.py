from django.contrib import messages
import uuid
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from .models import SessaoCaixa
from .forms import AberturaForm, MovimentoForm, FechamentoForm
from . import services


def permitidos(usuario):
    qs = SessaoCaixa.objects.select_related("operador")
    return qs if usuario.has_perm("caixa.ver_todos_caixas") else qs.filter(operador=usuario)


@login_required
@permission_required("caixa.operar_caixa", raise_exception=True)
def painel(request):
    acao = request.POST.get("acao")
    forms = {"abrir": AberturaForm(request.POST if acao == "abrir" else None),
        "movimentar": MovimentoForm(request.POST if acao == "movimentar" else None, initial={"chave": uuid.uuid4()}),
        "fechar": FechamentoForm(request.POST if acao == "fechar" else None)}
    if request.method == "POST" and acao in forms and forms[acao].is_valid():
        try:
            resultado = getattr(services, acao)(request.user, **forms[acao].cleaned_data)
            messages.success(request, "Operação de caixa registrada.")
            if acao == "fechar":
                return redirect("caixa:detalhe", pk=resultado.pk)
            return redirect("caixa:painel")
        except ValidationError as exc:
            forms[acao].add_error(None, exc)
    sessao = SessaoCaixa.objects.filter(operador=request.user, fechado_em__isnull=True).first()
    return render(request, "caixa/painel.html", {"sessao": sessao, "formularios": forms,
        "historico": permitidos(request.user)[:30]})


@login_required
@permission_required("caixa.view_sessaocaixa", raise_exception=True)
def detalhe(request, pk):
    sessao = get_object_or_404(permitidos(request.user), pk=pk)
    return render(request, "caixa/detalhe.html", {"sessao": sessao, "movimentos": sessao.movimentos.select_related("operador", "venda")})
