from django import forms
from decimal import Decimal
from core.forms import EstiloForm


class AberturaForm(EstiloForm, forms.Form):
    saldo = forms.DecimalField(label="Dinheiro inicial (R$)", min_value=0, max_digits=12, decimal_places=2, localize=True)


class MovimentoForm(EstiloForm, forms.Form):
    chave = forms.UUIDField(widget=forms.HiddenInput)
    tipo = forms.ChoiceField(choices=[("suprimento", "Suprimento — entrada de dinheiro"), ("sangria", "Sangria — retirada de dinheiro")])
    valor = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2, localize=True)
    motivo = forms.CharField(max_length=240)


class FechamentoForm(EstiloForm, forms.Form):
    informado = forms.DecimalField(label="Dinheiro contado (R$)", min_value=0, max_digits=12, decimal_places=2, localize=True)
    observacoes = forms.CharField(label="Observações / justificativa de diferença", required=False, widget=forms.Textarea)
