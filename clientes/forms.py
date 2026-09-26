from django import forms
from core.forms import EstiloForm
from .models import Cliente


class ClienteForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nome", "documento", "telefone", "email", "endereco", "observacoes", "ativo"]
