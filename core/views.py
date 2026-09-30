from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import ConfiguracaoEmpresaForm
from .models import ConfiguracaoEmpresa


@login_required
@permission_required("core.change_configuracaoempresa", raise_exception=True)
@require_http_methods(["GET", "POST"])
def configuracao_empresa(request):
    with transaction.atomic():
        configuracao = ConfiguracaoEmpresa.objects.select_for_update().first()
        form = ConfiguracaoEmpresaForm(
            request.POST if request.method == "POST" else None,
            request.FILES if request.method == "POST" else None,
            instance=configuracao,
        )
        if request.method == "POST" and form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError:
                form.add_error(None, "A configuração foi criada por outro usuário. Recarregue a página antes de editar.")
            else:
                messages.success(request, "Configurações da empresa salvas.")
                return redirect("core:configuracao_empresa")
    response = render(request, "core/configuracao_empresa.html", {"form": form, "configuracao": configuracao})
    response["Cache-Control"] = "private, no-store"
    return response
