from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, render, redirect
from core.auditoria import registrar
from .models import ContaReceber
from .forms import PlanoReceberForm
from .services import salvar_plano_receber


@login_required
@permission_required('comercial.change_contareceber', raise_exception=True)
def parcelamento(request, pk):
    conta = get_object_or_404(ContaReceber, pk=pk)
    form = PlanoReceberForm(request.POST if request.method == 'POST' else None,
        total=conta.valor_original, initial={'vencimento': conta.vencimento})
    if request.method == 'POST' and form.is_valid():
        try:
            salvar_plano_receber(request.user, conta, form.cleaned_data['plano'])
            messages.success(request, 'Parcelamento atualizado. Nenhum recebimento foi registrado.')
            return redirect('comercial:conta', pk=pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'comercial/conta_formulario.html', {'form':form, 'conta':conta,
        'titulo':f'Parcelamento de {conta.codigo}'})


@login_required
@permission_required('comercial.delete_contareceber', raise_exception=True)
@transaction.atomic
def excluir(request, pk):
    conta = get_object_or_404(ContaReceber.objects.select_for_update(), pk=pk)
    permitido = not (conta.venda_id or conta.os_id or conta.recebimentos.exists())
    if request.method == 'POST':
        if not permitido:
            messages.error(request, 'Conta vinculada a venda/OS ou com recebimentos: o histórico deve ser preservado.')
            return redirect('comercial:conta', pk=pk)
        if request.POST.get('confirmar') == 'sim':
            registrar(request.user, 'conta.receber_excluida', conta.codigo, valor=str(conta.valor_original))
            conta.delete()
            messages.success(request, 'Conta excluída.')
            return redirect('comercial:contas')
    return render(request, 'comercial/conta_excluir.html', {'conta':conta, 'permitido':permitido})


@login_required
@permission_required('comercial.view_contareceber', raise_exception=True)
def imprimir(request, pk):
    conta = get_object_or_404(ContaReceber.objects.select_related('cliente','venda','os')
        .prefetch_related('recebimentos__operador','parcelas_financeiras__forma_prevista'), pk=pk)
    return render(request, 'comercial/conta_imprimir.html', {'conta':conta})
