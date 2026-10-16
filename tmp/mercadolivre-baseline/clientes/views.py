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
    clientes = Cliente.objects.filter(Q(nome__icontains=q) | Q(documento__icontains=q) | Q(telefone__icontains=q))
    return render(request, "clientes/lista.html", {"pagina": Paginator(clientes, 30).get_page(request.GET.get("page")), "q": q})


@login_required
def editar(request, pk=None):
    from django.core.exceptions import PermissionDenied
    if not request.user.has_perm("clientes.change_cliente" if pk else "clientes.add_cliente"):
        raise PermissionDenied
    cliente = get_object_or_404(Cliente, pk=pk) if pk else None
    form = ClienteForm(request.POST or None, instance=cliente)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            cliente = form.save()
            registrar(request.user, "cliente.alterado" if pk else "cliente.criado", f"Cliente {cliente.pk}", campos=form.changed_data)
        messages.success(request, "Cliente salvo.")
        return redirect("clientes:detalhe", pk=cliente.pk)
    return render(request, "core/form.html", {"form": form, "titulo": "Editar cliente" if pk else "Novo cliente"})


@login_required
@permission_required("clientes.view_cliente", raise_exception=True)
def detalhe(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    vendas = cliente.vendas.select_related("vendedor")
    if not request.user.has_perm("vendas.ver_todas_vendas"):
        vendas = vendas.filter(vendedor=request.user)
    if not request.user.has_perm("vendas.view_venda"):
        vendas = vendas.none()
    return render(request, "clientes/detalhe.html", {"cliente": cliente, "vendas": vendas[:100]})
