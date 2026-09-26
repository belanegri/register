from django import forms
from decimal import Decimal
from django.utils import timezone
from core.forms import EstiloForm
from clientes.models import Cliente
from .models import FormaPagamento
from estoque.models import Peca


class CheckoutForm(EstiloForm, forms.Form):
    chave = forms.UUIDField(widget=forms.HiddenInput)
    cliente = forms.ModelChoiceField(queryset=Cliente.objects.filter(ativo=True), required=False, empty_label="Consumidor não identificado")
    desconto = forms.DecimalField(label="Desconto total (R$)", min_value=0, max_digits=12, decimal_places=2, initial=0, localize=True)
    vencimento = forms.DateField(label="Vencimento da promissória", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    beneficiario = forms.CharField(label="Beneficiário (nome / razão social)", max_length=160, initial="PontoCar Comércio de Peças", required=False)
    documento_beneficiario = forms.CharField(label="CPF/CNPJ do beneficiário", max_length=20, required=False)
    local_emissao = forms.CharField(label="Local de emissão (cidade/UF)", max_length=160, required=False)
    local_pagamento = forms.CharField(label="Local de pagamento (endereço/cidade)", max_length=200, required=False)


class FormaWidget(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value and hasattr(value, "instance"):
            option["attrs"]["data-dinheiro"] = "1" if value.instance.dinheiro else "0"
            option["attrs"]["data-promissoria"] = "1" if value.instance.promissoria else "0"
        return option


class PagamentoForm(EstiloForm, forms.Form):
    forma = forms.ModelChoiceField(label="Forma", queryset=FormaPagamento.objects.filter(ativa=True), widget=FormaWidget)
    valor = forms.DecimalField(label="Valor (R$)", min_value=Decimal("0.01"), max_digits=12, decimal_places=2, localize=True)


PagamentosFormSet = forms.formset_factory(PagamentoForm, extra=3, max_num=8, validate_max=True, min_num=1, validate_min=True)


class CancelamentoForm(EstiloForm, forms.Form):
    motivo = forms.CharField(max_length=1000, widget=forms.Textarea)


class DevolucaoForm(CancelamentoForm):
    chave = forms.UUIDField(widget=forms.HiddenInput)
    item = forms.ChoiceField(label="Item a devolver")
    quantidade = forms.IntegerField(min_value=1)
    forma = forms.ModelChoiceField(label="Forma de reembolso (se houver valor recebido)", queryset=FormaPagamento.objects.filter(ativa=True, promissoria=False))


class CorrecaoForm(CheckoutForm):
    motivo = forms.CharField(label="Motivo da edição", max_length=1000, widget=forms.Textarea)


class ItemCorrecaoForm(EstiloForm, forms.Form):
    peca = forms.ModelChoiceField(queryset=Peca.objects.all(), label="Peça")
    quantidade = forms.IntegerField(min_value=1, max_value=1000000)
    preco = forms.DecimalField(label="Preço unitário (R$)", max_digits=12, decimal_places=2, min_value=0, localize=True)


ItensCorrecaoFormSet = forms.formset_factory(ItemCorrecaoForm, extra=1, can_delete=True, max_num=100, validate_max=True, min_num=1, validate_min=True)


class ReceberNotaForm(EstiloForm, forms.Form):
    chave = forms.UUIDField(widget=forms.HiddenInput)
    forma = forms.ModelChoiceField(label="Recebido por", queryset=FormaPagamento.objects.filter(ativa=True, promissoria=False))
    valor = forms.DecimalField(label="Valor recebido (R$)", min_value=Decimal(".01"), max_digits=12, decimal_places=2, localize=True)


class PeriodoForm(EstiloForm, forms.Form):
    inicio = forms.DateField(label="De", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    fim = forms.DateField(label="Até", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    def clean(self):
        data = super().clean()
        if data.get("inicio") and data.get("fim"):
            if data["inicio"] > data["fim"] or (data["fim"] - data["inicio"]).days > 366:
                raise forms.ValidationError("Escolha um intervalo em ordem, de até 366 dias.")
        return data
