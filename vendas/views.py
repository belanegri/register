import csv
import uuid
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from estoque.models import Peca
from caixa.models import SessaoCaixa, MovimentoCaixa
from core.models import Evento
from .models import Venda, Devolucao, Pagamento, NotaPromissoria
from .forms import CheckoutForm, PagamentosFormSet, CancelamentoForm, DevolucaoForm, PeriodoForm, CorrecaoForm, ItensCorrecaoFormSet, ReceberNotaForm
from . import services


def vendas_permitidas(usuario):
    qs = Venda.objects.select_related("vendedor", "cliente", "caixa")
    return qs if usuario.has_perm("vendas.ver_todas_vendas") else qs.filter(vendedor=usuario)


def dados_promissoria(form):
    return {campo: form.cleaned_data.get(campo) or "" for campo in
        ["vencimento", "beneficiario", "documento_beneficiario", "local_emissao", "local_pagamento"]}


@login_required
@permission_required("vendas.view_venda", raise_exception=True)
def recibo(request, pk):
    venda = get_object_or_404(vendas_permitidas(request.user), pk=pk)
    devolucoes = Devolucao.objects.filter(item__venda=venda).select_related("item")
    reembolsado = devolucoes.aggregate(s=Sum("valor"))["s"] or Decimal("0")
    response = render(request, "impressao/recibo.html", {"venda": venda,
        "itens": venda.itens.all(), "pagamentos": venda.pagamentos.all(), "devolucoes": devolucoes,
        "liquido": Decimal("0") if venda.status == "cancelada" else venda.total-reembolsado})
    response["Cache-Control"] = "private, no-store"
    return response


def linhas_carrinho(request):
    carrinho = request.session.get("carrinho", {})
    pecas = {str(p.pk): p for p in Peca.objects.filter(pk__in=carrinho.keys()).select_related("localizacao")}
    linhas = []
    for pk, dados in carrinho.items():
        peca = pecas.get(pk)
        linhas.append({"id": pk, "peca": peca, "quantidade": dados["quantidade"], "preco": Decimal(dados["preco"]),
            "total": Decimal(dados["preco"]) * dados["quantidade"]})
    return linhas


@login_required
@permission_required("vendas.usar_pdv", raise_exception=True)
def pdv(request):
    q = request.GET.get("q", "").strip()[:200]
    pecas = Peca.objects.filter(status="disponivel", quantidade__gt=0).select_related("categoria", "localizacao").prefetch_related("fotos")
    for termo in q.split()[:12]:
        filtro = Q()
        for campo in ["codigo", "nome", "marca", "aplicacao", "posicao", "motor", "categoria__nome", "localizacao__codigo", "veiculo_origem__modelo", "veiculo_origem__versao"]:
            filtro |= Q(**{f"{campo}__icontains": termo})
        if termo.isdigit() and 1900 <= int(termo) <= 2100:
            filtro |= Q(ano_inicial__lte=int(termo), ano_final__gte=int(termo)) | Q(veiculo_origem__ano_modelo=int(termo))
        pecas = pecas.filter(filtro)
    linhas = linhas_carrinho(request)
    chave = request.session.get("checkout_chave") or str(uuid.uuid4())
    request.session["checkout_chave"] = chave
    return render(request, "vendas/pdv.html", {"q": q, "pecas": pecas[:40], "linhas": linhas,
        "subtotal": sum(l["total"] for l in linhas), "form": CheckoutForm(initial={"chave": chave}),
        "pagamentos": PagamentosFormSet(prefix="pag"),
        "caixa": SessaoCaixa.objects.filter(operador=request.user, fechado_em__isnull=True).first()})


@login_required
@permission_required("vendas.usar_pdv", raise_exception=True)
@require_POST
def carrinho(request):
    dados = request.session.get("carrinho", {})
    acao, pk = request.POST.get("acao"), request.POST.get("peca")
    try:
        if acao == "limpar":
            dados = {}
        elif acao == "remover":
            dados.pop(pk, None)
        elif acao == "preco":
            if pk not in dados:
                raise ValidationError("Adicione a peça ao carrinho primeiro.")
            preco = services.dinheiro(request.POST.get("preco"))
            if preco <= 0:
                raise ValidationError("O preço deve ser maior que zero.")
            dados[pk]["preco"] = str(preco)
            dados[pk]["preco_personalizado"] = True
        elif acao in ["adicionar", "quantidade"]:
            peca = get_object_or_404(Peca, pk=pk)
            quantidade = services.quantidade_inteira(request.POST.get("quantidade", "1"))
            if acao == "adicionar":
                quantidade += dados.get(pk, {}).get("quantidade", 0)
            if peca.status != "disponivel" or quantidade > peca.quantidade:
                raise ValidationError("Quantidade indisponível em estoque.")
            if len(dados) >= 100 and pk not in dados:
                raise ValidationError("O carrinho suporta até 100 peças diferentes.")
            dados[pk] = {**dados.get(pk, {}), "quantidade": quantidade, "preco": dados.get(pk, {}).get("preco", str(peca.preco_venda))}
        else:
            raise ValidationError("Operação inválida.")
        request.session["carrinho"] = dados
        request.session["checkout_chave"] = str(uuid.uuid4())
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("vendas:pdv")


@login_required
@permission_required("vendas.usar_pdv", raise_exception=True)
@require_POST
def finalizar(request):
    form = CheckoutForm(request.POST)
    pagamentos = PagamentosFormSet(request.POST, prefix="pag")
    if form.is_valid() and pagamentos.is_valid():
        chave = form.cleaned_data["chave"]
        existente = Venda.objects.filter(chave=chave, vendedor=request.user).first()
        if existente:
            return redirect("vendas:detalhe", pk=existente.pk)
        if str(chave) != request.session.get("checkout_chave"):
            form.add_error(None, "O carrinho mudou. Volte ao PDV e revise os itens antes de finalizar.")
        else:
            try:
                venda = services.finalizar(request.user, chave, request.session.get("carrinho", {}),
                    [{"forma": f.cleaned_data["forma"].pk, "valor": f.cleaned_data["valor"]} for f in pagamentos if f.cleaned_data],
                    desconto=form.cleaned_data["desconto"],
                    cliente_id=form.cleaned_data["cliente"].pk if form.cleaned_data["cliente"] else None,
                    dados_nota=dados_promissoria(form))
                request.session["carrinho"] = {}
                request.session.pop("checkout_chave", None)
                messages.success(request, f"Venda {venda.codigo} concluída. Estoque atualizado.")
                return redirect("vendas:detalhe", pk=venda.pk)
            except ValidationError as exc:
                form.add_error(None, exc)
    linhas = linhas_carrinho(request)
    return render(request, "vendas/pdv.html", {"form": form, "pagamentos": pagamentos, "linhas": linhas,
        "subtotal": sum(l["total"] for l in linhas), "pecas": [],
        "caixa": SessaoCaixa.objects.filter(operador=request.user, fechado_em__isnull=True).first()}, status=400)


@login_required
@permission_required("vendas.view_venda", raise_exception=True)
def lista(request):
    qs = vendas_permitidas(request.user)
    q = request.GET.get("q", "").strip()[:150]
    if q:
        filtro = Q(cliente_nome__icontains=q) | Q(vendedor__username__icontains=q)
        codigo = q.upper().removeprefix("VEN-")
        if codigo.isdigit():
            filtro |= Q(pk=int(codigo))
        qs = qs.filter(filtro)
    return render(request, "vendas/lista.html", {"pagina": Paginator(qs, 30).get_page(request.GET.get("page")), "q": q})


@login_required
@permission_required("vendas.view_venda", raise_exception=True)
def detalhe(request, pk):
    venda = get_object_or_404(vendas_permitidas(request.user), pk=pk)
    itens = list(venda.itens.prefetch_related("devolucoes").select_related("peca"))
    devolucao = DevolucaoForm(initial={"chave": uuid.uuid4()})
    devolucao.fields["item"].choices = [(i.pk, f"{i.descricao} — {i.quantidade_restante} a devolver") for i in itens if i.quantidade_restante]
    retornos = Devolucao.objects.filter(item__venda=venda).select_related("operador", "item")
    reembolsado = retornos.aggregate(s=Sum("valor"))["s"] or Decimal("0")
    notas = NotaPromissoria.objects.filter(pagamento__venda=venda).select_related("pagamento").prefetch_related("movimentos")
    return render(request, "vendas/detalhe.html", {"venda": venda, "itens": itens,
        "pagamentos": venda.pagamentos.all(), "devolucoes": retornos, "reembolsado": reembolsado,
        "liquido": Decimal("0") if venda.status == "cancelada" else venda.total-reembolsado,
        "cancelamento_form": CancelamentoForm(), "devolucao_form": devolucao,
        "notas": notas, "pendente": sum((n.saldo for n in notas), Decimal("0")),
        "historico": Evento.objects.filter(objeto=venda.codigo).select_related("usuario")})


@login_required
@permission_required("vendas.cancelar_venda", raise_exception=True)
@require_POST
def cancelar(request, pk):
    get_object_or_404(vendas_permitidas(request.user), pk=pk)
    form = CancelamentoForm(request.POST)
    if form.is_valid():
        try:
            services.cancelar(request.user, pk, form.cleaned_data["motivo"])
            messages.success(request, "Venda cancelada; estoque reposto e estorno registrado. Efetue o reembolso no meio de pagamento utilizado.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    else:
        messages.error(request, "Informe o motivo do cancelamento.")
    return redirect("vendas:detalhe", pk=pk)


@login_required
@permission_required("vendas.editar_venda", raise_exception=True)
def editar(request, pk):
    venda = get_object_or_404(vendas_permitidas(request.user), pk=pk)
    if venda.status != "concluida":
        messages.error(request, "Esta venda não pode ser editada. Consulte seu histórico de cancelamento/devolução.")
        return redirect("vendas:detalhe", pk=pk)
    inicial = {"chave": uuid.uuid4(), "cliente": venda.cliente_id, "desconto": venda.desconto}
    nota = NotaPromissoria.objects.filter(pagamento__venda=venda).first()
    if nota:
        for campo in ["vencimento", "beneficiario", "documento_beneficiario", "local_emissao", "local_pagamento"]:
            inicial[campo] = getattr(nota, campo)
    form = CorrecaoForm(request.POST if request.method == "POST" else None, initial=inicial)
    itens = ItensCorrecaoFormSet(request.POST if request.method == "POST" else None, prefix="itens",
        initial=[{"peca": i.peca_id, "quantidade": i.quantidade, "preco": i.preco_unitario} for i in venda.itens.all()])
    pagamentos = PagamentosFormSet(request.POST if request.method == "POST" else None, prefix="pag",
        initial=[{"forma": p.forma_id, "valor": p.valor} for p in venda.pagamentos.all()])
    if request.method == "POST" and all([form.is_valid(), itens.is_valid(), pagamentos.is_valid()]):
        carrinho = {}
        for linha in itens.cleaned_data:
            if linha and not linha.get("DELETE"):
                chave = str(linha["peca"].pk)
                if chave in carrinho:
                    form.add_error(None, "Não repita a mesma peça; ajuste a quantidade na linha existente.")
                carrinho[chave] = {"quantidade": linha["quantidade"], "preco": str(linha["preco"])}
        if not form.errors:
            try:
                nova = services.corrigir(request.user, venda.pk, form.cleaned_data["chave"], carrinho,
                    [{"forma": f.cleaned_data["forma"].pk, "valor": f.cleaned_data["valor"]} for f in pagamentos if f.cleaned_data],
                    form.cleaned_data["motivo"], form.cleaned_data["desconto"],
                    form.cleaned_data["cliente"].pk if form.cleaned_data["cliente"] else None, dados_promissoria(form))
                messages.success(request, f"Correção registrada em {nova.codigo}. A venda anterior foi cancelada e preservada no histórico.")
                return redirect("vendas:detalhe", pk=nova.pk)
            except ValidationError as exc:
                form.add_error(None, exc)
    return render(request, "vendas/editar.html", {"venda": venda, "form": form, "itens": itens, "pagamentos": pagamentos})


@login_required
@permission_required("vendas.view_venda", raise_exception=True)
def promissoria(request, pk):
    nota = get_object_or_404(NotaPromissoria.objects.select_related("pagamento__venda").prefetch_related("movimentos"), pk=pk)
    get_object_or_404(vendas_permitidas(request.user), pk=nota.pagamento.venda_id)
    response = render(request, "impressao/promissoria.html", {"nota": nota})
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@permission_required("vendas.receber_promissoria", raise_exception=True)
def receber_promissoria(request, pk):
    nota = get_object_or_404(NotaPromissoria.objects.select_related("pagamento__venda"), pk=pk)
    get_object_or_404(vendas_permitidas(request.user), pk=nota.pagamento.venda_id)
    form = ReceberNotaForm(request.POST if request.method == "POST" else None, initial={"chave": uuid.uuid4(), "valor": nota.saldo})
    if request.method == "POST" and form.is_valid():
        try:
            services.receber_nota(request.user, nota.pk, form.cleaned_data["valor"], form.cleaned_data["forma"].pk, form.cleaned_data["chave"])
            messages.success(request, "Recebimento registrado no caixa e abatido do saldo da promissória.")
            return redirect("vendas:detalhe", pk=nota.pagamento.venda_id)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "core/form.html", {"form": form, "titulo": f"Receber {nota.codigo} — saldo R$ {nota.saldo:.2f}"})


@login_required
@permission_required("vendas.devolver_venda", raise_exception=True)
@require_POST
def devolver(request, pk):
    venda = get_object_or_404(vendas_permitidas(request.user), pk=pk)
    form = DevolucaoForm(request.POST)
    form.fields["item"].choices = [(i.pk, i.descricao) for i in venda.itens.all()]
    if form.is_valid():
        d = form.cleaned_data
        try:
            retorno = services.devolver(request.user, pk, d["item"], d["quantidade"], d["forma"].pk, d["motivo"], d["chave"])
            messages.success(request, f"Estoque reposto. Reembolso ao cliente: R$ {retorno.reembolsado:.2f}. Abatimento de promissória: R$ {retorno.abatimento_promissoria:.2f}.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    else:
        messages.error(request, "Confira o item, quantidade, forma de reembolso e motivo.")
    return redirect("vendas:detalhe", pk=pk)


@login_required
@permission_required("vendas.ver_relatorios", raise_exception=True)
def relatorios(request):
    hoje = timezone.localdate()
    form = PeriodoForm(request.GET or {"inicio": hoje.replace(day=1), "fim": hoje})
    vendas = Venda.objects.none()
    movimentos = MovimentoCaixa.objects.none()
    retornos = Devolucao.objects.none()
    if form.is_valid():
        intervalo = (form.cleaned_data["inicio"], form.cleaned_data["fim"])
        vendas = Venda.objects.filter(criado_em__date__range=intervalo)
        movimentos = MovimentoCaixa.objects.filter(criado_em__date__range=intervalo)
        retornos = Devolucao.objects.filter(criado_em__date__range=intervalo)
    resumo = vendas.exclude(status="cancelada").aggregate(valor=Sum("total"), descontos=Sum("desconto"), quantidade=Count("pk"))
    entradas = movimentos.filter(tipo="venda").aggregate(s=Sum("valor"))["s"] or Decimal("0")
    estornos = movimentos.filter(tipo="estorno").aggregate(s=Sum("valor"))["s"] or Decimal("0")
    if request.GET.get("exportar") == "csv" and form.is_valid():
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="vendas-pontocar.csv"'
        response.write("\ufeff")
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["Venda", "Data", "Cliente", "Vendedor", "Subtotal", "Desconto", "Total", "Situação"])
        for venda in vendas.select_related("vendedor").iterator():
            def seguro(valor):
                s = str(valor)
                return "'" + s if s.lstrip().startswith(("=", "+", "-", "@")) else s
            writer.writerow([venda.codigo, timezone.localtime(venda.criado_em).strftime("%d/%m/%Y %H:%M"),
                seguro(venda.cliente_nome), seguro(venda.vendedor.username), venda.subtotal, venda.desconto, venda.total, venda.get_status_display()])
        return response
    return render(request, "vendas/relatorios.html", {"form": form, "resumo": resumo, "entradas": entradas,
        "estornos": -estornos, "liquido": entradas+estornos, "canceladas": vendas.filter(status="cancelada").count(),
        "retornos": retornos.aggregate(s=Sum("valor"))["s"] or 0,
        "formas": Pagamento.objects.filter(venda__in=vendas).values("forma_nome").annotate(valor=Sum("valor")).order_by("forma_nome"),
        "estoque": Peca.objects.values("status").annotate(cadastros=Count("pk"), unidades=Sum("quantidade")),
        "vendas": vendas.select_related("vendedor")[:100]})
