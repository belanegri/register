from django import forms
from .parcelamento import FREQUENCIAS


class CamposParcelamento(forms.Form):
    entrada = forms.DecimalField(label='Entrada prevista', max_digits=12, decimal_places=2,
                                 min_value=0, required=False, help_text='Não confirma pagamento automaticamente.')
    data_entrada = forms.DateField(label='Vencimento da entrada', required=False,
                                  widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    intervalo_dias = forms.IntegerField(label='Intervalo em dias', min_value=1, max_value=3650, required=False, initial=30)
    plano_personalizado = forms.CharField(label='Parcelas personalizadas', required=False, max_length=12000,
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': '2026-11-05;100,00\n2026-12-05;150,00'}),
        help_text='Ajuste os valores, vencimentos e formas por parcela. Inclua a entrada; a soma deve fechar o total.')


def validar_formas(plano):
    from vendas.models import FormaPagamento
    ids = {p['forma_id'] for p in plano if p['forma_id']}
    if ids - set(FormaPagamento.objects.filter(pk__in=ids, ativa=True, promissoria=False).values_list('pk', flat=True)):
        raise forms.ValidationError('Selecione formas de pagamento ativas, sem promissória, para as parcelas.')
